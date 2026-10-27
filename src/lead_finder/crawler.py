"""Politely crawl business websites (homepage + a few contact pages) for contact details."""

from __future__ import annotations

import asyncio
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from .extract import parse_page
from .models import Business


class SiteCrawler:
    def __init__(
        self,
        client: httpx.AsyncClient,
        region: str = "US",
        max_pages: int = 4,
        concurrency: int = 8,
        user_agent: str = "lead-finder",
    ) -> None:
        self.client = client
        self.region = region
        self.max_pages = max_pages
        self.user_agent = user_agent
        self._sem = asyncio.Semaphore(concurrency)
        self._robots: dict[str, RobotFileParser | None] = {}

    async def _allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots:
            rp: RobotFileParser | None = RobotFileParser()
            try:
                resp = await self.client.get(origin + "/robots.txt")
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                else:
                    rp = None  # No robots.txt: everything is allowed.
            except httpx.HTTPError:
                rp = None
            self._robots[origin] = rp
        rp = self._robots[origin]
        return rp is None or rp.can_fetch(self.user_agent, url)

    async def _fetch(self, url: str) -> tuple[str, str] | None:
        """Return ``(final_url, html)`` or ``None`` if the page can't be used."""
        if not await self._allowed(url):
            return None
        resp = await self.client.get(url)
        if resp.status_code >= 400 or "html" not in resp.headers.get("content-type", ""):
            return None
        return str(resp.url), resp.text

    async def enrich(self, biz: Business) -> Business:
        if not biz.website:
            biz.crawl_status = "no_website"
            return biz
        async with self._sem:
            try:
                await self._crawl(biz)
            except httpx.TimeoutException:
                biz.crawl_status = "timeout"
            except (httpx.HTTPError, httpx.InvalidURL, ValueError, UnicodeError) as exc:
                # Broken DNS, TLS, URLs or markup on one site must not stop the whole run.
                biz.crawl_status = f"error:{type(exc).__name__}"
        return biz

    async def _crawl(self, biz: Business) -> None:
        if not await self._allowed(biz.website):
            biz.crawl_status = "blocked_by_robots"
            return
        first = await self._fetch(biz.website)
        if first is None:
            biz.crawl_status = "unreachable"
            return
        home_url, html = first
        queue = [(home_url, html)]
        seen = {home_url}
        emails: list[str] = []
        phones: list[str] = []
        socials: dict[str, str] = {}

        while queue and biz.pages_crawled < self.max_pages:
            url, html = queue.pop(0)
            biz.pages_crawled += 1
            found = parse_page(html, url, self.region)
            emails += found["emails"]
            phones += found["phones"]
            for network, link in found["socials"].items():
                socials.setdefault(network, link)
            # Only follow contact-page links from the homepage.
            if url == home_url:
                for link in found["contact_pages"]:
                    if link in seen or len(seen) >= self.max_pages:
                        continue
                    seen.add(link)
                    page = await self._fetch(link)
                    if page:
                        queue.append(page)

        biz.site_emails = list(dict.fromkeys(emails))
        biz.site_phones = list(dict.fromkeys(phones))
        biz.socials = socials
        biz.crawl_status = "ok"


async def enrich_all(
    businesses: list[Business],
    region: str = "US",
    concurrency: int = 8,
    timeout: float = 15.0,
    user_agent: str = "lead-finder",
    on_done=None,
) -> list[Business]:
    headers = {"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml"}
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
        crawler = SiteCrawler(client, region=region, concurrency=concurrency, user_agent=user_agent)

        async def run(biz: Business) -> Business:
            result = await crawler.enrich(biz)
            if on_done:
                on_done(result)
            return result

        return await asyncio.gather(*(run(b) for b in businesses))
