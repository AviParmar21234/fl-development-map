# Florida Development Opportunity Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A GitHub-Pages-hosted interactive map of development/multifamily opportunities scraped from South + Central Florida municipal agenda portals, refreshed with one command.

**Architecture:** Python scraper with one connector per agenda platform (Legistar API, IQM2/Granicus, CivicClerk, Municode, NovusAgenda) driven by a `sources.json` registry; pure-logic pipeline (filter → extract → geocode → build GeoJSON); static Leaflet site in `site/`; `refresh.sh` re-runs everything and pushes.

**Tech Stack:** Python 3.13 (requests, beautifulsoup4, pytest), Leaflet + markercluster (vendored), US Census geocoder + Nominatim fallback, GitHub Pages.

## Global Constraints

- Python 3.13; deps limited to `requests`, `beautifulsoup4`, `pytest` (venv in `.venv/`).
- Per-source isolation: a connector exception must never abort the run; record in coverage.
- Polite scraping: 0.5s delay between requests per host, 20s timeout, 2 retries, User-Agent `MorganGroupMapBot/1.0 (contact: aviparmar2313@gmail.com)`.
- No guessed coordinates: geocode failure → `unmapped.json`, never a pin.
- All output data written under `site/data/` (projects.geojson, unmapped.json, coverage.json).
- Item schema (exact keys): `id, source, jurisdiction, county, meeting_body, meeting_date, title, summary, link, project_type, multifamily, address, parcel, lat, lon, status`.

---

### Task 1: Scaffold + seed source registry

**Files:**
- Create: `scraper/__init__.py`, `scraper/connectors/__init__.py`, `tests/__init__.py`
- Create: `sources.json`
- Create: `requirements.txt` (`requests`, `beautifulsoup4`, `pytest`)
- Create: `.gitignore` (`.venv/`, `__pycache__/`, `geocache.json.tmp`, `raw_cache/`)

**Interfaces:**
- Produces: `sources.json` — array of `{"id": str, "name": str, "county": str, "state": "FL", "platform": "legistar|iqm2|civicclerk|municode|novus|county_custom", "url": str, "legistar_client": str|null, "enabled": bool}`.

