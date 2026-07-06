"""Turn classified items into site/data outputs: projects.geojson, unmapped.json, coverage.json, meta.json."""
import hashlib
import json
import os
import re
from collections import Counter
from datetime import date, datetime, timezone

_HEADER_TITLE_RE = re.compile(
    r"^(new business|old business|unfinished business|information:?|consent( agenda)?:?|"
    r"discussion( items?)?:?|public hearings?:?|[\w' ]{0,20}report'?s?:?)$", re.I)


def polish(items: list[dict]) -> None:
    """Fix low-information items in place.

    1. Items whose title is a bare section header ("NEW BUSINESS") get their
       real text promoted from the summary/agenda-note field.
    2. Venue addresses (the same address on >=40% and >=3 of a source's items
       is almost certainly the meeting location, not a project site) are
       dropped so items don't produce misleading pins at city hall.
    """
    for it in items:
        t = (it.get("title") or "").strip()
        if len(t) < 40 and _HEADER_TITLE_RE.match(t) and (it.get("summary") or "").strip():
            it["title"] = it["summary"][:300]
    by_src: dict[str, list[dict]] = {}
    for it in items:
        by_src.setdefault(it["source"], []).append(it)
    for its in by_src.values():
        counts = Counter(i["address"] for i in its if i.get("address"))
        total = sum(counts.values())
        for addr, n in counts.items():
            if n >= 3 and n / total >= 0.4:
                for i in its:
                    if i.get("address") == addr:
                        i["address"] = None
                        if not i.get("parcel"):
                            i["lat"] = i["lon"] = None

SCHEMA_KEYS = ["id", "source", "jurisdiction", "county", "meeting_body", "meeting_date",
               "title", "summary", "plain", "link", "project_type", "multifamily", "address",
               "parcel", "lat", "lon", "status", "first_seen", "units", "acres", "score"]

_TYPE_LABELS = {
    "rezoning": "Rezoning", "land-use": "Land-use change", "site-plan": "Site plan",
    "pud": "Planned development (PUD)", "plat": "Plat / subdivision", "variance": "Variance",
    "special-exception": "Special exception", "development-agreement": "Development agreement",
    "annexation": "Annexation", "other-development": "Development item",
}
_JURIS_PREFIX = re.compile(r"^(City of|Town of|Village of)\s+", re.I)


def plain_summary(it: dict) -> str:
    """One-line developer-friendly description built from extracted facts."""
    label = _TYPE_LABELS.get(it.get("project_type"), "Development item")
    lead = f"Multifamily {label[0].lower()}{label[1:]}" if it.get("multifamily") else label
    facts = []
    if it.get("units"):
        facts.append(f"{it['units']} units")
    if it.get("acres"):
        acres = it["acres"]
        facts.append(f"{acres:g} ac")
    if it.get("address"):
        loc = f"at {it['address']}"
    elif it.get("parcel"):
        loc = f"parcel {it['parcel']}"
    else:
        loc = "location not stated in item"
    place = _JURIS_PREFIX.sub("", it.get("jurisdiction") or "").strip()
    head = lead + (" · " + " · ".join(facts) if facts else "")
    return f"{head} — {loc}, {place}"


def load_first_seen(out_dir: str) -> dict:
    """Map of item id -> first_seen date from the previous build's outputs."""
    seen: dict[str, str] = {}
    for fname in ("projects.geojson", "unmapped.json"):
        path = os.path.join(out_dir, fname)
        if not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception:
            continue
        records = [ft["properties"] for ft in data.get("features", [])] if isinstance(data, dict) else data
        for rec in records:
            if rec.get("id") and rec.get("first_seen"):
                seen[rec["id"]] = rec["first_seen"]
    return seen


def item_id(source_id: str, link: str, title: str) -> str:
    return hashlib.sha1(f"{source_id}|{link}|{title}".encode()).hexdigest()[:16]


def finalize(items: list[dict], today: str | None = None, first_seen: dict | None = None) -> list[dict]:
    """Dedup by id, set status and first_seen, clip to schema keys."""
    today = today or date.today().isoformat()
    first_seen = first_seen or {}
    seen, out = set(), []
    for it in items:
        iid = item_id(it["source"], it["link"], it["title"])
        if iid in seen:
            continue
        seen.add(iid)
        it["id"] = iid
        it["status"] = "upcoming" if (it.get("meeting_date") or "") >= today else "heard"
        it["first_seen"] = first_seen.get(iid, today)
        it["plain"] = plain_summary(it)
        out.append({k: it.get(k) for k in SCHEMA_KEYS})
    return out


def write_outputs(items: list[dict], coverage: list[dict], out_dir: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    mapped = [it for it in items if it.get("lat") is not None and it.get("lon") is not None]
    unmapped = [it for it in items if it not in mapped]

    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature",
         "geometry": {"type": "Point", "coordinates": [it["lon"], it["lat"]]},
         "properties": {k: v for k, v in it.items() if k not in ("lat", "lon")}}
        for it in mapped
    ]}
    with open(os.path.join(out_dir, "projects.geojson"), "w") as f:
        json.dump(fc, f)
    with open(os.path.join(out_dir, "unmapped.json"), "w") as f:
        json.dump(unmapped, f)
    with open(os.path.join(out_dir, "coverage.json"), "w") as f:
        json.dump(coverage, f, indent=1)
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "totals": {
            "sources_attempted": len(coverage),
            "sources_ok": sum(1 for c in coverage if c.get("ok")),
            "projects_mapped": len(mapped),
            "projects_unmapped": len(unmapped),
            "multifamily": sum(1 for it in items if it.get("multifamily")),
        },
    }
    with open(os.path.join(out_dir, "meta.json"), "w") as f:
        json.dump(meta, f, indent=1)
    return meta
