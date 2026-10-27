"""Command-line entry point: ``lead-finder find --category hvac --area Florida``."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.progress import Progress
from rich.table import Table

from . import clean, crawler, export, osm

app = typer.Typer(add_completion=False, help="Build B2B lead lists from OpenStreetMap + business websites.")
console = Console()

USER_AGENT = "lead-finder/0.1 (+https://github.com/HoMuChen/lead-finder)"


@app.command()
def categories() -> None:
    """List built-in category presets and the OSM tags they map to."""
    table = Table("category", "OSM tags")
    for name, tags in osm.CATEGORIES.items():
        table.add_row(name, ", ".join(f"{k}={v}" for k, v in tags))
    console.print(table)


@app.command()
def find(
    area: Annotated[str, typer.Option(help='Administrative area name as in OSM, e.g. "Florida" or "Austin".')],
    category: Annotated[Optional[str], typer.Option(help="Built-in category preset (see `categories`).")] = None,
    tag: Annotated[Optional[list[str]], typer.Option(help="Extra OSM tag filter key=value (repeatable).")] = None,
    admin_level: Annotated[Optional[int], typer.Option(help="Restrict the area match to an OSM admin_level (4=state, 8=city).")] = None,
    region: Annotated[str, typer.Option(help="Default country for phone parsing (ISO code).")] = "US",
    out: Annotated[Path, typer.Option(help="Output path; .csv and .xlsx are written side by side.")] = Path("out/leads.csv"),
    limit: Annotated[Optional[int], typer.Option(help="Only keep the first N businesses.")] = None,
    crawl: Annotated[bool, typer.Option(help="Visit business websites to find more contact details.")] = True,
    verify_mx: Annotated[bool, typer.Option(help="Check that email domains have MX records.")] = True,
    concurrency: Annotated[int, typer.Option(help="Websites crawled in parallel.")] = 8,
) -> None:
    """Find businesses in an area and export an enriched lead list."""
    tags = list(osm.CATEGORIES.get(category, [])) if category else []
    if category and category not in osm.CATEGORIES:
        raise typer.BadParameter(f"Unknown category {category!r}; run `lead-finder categories`.")
    tags += [osm.parse_tag(t) for t in tag or []]
    if not tags:
        raise typer.BadParameter("Give --category and/or at least one --tag key=value.")
    asyncio.run(_run(area, tags, category or "custom", admin_level, region, out, limit, crawl, verify_mx, concurrency))


async def _run(area, tags, category, admin_level, region, out, limit, crawl, verify_mx, concurrency) -> None:
    with console.status(f"Searching OpenStreetMap for {category} in {area}..."):
        businesses = await osm.search(area, tags, category, admin_level=admin_level, user_agent=USER_AGENT)
    businesses = clean.dedupe(businesses)[:limit]
    console.print(f"Found [bold]{len(businesses)}[/] businesses ({sum(1 for b in businesses if b.website)} with a website).")

    if crawl:
        with Progress(console=console) as progress:
            task = progress.add_task("Crawling websites", total=len(businesses))
            await crawler.enrich_all(
                businesses, region=region, concurrency=concurrency, user_agent=USER_AGENT,
                on_done=lambda _: progress.advance(task),
            )

    for biz in businesses:
        clean.finalize(biz, region)
    if verify_mx:
        with console.status("Checking email domains (MX)..."):
            await clean.verify_mx(businesses)

    stats = export.coverage(businesses)
    csv_path = out.with_suffix(".csv")
    xlsx_path = out.with_suffix(".xlsx")
    export.write_csv(businesses, csv_path)
    export.write_xlsx(businesses, xlsx_path, stats)

    table = Table("metric", "count", "share")
    for key, value in stats.items():
        share = f"{value / stats['businesses']:.0%}" if stats["businesses"] and key != "businesses" else ""
        table.add_row(key, str(value), share)
    console.print(table)
    console.print(f"Saved [bold]{csv_path}[/] and [bold]{xlsx_path}[/]")


if __name__ == "__main__":
    app()
