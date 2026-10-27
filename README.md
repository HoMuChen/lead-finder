# lead-finder

**Turn "find me every HVAC company in Florida with an email" into a clean spreadsheet in minutes.**

`lead-finder` builds B2B lead lists from [OpenStreetMap](https://www.openstreetmap.org/) and then visits each
business website to fill in the contact details OSM is missing — emails (including Cloudflare-obfuscated ones),
phone numbers, and social profiles. Results are de-duplicated, normalized, ranked and exported to CSV + Excel.

## Real run: HVAC contractors in Florida

```
$ lead-finder find --category hvac --area Florida --admin-level 4 --out out/florida_hvac.csv
Found 127 businesses (98 with a website).
```

| metric | OpenStreetMap only | after website enrichment |
|---|---:|---:|
| businesses | 127 | 127 |
| with email | 29 (23%) | **52 (41%)** |
| with phone | 98 (77%) | **102 (80%)** |
| with a social profile | – | **66 (52%)** |

- Every email domain passed an MX check (it can actually receive mail).
- 29 of 52 emails are on the company's own domain; the rest are flagged with `email_matches_site=False`
  (typically Gmail/Yahoo inboxes used by small businesses) so you can decide how to treat them.
- 21 listed websites could not be crawled (11 dead domains, 7 unreachable, 1 timeout, 1 disallowed by robots.txt) —
  each row records why in `crawl_status`.

Sample output (emails partially masked for this public repo): [`examples/florida_hvac_sample.csv`](examples/florida_hvac_sample.csv)

## Quick start

```bash
git clone https://github.com/HoMuChen/lead-finder && cd lead-finder
uv sync
uv run lead-finder find --category dentist --area "Austin" --admin-level 8 --out out/austin_dentists.csv
```

Writes `out/austin_dentists.csv` and `out/austin_dentists.xlsx` (with a filterable **Leads** sheet and a
**Summary** sheet).

### Options

| option | meaning |
|---|---|
| `--area` | Administrative area name as it appears in OSM (state, county, city…) |
| `--admin-level` | Disambiguate the area: `4` = state, `6` = county, `8` = city (US) |
| `--category` | Built-in preset — run `lead-finder categories` (hvac, plumber, electrician, roofer, dentist, lawyer, accountant, real_estate, restaurant, cafe, gym, hotel, car_repair) |
| `--tag key=value` | Any OSM tag, repeatable — e.g. `--tag shop=florist --tag craft=gardener` |
| `--region` | Default country for phone parsing (default `US`) |
| `--limit N` | Keep only the first N businesses |
| `--no-crawl` | Skip website enrichment (OSM data only) |
| `--no-verify-mx` | Skip the MX check |
| `--concurrency` | Websites crawled in parallel (default 8) |

### Output columns

`name, website, email, email_source (osm|website), email_matches_site, email_mx_ok, phone (E.164),
all_emails, all_phones, facebook, instagram, linkedin, x, youtube, address, city, state, postcode, lat, lon,
crawl_status, osm_url`

## How it works

```
OpenStreetMap (Overpass API) ──► businesses + any listed contact info
            │
            ▼
 website crawler ── homepage + up to 3 contact/about pages
            │        • mailto: links, plain-text emails, Cloudflare data-cfemail decoding
            │        • tel: links + libphonenumber text matching
            │        • Facebook / Instagram / LinkedIn / X / YouTube profile links
            ▼
 cleaning ── junk-email filter (example.com, sentry, image@2x.png…), E.164 phones,
            │ rank emails (own domain > generic inbox like info@ > others),
            │ de-dupe by domain and name+city, MX verification
            ▼
 CSV + Excel (Leads + Summary sheets)
```

## Responsible use

- Only public sources: OSM data and the businesses' own public websites. No LinkedIn, Google Maps or other
  platforms whose terms forbid scraping.
- Respects `robots.txt`, identifies itself with a descriptive User-Agent, limits concurrency and crawls at most
  4 pages per site.
- OSM data is © OpenStreetMap contributors, available under the [ODbL](https://www.openstreetmap.org/copyright).
- Make sure your outreach complies with CAN-SPAM / GDPR and similar rules.

## Development

```bash
uv sync
uv run pytest      # 28 tests: extraction, OSM parsing, cleaning, crawler (HTTP mocked), export
```

## Need a custom lead list or scraper?

I build data collection, enrichment and automation tools — custom sources, CRM/Google Sheets delivery,
scheduled refreshes. Reach out on Upwork.

## License

MIT