- [ ] **Step 1:** Create venv, install deps, create package dirs and `.gitignore`.
- [ ] **Step 2:** Seed `sources.json` with known-good entries (Miami IQM2 `https://miamifl.iqm2.com`, Miami-Dade Legistar client `miamidade`, plus placeholders `enabled:false` for every target jurisdiction in the spec's geography list).
- [ ] **Step 3:** Commit: `chore: scaffold scraper and seed source registry`.

### Task 2: Source discovery (parallel agents)

**Files:**
- Modify: `sources.json` (verify/flip `enabled`, fill real URLs/platforms)
- Create: `docs/coverage-notes.md` (jurisdictions with unsupported portals)

**Interfaces:**
- Consumes: seeded `sources.json`.
- Produces: verified `sources.json`; every entry either `enabled:true` with a working URL + correct platform, or `enabled:false` with a `note`.

- [ ] **Step 1:** Dispatch parallel research agents (one per county cluster: Miami-Dade cities, Broward cities, Palm Beach cities, Orlando metro, Tampa Bay + Polk) to identify each jurisdiction's agenda platform and base URL. Legistar check: `https://webapi.legistar.com/v1/<client>/Bodies?$top=1` returns JSON 200.
- [ ] **Step 2:** Merge results into `sources.json`; unsupported portals documented in `docs/coverage-notes.md`.
- [ ] **Step 3:** Commit: `feat: verified source registry for SoFla + Central FL`.

### Task 3: Development filter + multifamily classifier (TDD)

**Files:**
- Create: `scraper/filter.py`
- Test: `tests/test_filter.py`

**Interfaces:**
- Produces: `classify(title: str, body: str = "") -> dict | None` — returns `None` if not a development item, else `{"project_type": str, "multifamily": bool}`. `project_type ∈ {"rezoning","land-use","site-plan","plat","variance","special-exception","pud","development-agreement","annexation","other-development"}`.

- [ ] **Step 1: Write failing tests**

```python
from scraper.filter import classify

def test_rezoning_multifamily():
    r = classify("Ordinance: rezoning of 1200 NW 7th Ave to T6-8-O for a 250-unit multifamily development")
    assert r == {"project_type": "rezoning", "multifamily": True}

def test_site_plan_not_mf():
    r = classify("Site plan approval for retail warehouse at 500 Industrial Way")
    assert r["project_type"] == "site-plan" and r["multifamily"] is False

def test_non_development_returns_none():
    assert classify("Approval of minutes of the June 3 meeting") is None
    assert classify("Proclamation honoring Officer Diaz") is None

def test_live_local_flags_mf():
    r = classify("Resolution regarding a Live Local Act application for workforce housing, 91 SW 3rd St")
    assert r is not None and r["multifamily"] is True
```

- [ ] **Step 2:** Run `pytest tests/test_filter.py -v` — expect FAIL (module missing).
- [ ] **Step 3:** Implement keyword-based `classify` per spec keyword lists (dev keywords → type mapping checked in priority order; multifamily keywords as separate boolean; exclusion guard: items matching only minutes/proclamation/appointment boilerplate return None even if a dev word appears incidentally).
- [ ] **Step 4:** Run tests — PASS. Commit `feat: development filter and multifamily classifier`.

### Task 4: Address + parcel extraction (TDD)

**Files:**
- Create: `scraper/extract.py`
- Test: `tests/test_extract.py`

**Interfaces:**
- Produces: `extract_location(text: str) -> dict` — `{"address": str|None, "parcel": str|None}`. Address = first street address matching FL patterns (number + directional? + name + suffix), normalized single-space. Parcel = folio patterns like `01-4137-030-0010` or `30-2029-005-1050`.

- [ ] **Step 1: Write failing tests**

```python
from scraper.extract import extract_location

def test_simple_address():
    assert extract_location("rezoning of property at 1200 NW 7th Avenue, Miami")["address"] == "1200 NW 7th Avenue"

def test_folio():
    assert extract_location("Folio No. 01-4137-030-0010")["parcel"] == "01-4137-030-0010"

def test_no_address():
    r = extract_location("Discussion of the comprehensive plan generally")
    assert r["address"] is None and r["parcel"] is None

def test_address_range_and_suffixes():
    assert extract_location("located at 3500-3520 Biscayne Blvd")["address"] == "3500-3520 Biscayne Blvd"
```

- [ ] **Step 2:** Run — FAIL. **Step 3:** Implement with compiled regexes (street suffixes: St, Street, Ave, Avenue, Blvd, Boulevard, Rd, Road, Dr, Drive, Ct, Court, Ter, Terrace, Way, Pl, Place, Ln, Lane, Trl, Trail, Pkwy, Hwy, Highway; directionals NW/NE/SW/SE/N/S/E/W optional both sides; number may be a range). **Step 4:** PASS. Commit `feat: address and parcel extraction`.

### Task 5: HTTP utility + connector base

**Files:**
- Create: `scraper/http.py`, `scraper/connectors/base.py`
- Test: `tests/test_http.py` (cache-path logic only, no network)

**Interfaces:**
- Produces: `http.get(url, *, params=None) -> requests.Response` (delay/retry/UA per Global Constraints, per-host last-request tracking); `RawItem` dataclass `{source_id, jurisdiction, county, meeting_body, meeting_date (ISO str), title, body_text, link}`; connector contract: module-level `fetch(source: dict) -> list[RawItem]`.

- [ ] Implement + unit-test the retry/delay bookkeeping (mock `requests`), commit `feat: polite http layer and connector contract`.

### Task 6: Legistar connector

**Files:**
- Create: `scraper/connectors/legistar.py`
- Test: `tests/test_legistar.py` (fixture-based: canned JSON), plus live smoke via `python -m scraper.run --source miamidade --dry-run`

**Interfaces:**
- Consumes: `http.get`, `RawItem`.
- Produces: `fetch(source)` hitting `https://webapi.legistar.com/v1/{client}/Events?$filter=EventDate ge datetime'{six_months_ago}'` then `/Events({id})/EventItems?AgendaNote=1&MinutesNote=1` mapping `EventItemTitle`→title, matter link `https://{client}.legistar.com/LegislationDetail.aspx?ID={EventItemMatterId}` when present, else event `EventInSiteURL`.

- [ ] Fixture test for JSON→RawItem mapping; live smoke against 2 clients; commit `feat: legistar connector`.

### Task 7: IQM2/Granicus connector (Miami end-to-end proof)

**Files:**
- Create: `scraper/connectors/iqm2.py`
- Test: `tests/test_iqm2.py` (fixture HTML), live smoke on `miamifl.iqm2.com`

**Interfaces:**
- Produces: `fetch(source)` — parse `Calendar.aspx?From={jan1}&To={dec31}` (current + prior year window as needed) for meeting rows (`Detail_Meeting.aspx?ID=`), fetch each meeting detail, parse agenda item rows (`Detail_LegiFile.aspx?ID=` links + item text) into RawItems with absolute links.

- [ ] Fixture test on saved Miami HTML; live smoke: ≥1 known PZAB/Commission item extracted with working link; commit `feat: iqm2 connector verified on Miami`.

### Task 8: CivicClerk, Municode, Novus connectors

**Files:**
- Create: `scraper/connectors/civicclerk.py` (`https://{site}.api.civicclerk.com/v1/Events` JSON + event files), `scraper/connectors/municode.py` (`https://{client}.municodemeetings.com` HTML list → agenda PDFs/HTML pages; HTML-only parse, PDFs skipped and counted in coverage), `scraper/connectors/novus.py` (`https://{client}.novusagenda.com/agendapublic/` MeetingsList → AgendaWeb items)
- Test: fixture test per connector + live smoke on 1 client each

**Interfaces:** same `fetch(source) -> list[RawItem]` contract.

- [ ] Implement each with fixture test; any platform that proves unparseable tonight → mark its sources `enabled:false` with note, log in coverage-notes; commit per connector.

### Task 9: County development-application pages (best effort)

**Files:**
- Create: `scraper/connectors/county_custom.py` with per-county parser functions keyed by `source["id"]`

**Interfaces:** same `fetch` contract; unsupported counties documented.

- [ ] Attempt Miami-Dade, Broward, Palm Beach, Orange, Hillsborough application/tracker pages; keep whichever parse cleanly within timebox (45 min); commit `feat: county application connectors (best effort)`.

### Task 10: Geocoder with cache (TDD on cache logic)

**Files:**
- Create: `scraper/geocode.py`
- Test: `tests/test_geocode.py` (cache read/write + batch chunking, network mocked)

**Interfaces:**
- Produces: `geocode_all(items: list[dict], cache_path="geocache.json") -> None` — mutates items, sets `lat`/`lon` floats or leaves None. Key = `f"{address}, {jurisdiction}, FL"`. Census batch endpoint `https://geocoding.geo.census.gov/geocoder/locations/addressbatch` (CSV, chunks of 1000); misses retried one-by-one on Nominatim (1 req/s, `format=jsonv2`, viewbox biased to FL). Cache stores misses as `null` to avoid re-querying.

- [ ] TDD cache + chunking; live smoke on 5 real addresses; commit `feat: geocoder with persistent cache`.

### Task 11: Pipeline runner + GeoJSON build (TDD)

**Files:**
- Create: `scraper/run.py` (CLI: `python -m scraper.run [--source ID] [--dry-run]`), `scraper/build.py`
- Test: `tests/test_build.py`

**Interfaces:**
- Consumes: connectors' `fetch`, `classify`, `extract_location`, `geocode_all`.
- Produces: `site/data/projects.geojson` (FeatureCollection, properties = full item schema), `site/data/unmapped.json` (items w/o lat/lon), `site/data/coverage.json` (`[{source_id, name, county, ok, items_raw, items_dev, error}]`), `site/data/meta.json` (`{generated_at, totals}`). Dedup: id = sha1 of `source_id|link|title` — stable across runs (idempotent refresh).

- [ ] TDD build/dedup; run full pipeline on all enabled sources; commit `feat: pipeline and geojson build`.

### Task 12: Map site

**Files:**
- Create: `site/index.html`, `site/app.js`, `site/style.css`, vendored `site/vendor/leaflet*` + markercluster

**Interfaces:**
- Consumes: `site/data/*.json|geojson` exactly as produced by Task 11.
- Produces: the shipped UI per spec: clustered pins colored by `project_type`, multifamily accent styling + default-emphasis toggle, filters (county, city, type, multifamily-only, upcoming/recent by `status`), text search, popups (title, jurisdiction, body, date, chips, source link), unmapped panel, coverage panel, Morgan Group header. Use frontend-design skill for quality bar.

- [ ] Build UI, verify locally with `python3 -m http.server` + preview tools (pins render, filters filter, popup links open real agenda pages); commit `feat: map site`.

### Task 13: Deploy + refresh script + acceptance

**Files:**
- Create: `refresh.sh`, `README.md`
- Create: `.github/workflows/pages.yml` — GitHub Actions workflow that uploads `site/` as the Pages artifact on every push to `main` (keeps the app in `site/` without moving directories).
- Repo: create GitHub repo `fl-development-map` under AviParmar21234 with Pages source = GitHub Actions.

**Interfaces:**
- Produces: `./refresh.sh` = venv python `-m scraper.run` → `git add site/data && git commit && git push` → Action redeploys Pages.

- [ ] Create repo + Actions workflow, push, verify live URL loads with real data.
- [ ] Run `./refresh.sh` twice; verify idempotent (second commit empty / no dup features).
- [ ] Acceptance per spec: Miami end-to-end ✓, ≥2 Legistar clients ✓, ≥25 sources attempted in coverage ✓, filters + popups ✓. Commit `feat: refresh script and pages deploy`.
