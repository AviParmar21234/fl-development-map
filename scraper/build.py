"""Turn classified items into site/data outputs: projects.geojson, unmapped.json, coverage.json, meta.json."""
import hashlib
import json
import os
from datetime import date, datetime, timezone

SCHEMA_KEYS = ["id", "source", "jurisdiction", "county", "meeting_body", "meeting_date",
               "title", "summary", "link", "project_type", "multifamily", "address",
               "parcel", "lat", "lon", "status"]


def item_id(source_id: str, link: str, title: str) -> str:
    return hashlib.sha1(f"{source_id}|{link}|{title}".encode()).hexdigest()[:16]


def finalize(items: list[dict], today: str | None = None) -> list[dict]:
    """Dedup by id, set status, clip to schema keys."""
    today = today or date.today().isoformat()
    seen, out = set(), []
    for it in items:
        iid = item_id(it["source"], it["link"], it["title"])
        if iid in seen:
            continue
        seen.add(iid)
        it["id"] = iid
        it["status"] = "upcoming" if (it.get("meeting_date") or "") >= today else "heard"
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
