"""Merge, normalize, rank and de-duplicate contact details."""

from __future__ import annotations

from urllib.parse import urlparse

import dns.asyncresolver
import dns.exception

from .extract import is_valid_email, normalize_phone
from .models import Business

# Generic inboxes a business is likely to read, in order of preference.
PREFERRED_LOCAL_PARTS = ("info", "contact", "office", "hello", "sales", "service", "support", "admin")


def site_domain(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def rank_emails(emails: list[str], website: str) -> list[str]:
    """Order emails so the most useful one comes first."""
    domain = site_domain(website)

    def score(email: str) -> tuple[int, int]:
        local, _, email_domain = email.partition("@")
        same_domain = bool(domain) and (email_domain == domain or email_domain.endswith("." + domain))
        generic = local in PREFERRED_LOCAL_PARTS
        return (0 if same_domain else 1, PREFERRED_LOCAL_PARTS.index(local) if generic else len(PREFERRED_LOCAL_PARTS))

    return sorted(emails, key=score)


def finalize(biz: Business, region: str = "US") -> Business:
    """Fill ``best_*`` / ``all_*`` fields from the OSM and website data."""
    osm_emails = [e.lower() for e in biz.osm_emails if is_valid_email(e)]
    emails = list(dict.fromkeys(osm_emails + biz.site_emails))
    biz.all_emails = rank_emails(emails, biz.website)
    if osm_emails:
        biz.best_email, biz.email_source = osm_emails[0], "osm"
    elif biz.all_emails:
        biz.best_email, biz.email_source = biz.all_emails[0], "website"

    osm_phones = [p for p in (normalize_phone(raw, region) for raw in biz.osm_phones) if p]
    biz.all_phones = list(dict.fromkeys(osm_phones + biz.site_phones))
    biz.best_phone = biz.all_phones[0] if biz.all_phones else ""
    return biz


def dedupe(businesses: list[Business]) -> list[Business]:
    """Drop duplicates that share a website domain, or the same name in the same city."""
    seen: set[str] = set()
    result = []
    for biz in businesses:
        keys = {f"name:{biz.name.lower().strip()}|{biz.city.lower().strip()}"}
        if biz.website:
            keys.add(f"site:{site_domain(biz.website)}")
        if keys & seen:
            continue
        seen |= keys
        result.append(biz)
    return result


async def has_mx(domain: str, resolver: dns.asyncresolver.Resolver | None = None) -> bool:
    resolver = resolver or dns.asyncresolver.Resolver()
    try:
        answer = await resolver.resolve(domain, "MX", lifetime=5)
        return len(answer) > 0
    except (dns.exception.DNSException, OSError):
        return False


async def verify_mx(businesses: list[Business]) -> None:
    """Check that each best email's domain can receive mail (MX record exists)."""
    resolver = dns.asyncresolver.Resolver()
    cache: dict[str, bool] = {}
    for biz in businesses:
        if not biz.best_email:
            continue
        domain = biz.best_email.partition("@")[2]
        if domain not in cache:
            cache[domain] = await has_mx(domain, resolver)
        biz.email_mx_ok = cache[domain]
