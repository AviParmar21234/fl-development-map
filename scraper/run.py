"""Pipeline runner: scrape all enabled sources -> filter -> extract -> geocode -> build.

Usage: python -m scraper.run [--source ID] [--dry-run] [--max-events N]
"""
import argparse
import importlib
import json
import re
import sys
import traceback

from scraper.build import finalize, write_outputs
from scraper.extract import extract_location
from scraper.filter import classify
from scraper.geocode import geocode_all

CONNECTORS = {
    "legistar": "scraper.connectors.legistar",
    "iqm2": "scraper.connectors.iqm2",
    "civicclerk": "scraper.connectors.civicclerk",
    "novus": "scraper.connectors.novus",
    "county_custom": "scraper.connectors.county_custom",
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
        for ri, coords in pairs:
            cls = classify(ri.title, ri.body_text)
            if not cls:
                continue
            loc = extract_location(f"{ri.title} {ri.body_text}")
            it = {
                "source": ri.source_id, "jurisdiction": ri.jurisdiction, "county": ri.county,
                "meeting_body": ri.meeting_body, "meeting_date": ri.meeting_date,
                "title": ri.title[:400], "summary": (ri.body_text or "")[:400],
                "link": ri.link, "project_type": cls["project_type"],
                "multifamily": cls["multifamily"], "address": loc["address"],
                "parcel": loc["parcel"], "lat": None, "lon": None,
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
    for it in all_items:
        it.pop("city_hint", None)
    final = finalize(all_items)
    meta = write_outputs(final, coverage, args.out_dir)
    print(json.dumps(meta["totals"], indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
