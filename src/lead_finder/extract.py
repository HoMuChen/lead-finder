"""Pull contact details (emails, phones, social links, contact pages) out of HTML."""

from __future__ import annotations

import re
from urllib.parse import unquote, urljoin, urlparse

import phonenumbers
from bs4 import BeautifulSoup

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}")

# Addresses that show up on websites but never belong to the business.
IGNORED_EMAIL_DOMAINS = {
    "example.com", "example.org", "domain.com", "email.com", "yourdomain.com", "yoursite.com",
    "sentry.io", "wixpress.com", "sentry.wixpress.com", "sentry-next.wixpress.com", "godaddy.com",
    "mysite.com", "company.com", "test.com",
}
IGNORED_EMAIL_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js")

SOCIAL_PATTERNS = {
    "facebook": re.compile(r"(?:^|\.)facebook\.com$"),
    "instagram": re.compile(r"(?:^|\.)instagram\.com$"),
    "linkedin": re.compile(r"(?:^|\.)linkedin\.com$"),
    "x": re.compile(r"(?:^|\.)(?:twitter|x)\.com$"),
    "youtube": re.compile(r"(?:^|\.)youtube\.com$"),
}
# Share buttons and platform pages rather than the business's own profile.
SOCIAL_IGNORED_PATHS = re.compile(r"/(?:sharer|share|intent|dialog|plugins|embed|watch)\b", re.I)

CONTACT_HINTS = re.compile(r"contact|about|get-in-touch|reach-us|location", re.I)


def decode_cfemail(encoded: str) -> str:
    """Decode a Cloudflare email-protection string (``data-cfemail`` / ``/cdn-cgi/l/email-protection#``)."""
    try:
        key = int(encoded[:2], 16)
        return "".join(chr(int(encoded[i : i + 2], 16) ^ key) for i in range(2, len(encoded), 2))
    except ValueError:
        return ""


def is_valid_email(email: str) -> bool:
    email = email.lower()
    if not EMAIL_RE.fullmatch(email) or email.endswith(IGNORED_EMAIL_SUFFIXES):
        return False
    local, _, domain = email.partition("@")
    if domain in IGNORED_EMAIL_DOMAINS:
        return False
    # Long hex local parts are tracking ids (e.g. Sentry DSNs), not mailboxes.
    return not re.fullmatch(r"[0-9a-f]{16,}", local)


def extract_emails(soup: BeautifulSoup, text: str) -> list[str]:
    found: list[str] = []
    for a in soup.select('a[href^="mailto:"]'):
        addr = unquote(a["href"][len("mailto:") :]).split("?")[0]
        found.extend(addr.split(","))
    for el in soup.select("[data-cfemail]"):
        found.append(decode_cfemail(el["data-cfemail"]))
    for a in soup.select('a[href*="/cdn-cgi/l/email-protection#"]'):
        found.append(decode_cfemail(a["href"].split("#", 1)[1]))
    found.extend(EMAIL_RE.findall(text))
    return _unique(e.strip().lower() for e in found if is_valid_email(e.strip()))


def extract_phones(soup: BeautifulSoup, text: str, region: str) -> list[str]:
    """Return phone numbers in E.164 format, ``tel:`` links first."""
    found: list[str] = []
    for a in soup.select('a[href^="tel:"]'):
        number = normalize_phone(unquote(a["href"][len("tel:") :]), region)
        if number:
            found.append(number)
    for match in phonenumbers.PhoneNumberMatcher(text, region):
        if phonenumbers.is_valid_number(match.number):
            found.append(phonenumbers.format_number(match.number, phonenumbers.PhoneNumberFormat.E164))
    return _unique(found)


def normalize_phone(raw: str, region: str) -> str:
    """Normalize a phone number to E.164, or return ``""`` if it isn't valid."""
    try:
        number = phonenumbers.parse(raw, region)
    except phonenumbers.NumberParseException:
        return ""
    if not phonenumbers.is_valid_number(number):
        return ""
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def extract_socials(soup: BeautifulSoup) -> dict[str, str]:
    socials: dict[str, str] = {}
    for a in soup.select("a[href]"):
        href = a["href"].strip()
        try:
            parsed = urlparse(href)
        except ValueError:  # Malformed hrefs such as "http://[placeholder]".
            continue
        host = parsed.netloc.lower().removeprefix("www.").removeprefix("m.")
        if not host or SOCIAL_IGNORED_PATHS.search(parsed.path) or parsed.path in ("", "/"):
            continue
        # Drop tracking query strings, except where the query *is* the profile (facebook.com/profile.php?id=...).
        link = href if parsed.path.endswith("profile.php") else href.split("?")[0]
        for network, pattern in SOCIAL_PATTERNS.items():
            if network not in socials and pattern.search(host):
                socials[network] = link
    return socials


def find_contact_pages(soup: BeautifulSoup, base_url: str, limit: int = 3) -> list[str]:
    """Links on the same site that look like contact/about pages."""
    base_host = _host(base_url)
    pages: list[str] = []
    for a in soup.select("a[href]"):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        try:
            url = urljoin(base_url, href).split("#")[0]
            host = _host(url)
        except ValueError:
            continue
        if host != base_host or url.rstrip("/") == base_url.rstrip("/"):
            continue
        if CONTACT_HINTS.search(href) or CONTACT_HINTS.search(a.get_text(" ", strip=True)):
            if url not in pages:
                pages.append(url)
        if len(pages) >= limit:
            break
    return pages


def parse_page(html: str, url: str, region: str) -> dict:
    """Extract everything useful from one page."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    return {
        "emails": extract_emails(soup, text),
        "phones": extract_phones(soup, text, region),
        "socials": extract_socials(soup),
        "contact_pages": find_contact_pages(soup, url),
    }


def _host(url: str) -> str:
    return urlparse(url).netloc.lower().removeprefix("www.")


def _unique(items) -> list:
    return list(dict.fromkeys(items))
