from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Business:
    """A business found in OpenStreetMap, optionally enriched from its website."""

    osm_type: str
    osm_id: int
    name: str
    category: str = ""
    website: str = ""
    address: str = ""
    city: str = ""
    state: str = ""
    postcode: str = ""
    lat: float | None = None
    lon: float | None = None
    # Contact details as listed in OSM.
    osm_emails: list[str] = field(default_factory=list)
    osm_phones: list[str] = field(default_factory=list)
    # Contact details found on the business website.
    site_emails: list[str] = field(default_factory=list)
    site_phones: list[str] = field(default_factory=list)
    socials: dict[str, str] = field(default_factory=dict)
    pages_crawled: int = 0
    crawl_status: str = "not_crawled"
    # Filled in by the cleaning step.
    best_email: str = ""
    email_source: str = ""
    best_phone: str = ""
    all_emails: list[str] = field(default_factory=list)
    all_phones: list[str] = field(default_factory=list)
    email_mx_ok: bool | None = None

    @property
    def osm_url(self) -> str:
        return f"https://www.openstreetmap.org/{self.osm_type}/{self.osm_id}"
