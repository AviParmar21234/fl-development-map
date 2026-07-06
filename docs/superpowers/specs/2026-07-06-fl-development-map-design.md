# Florida Development Opportunity Map — Design Spec

**Date:** 2026-07-06
**Client:** Morgan Group (multifamily developer)
**Goal:** A hosted, shareable interactive map of upcoming development/construction activity across South and Central Florida, with a multifamily-opportunity focus, refreshable with one command, extensible city-by-city.

## Purpose

Surface future development projects — before and as they hit public hearings — so Morgan Group can spot multifamily opportunities (land in play, rezonings, density increases, competing projects) across the region. Every pin must be traceable to its public source (agenda item or county application record).

## Geography (tonight's target)

- **South Florida:** Miami-Dade, Broward, Palm Beach counties + major cities (Miami, Miami Beach, Hialeah, Coral Gables, Doral, Homestead, North Miami, Fort Lauderdale, Hollywood, Pembroke Pines, Miramar, Pompano Beach, Coral Springs, Davie, Sunrise, Plantation, West Palm Beach, Boca Raton, Boynton Beach, Delray Beach, Jupiter, Wellington, Palm Beach Gardens).
- **Central Florida:** Orange, Osceola, Seminole, Hillsborough, Pinellas, Polk counties + major cities (Orlando, Kissimmee, Sanford, Altamonte Springs, Winter Park, Apopka, Tampa, St. Petersburg, Clearwater, Brandon-area/unincorporated Hillsborough, Lakeland, Winter Haven).
- Coverage is platform-driven: any source on a supported platform is included tonight; unsupported portals are recorded in a coverage report for follow-up.

## Data sources

1. **Meeting agenda platforms** (planning/zoning boards, city commissions, county commissions):
   - Legistar (free JSON API at `webapi.legistar.com/v1/<client>`)
   - Granicus / IQM2 (e.g., `miamifl.iqm2.com` — RSS + HTML meeting/agenda pages)
   - CivicClerk
   - Municode Meetings
   - NovusAgenda
2. **County development-application pages** — county planning/zoning "current applications" or development trackers (e.g., Miami-Dade, Broward, Palm Beach, Orange, Hillsborough) where they exist and are parseable. Per-county custom connectors; best-effort tonight, logged in coverage report otherwise.

**Time window:** agenda items from the last ~6 months plus all scheduled/upcoming meetings.

## Architecture

```
sources.json (registry: name, county, platform, url, geo bias)
        │
scraper/ (Python 3.13, stdlib + requests + beautifulsoup4)
  connectors/legistar.py, iqm2.py, civicclerk.py, municode.py, novus.py, county_custom.py
        │  → raw agenda items (title, body, meeting, date, link)
filter.py     — development-item keyword filter + project-type classifier + multifamily flag
extract.py    — street address / parcel-folio / project-name extraction
geocode.py    — US Census batch geocoder → Nominatim fallback; persistent cache (geocache.json)
build.py      — emits site/data/projects.geojson + unmapped.json + coverage.json
        │
site/ (static: index.html, MapLibre GL or Leaflet + markercluster, no build step)
        │
refresh.sh    — scrape → geocode → build → git commit → push (GitHub Pages redeploys)
```

## Classification

- **Development filter keywords:** rezoning, zoning change, land use amendment, FLUM, comprehensive plan amendment, site plan, plat, replat, variance, special exception, conditional use, PUD, development agreement, development order, MUSP, special area plan, annexation, density.
- **Multifamily flag (the lens):** multifamily, apartment, residential units, du/ac, dwelling units, townhome, condominium, mixed-use, affordable housing, workforce housing, Live Local, senior living, TOD/transit-oriented. Multifamily items get distinct pin styling and a default-on filter emphasis.
- Each item: `{id, source, jurisdiction, county, meeting_body, meeting_date, title, summary, link, project_type, multifamily: bool, address, parcel, lat, lon, status(upcoming|heard)}`

## Map UI (Morgan Group quality bar)

- Clustered pins, colored by project type; multifamily items visually distinct (larger/branded accent color).
- Filters: county, city, project type, multifamily-only toggle, date range (upcoming vs. recent).
- Search box (project text/address).
- Popup: project title, jurisdiction, hearing date + body, classification chips, and a link to the source agenda item / application record.
- "Unmapped items" panel listing development items with no extractable address (no fake pins).
- Coverage panel/badge: which sources were scraped, item counts, which failed — transparency instead of silent gaps.
- Clean professional styling, Morgan Group name in header.

## Delivery & growth

- **Hosting:** GitHub Pages on a new repo under `AviParmar21234` (gh CLI already authenticated). Public repo (data is public record).
- **Refresh:** `./refresh.sh` — one command; re-scrapes all sources, geocodes only new/uncached addresses, rebuilds GeoJSON, commits and pushes; live site updates in ~1 min.
- **Growth:** new city/county = one entry in `sources.json` (if platform supported) or a new connector module.

## Error handling

- Per-source isolation: one broken portal never kills the run; failures recorded in coverage.json and shown in UI.
- Geocode failures → unmapped list, never guessed coordinates.
- Polite scraping: request delays, timeouts, retries, custom User-Agent; Census batch API for geocoding volume.

## Testing / acceptance (tonight)

- Miami IQM2 connector verified end-to-end against real agendas (known items appear with correct links).
- Legistar connector verified on ≥2 clients.
- Map loads on GitHub Pages URL, filters work, popups link to real agenda items.
- Coverage report shows ≥ 25 sources attempted with per-source counts.
- `./refresh.sh` run twice is idempotent (no duplicates).

## Out of scope (tonight)

- Scheduled auto-updates (phase 2), paid data feeds (CoStar etc.), manual deal entry, login/auth, historical archive beyond ~6 months, oddball custom city portals.
