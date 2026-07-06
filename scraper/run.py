"""Pipeline runner: scrape all enabled sources -> filter -> extract -> geocode -> build.

Usage: python -m scraper.run [--source ID] [--dry-run] [--max-events N]
"""
import argparse
import importlib
import json
import re
import sys
import traceback

from scraper.build import finalize, load_first_seen, write_outputs
from scraper.extract import extract_intel, extract_location, opportunity_score
from scraper.filter import classify
from scraper.geocode import geocode_all

ENRICH_CAP = 40  # max detail-page fetches per source for items missing a location

CONNECTORS = {
    "legistar": "scraper.connectors.legistar",
    "iqm2": "scraper.connectors.iqm2",
    "civicclerk": "scraper.connectors.civicclerk",
    "novus": "scraper.connectors.novus",
    "county_custom": "scraper.connectors.county_custom",
    "granicus_mm": "scraper.connectors.granicus_mm",
    "civicplus": "scraper.connectors.civicplus",
    "onbase": "scraper.connectors.onbase",
    "escribe": "scraper.connectors.escribe",
    "primegov": "scraper.connectors.primegov",
}

_JURIS_PREFIX_RE = re.compile(r"^(City of|Town of|Village of)\s+", re.I)


def city_hint(jurisdiction: str) -> str:
    name = _JURIS_PREFIX_RE.sub("", jurisdiction).strip()
    if name.lower().endswith("county") or "applications" in name.lower():
        return ""
    return name


def scrape_source(source: dict) -> tuple[list[dict], dict]:
    """Return (classified item dicts, coverage entry)."""
    cov = {"source_id": source["id"], "name": source["name"], "county": source["county"],
           "ok": False, "items_raw": 0, "items_dev": 0, "error": None}
    items: list[dict] = []
    try:
        mod = importlib.import_module(CONNECTORS[source["platform"]])
        if hasattr(mod, "fetch_with_coords"):
            pairs = mod.fetch_with_coords(source)
        else:
            pairs = [(ri, None) for ri in mod.fetch(source)]
        cov["items_raw"] = len(pairs)
        enrich = getattr(mod, "fetch_detail", None)
        enriched = 0
        for ri, coords in pairs:
            cls = classify(ri.title, ri.body_text)
            if not cls:
                continue
            text = f"{ri.title} {ri.body_text}"
            loc = extract_location(text)
            intel = extract_intel(text)
            summary = (ri.body_text or "")[:400]
            if enrich and not loc["address"] and not loc["parcel"] and not coords and enriched < ENRICH_CAP:
                enriched += 1
                detail = enrich(ri.link)
                if detail:
                    loc = extract_location(detail)
                    more = extract_intel(detail)
                    intel = {k: intel[k] or more[k] for k in intel}
                    if not summary:
                        summary = detail[:400]
            it = {
                "source": ri.source_id, "jurisdiction": ri.jurisdiction, "county": ri.county,
                "meeting_body": ri.meeting_body, "meeting_date": ri.meeting_date,
                "title": ri.title[:400], "summary": summary,
                "link": ri.link, "project_type": cls["project_type"],
                "multifamily": cls["multifamily"], "address": loc["address"],
                "parcel": loc["parcel"], "lat": None, "lon": None,
                "units": intel["units"], "acres": intel["acres"],
                "city_hint": city_hint(ri.jurisdiction),
            }
            if coords:
                it["lat"], it["lon"] = coords
            items.append(it)
        cov["items_dev"] = len(items)
        cov["ok"] = True
    except Exception as e:
        cov["error"] = f"{type(e).__name__}: {e}"
        traceback.print_exc(limit=1)
    return items, cov


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", help="only run this source id")
    ap.add_argument("--dry-run", action="store_true", help="scrape+classify but skip geocode/build")
    ap.add_argument("--sources-file", default="sources.json")
    ap.add_argument("--out-dir", default="site/data")
    args = ap.parse_args(argv)

    with open(args.sources_file) as f:
        sources = json.load(f)
    targets = [s for s in sources if s.get("enabled") and (not args.source or s["id"] == args.source)]

    all_items, coverage = [], []
    for src in targets:
        print(f"[{src['id']}] scraping ({src['platform']})...", flush=True)
        items, cov = scrape_source(src)
        print(f"[{src['id']}] raw={cov['items_raw']} dev={cov['items_dev']}"
              + (f" ERROR: {cov['error']}" if cov["error"] else ""), flush=True)
        all_items += items
        coverage.append(cov)

    if args.dry_run:
        print(f"DRY RUN: {len(all_items)} dev items from {len(coverage)} sources")
        return 0

    print(f"geocoding {sum(1 for i in all_items if i['address'] and i['lat'] is None)} addresses...", flush=True)
    geocode_all(all_items)
    try:
        from scraper.parcels import resolve_parcels
        n = sum(1 for i in all_items if i["lat"] is None and i.get("parcel"))
        print(f"resolving {n} parcels via county GIS...", flush=True)
        resolve_parcels(all_items)
    except ImportError:
        pass
    for it in all_items:
        it.pop("city_hint", None)
    final = finalize(all_items, first_seen=load_first_seen(args.out_dir))
    for it in final:
        it["score"] = opportunity_score(it)

    if args.source:
        # single-source run: merge into existing outputs instead of clobbering them
        import json as _json, os as _os
        kept_items, kept_cov = [], []
        scraped_ids = {c["source_id"] for c in coverage}
        gj = _os.path.join(args.out_dir, "projects.geojson")
        um = _os.path.join(args.out_dir, "unmapped.json")
        if _os.path.exists(gj):
            fc = _json.load(open(gj))
            kept_items += [{**f["properties"],
                            "lon": f["geometry"]["coordinates"][0],
                            "lat": f["geometry"]["coordinates"][1]}
                           for f in fc["features"] if f["properties"]["source"] not in scraped_ids]
        if _os.path.exists(um):
            kept_items += [it for it in _json.load(open(um)) if it["source"] not in scraped_ids]
        cv = _os.path.join(args.out_dir, "coverage.json")
        if _os.path.exists(cv):
            kept_cov = [c for c in _json.load(open(cv)) if c["source_id"] not in scraped_ids]
        final = kept_items + final
        coverage = kept_cov + coverage

    meta = write_outputs(final, coverage, args.out_dir)
    print(json.dumps(meta["totals"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
