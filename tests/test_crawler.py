from pathlib import Path

import httpx
import respx

from lead_finder.crawler import SiteCrawler, enrich_all
from lead_finder.models import Business

HOME = (Path(__file__).parent / "fixtures" / "home.html").read_text()
CONTACT = '<html><body><a href="mailto:office@sunshinecooling.com">Email</a></body></html>'
HTML = {"content-type": "text/html; charset=utf-8"}


def make(website: str) -> Business:
    return Business(osm_type="node", osm_id=1, name="Sunshine", website=website)


@respx.mock
async def test_crawls_homepage_and_contact_pages():
    respx.get("https://www.sunshinecooling.com/robots.txt").respond(404)
    respx.get("https://www.sunshinecooling.com/").respond(200, text=HOME, headers=HTML)
    respx.get("https://www.sunshinecooling.com/contact-us/").respond(200, text=CONTACT, headers=HTML)
    respx.get("https://www.sunshinecooling.com/about").respond(404)

    [b] = await enrich_all([make("https://www.sunshinecooling.com/")])
    assert b.crawl_status == "ok"
    assert b.pages_crawled == 2
    assert "office@sunshinecooling.com" in b.site_emails
    assert "service@sunshinecooling.com" in b.site_emails
    assert b.socials["facebook"].endswith("sunshinecoolingmiami")


@respx.mock
async def test_respects_robots_txt():
    respx.get("https://blocked.example.net/robots.txt").respond(200, text="User-agent: *\nDisallow: /\n")
    home = respx.get("https://blocked.example.net/")

    [b] = await enrich_all([make("https://blocked.example.net/")])
    assert b.crawl_status == "blocked_by_robots"
    assert not home.called


@respx.mock
async def test_unreachable_and_timeout_statuses():
    respx.get("https://down.example.net/robots.txt").respond(404)
    respx.get("https://down.example.net/").respond(500)
    respx.get("https://slow.example.net/robots.txt").respond(404)
    respx.get("https://slow.example.net/").mock(side_effect=httpx.ReadTimeout("slow"))

    down, slow = await enrich_all([make("https://down.example.net/"), make("https://slow.example.net/")])
    assert down.crawl_status == "unreachable"
    assert slow.crawl_status == "timeout"


async def test_no_website():
    async with httpx.AsyncClient() as client:
        b = await SiteCrawler(client).enrich(make(""))
    assert b.crawl_status == "no_website"
