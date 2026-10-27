"""Find businesses in an area through the OpenStreetMap Overpass API."""

from __future__ import annotations

import re

import httpx

from .models import Business

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Category presets: each maps to one or more OSM key=value tags.
CATEGORIES: dict[str, list[tuple[str, str]]] = {
    "hvac": [("craft", "hvac"), ("shop", "hvac"), ("trade", "hvac")],
    "plumber": [("craft", "plumber"), ("trade", "plumber")],
    "electrician": [("craft", "electrician"), ("trade", "electrician")],
    "roofer": [("craft", "roofer")],
    "car_repair": [("shop", "car_repair")],
    "dentist": [("amenity", "dentist"), ("healthcare", "dentist")],
    "lawyer": [("office", "lawyer")],
    "accountant": [("office", "accountant")],
    "real_estate": [("office", "estate_agent")],
    "restaurant": [("amenity", "restaurant")],
    "cafe": [("amenity", "cafe")],
    "gym": [("leisure", "fitness_centre")],
    "hotel": [("tourism", "hotel")],
}

_SAFE_VALUE = re.compile(r'^[^"\\\n]+$')


def parse_tag(spec: str) -> tuple[str, str]:
    """Parse a ``key=value`` tag filter given on the command line."""
    key, sep, value = spec.partition("=")
    if not sep or not key.strip() or not value.strip():
        raise ValueError(f"Tag filter must look like key=value, got {spec!r}")
    return key.strip(), value.strip()


def build_query(
    area: str,
    tags: list[tuple[str, str]],
    admin_level: int | None = None,
    timeout: int = 120,
) -> str:
    """Build an Overpass QL query for all objects with any of ``tags`` inside ``area``."""
    for value in [area, *(k for k, _ in tags), *(v for _, v in tags)]:
        if not _SAFE_VALUE.match(value):
            raise ValueError(f"Unsupported characters in {value!r}")
    if not tags:
        raise ValueError("At least one tag filter is required")

    area_filter = f'area["name"="{area}"]["boundary"="administrative"]'
    if admin_level is not None:
        area_filter += f'["admin_level"="{admin_level}"]'
    selectors = "\n".join(f'  nwr["{k}"="{v}"](area.a);' for k, v in tags)
    return f"[out:json][timeout:{timeout}];\n{area_filter}->.a;\n(\n{selectors}\n);\nout tags center;\n"


def _split_multi(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[;,]", value) if part.strip()]


def _normalize_website(url: str) -> str:
    url = url.strip()
    if url and not re.match(r"^https?://", url, re.I):
        url = "https://" + url
    return url


def parse_elements(elements: list[dict], category: str) -> list[Business]:
    """Turn Overpass JSON elements into :class:`Business` records (unnamed ones are skipped)."""
    businesses = []
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name", "").strip()
        if not name:
            continue
        center = el.get("center", {})
        street = " ".join(p for p in [tags.get("addr:housenumber", ""), tags.get("addr:street", "")] if p)
        emails = _split_multi(tags.get("email", "")) + _split_multi(tags.get("contact:email", ""))
        phones = _split_multi(tags.get("phone", "")) + _split_multi(tags.get("contact:phone", ""))
        website = tags.get("website") or tags.get("contact:website") or tags.get("url") or ""
        businesses.append(
            Business(
                osm_type=el.get("type", "node"),
                osm_id=int(el["id"]),
                name=name,
                category=category,
                website=_normalize_website(website),
                address=street,
                city=tags.get("addr:city", ""),
                state=tags.get("addr:state", ""),
                postcode=tags.get("addr:postcode", ""),
                lat=el.get("lat", center.get("lat")),
                lon=el.get("lon", center.get("lon")),
                osm_emails=emails,
                osm_phones=phones,
            )
        )
    return businesses


async def search(
    area: str,
    tags: list[tuple[str, str]],
    category: str,
    admin_level: int | None = None,
    endpoint: str = OVERPASS_URL,
    user_agent: str = "lead-finder",
) -> list[Business]:
    """Query Overpass and return the businesses found."""
    query = build_query(area, tags, admin_level=admin_level)
    async with httpx.AsyncClient(timeout=180, headers={"User-Agent": user_agent}) as client:
        resp = await client.post(endpoint, data={"data": query})
        resp.raise_for_status()
        return parse_elements(resp.json().get("elements", []), category)
