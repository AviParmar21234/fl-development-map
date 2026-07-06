# Morgan Group · Florida Development Radar

An interactive map of development and multifamily opportunity signals across South and Central Florida, scraped from public municipal agenda portals and county development trackers.

**Live map:** deployed via GitHub Pages (see repo Settings → Pages for URL).

## What it shows

Every pin is a real development item from a public record — rezonings, land-use amendments, site plans, PUDs, plats, variances, special exceptions, development agreements, annexations — pulled from planning/zoning board and commission agendas across ~37 jurisdictions in Miami-Dade, Broward, Palm Beach, Orange, Osceola, Seminole, Lake, Hillsborough, Pinellas, and Polk counties. Multifamily-relevant items (apartments, mixed-use, workforce/affordable housing, Live Local Act) are highlighted in brass.

Every popup links back to the source agenda item. Items with no extractable address appear in the **Unmapped** panel instead of getting fake pins. The **Coverage** panel shows exactly which sources were scraped and which failed.

## Refresh the data

```bash
./refresh.sh
```

Scrapes all enabled sources in `sources.json`, geocodes new addresses (US Census batch + Nominatim fallback, cached in `geocache.json`), rebuilds `site/data/`, commits, and pushes — the live site updates automatically.

## Add a city

If it runs on Legistar, IQM2/Granicus, CivicClerk, or NovusAgenda: add one entry to `sources.json` with the platform and URL, set `enabled: true`, and refresh. Otherwise see `docs/coverage-notes.md` for the follow-up list and add a connector in `scraper/connectors/`.

## Architecture

```
sources.json          jurisdiction registry (platform + URL per source)
scraper/connectors/   one connector per agenda platform
scraper/filter.py     development-item classifier + multifamily flag
scraper/extract.py    address & parcel extraction
scraper/geocode.py    census batch geocoder with persistent cache
scraper/run.py        pipeline: scrape → classify → extract → geocode → build
site/                 static Leaflet map (GitHub Pages)
```

Tests: `.venv/bin/pytest tests/ -q`
