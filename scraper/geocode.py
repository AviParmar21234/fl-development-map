"""Geocoding: US Census batch first, Nominatim fallback, persistent JSON cache."""
import csv
import io
import json
import os
import time

import requests

from scraper.http import USER_AGENT

CENSUS_BATCH_URL = "https://geocoding.geo.census.gov/geocoder/locations/addressbatch"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
BATCH_SIZE = 1000
# rough Florida bounding box to reject wild geocodes
FL_BOUNDS = (24.3, -87.7, 31.1, -79.8)  # lat_min, lon_min, lat_max, lon_max


def load_cache(path: str) -> dict:
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def save_cache(path: str, cache: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cache, f, indent=0, sort_keys=True)
    os.replace(tmp, path)


def _in_florida(lat: float, lon: float) -> bool:
    return FL_BOUNDS[0] <= lat <= FL_BOUNDS[2] and FL_BOUNDS[1] <= lon <= FL_BOUNDS[3]


def build_batch_csv(rows: list[tuple[str, str, str]]) -> str:
    """rows: [(key, street, city)] -> census batch CSV (id,street,city,state,zip)."""
    out = []
    for i, (_key, street, city) in enumerate(rows, start=1):
        out.append(f'{i},"{street}","{city}","FL",""')
    return "\n".join(out) + "\n"


def parse_census_response(body: str) -> dict:
    """Return {input_id: (lat, lon) | None} from census batch CSV response."""
    out: dict[str, tuple | None] = {}
    for row in csv.reader(io.StringIO(body)):
        if not row:
            continue
        rid = row[0]
        if len(row) >= 6 and row[2] == "Match" and row[5]:
            lon_s, lat_s = row[5].split(",")
            out[rid] = (float(lat_s), float(lon_s))
        else:
            out[rid] = None
    return out


def _census_batch(rows: list[tuple[str, str, str]]) -> dict:
    """rows: [(key, street, city)] -> {key: (lat, lon) | None}."""
    csv_text = build_batch_csv(rows)
    files = {"addressFile": ("addresses.csv", csv_text, "text/csv")}
    data = {"benchmark": "Public_AR_Current"}
    resp = requests.post(CENSUS_BATCH_URL, files=files, data=data, timeout=120,
                         headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    by_id = parse_census_response(resp.text)
    return {rows[int(rid) - 1][0]: coords for rid, coords in by_id.items()}


def _nominatim_one(street: str, city: str):
    time.sleep(1.1)  # Nominatim usage policy: max 1 req/s
    try:
        resp = requests.get(NOMINATIM_URL, params={
            "street": street, "city": city, "state": "Florida",
            "country": "USA", "format": "jsonv2", "limit": 1,
        }, headers={"User-Agent": USER_AGENT}, timeout=30)
        resp.raise_for_status()
        hits = resp.json()
        if hits:
            lat, lon = float(hits[0]["lat"]), float(hits[0]["lon"])
            if _in_florida(lat, lon):
                return (lat, lon)
    except Exception:
        pass
    return None


def geocode_all(items: list[dict], cache_path: str = "geocache.json") -> None:
    """Set lat/lon on items (dicts with address, city_hint). Cache hits skip network."""
    cache = load_cache(cache_path)
    pending: dict[str, tuple[str, str]] = {}
    for it in items:
        if not it.get("address"):
            continue
        city = it.get("city_hint") or ""
        key = f"{it['address']}, {city}, FL"
        it["_geokey"] = key
        if key not in cache:
            pending[key] = (it["address"], city)

    keys = list(pending.keys())
    for i in range(0, len(keys), BATCH_SIZE):
        chunk = [(k, pending[k][0], pending[k][1]) for k in keys[i:i + BATCH_SIZE]]
        try:
            results = _census_batch(chunk)
        except Exception:
            results = {k: None for k, _, _ in chunk}
        for k, coords in results.items():
            if coords and not _in_florida(*coords):
                coords = None
            cache[k] = list(coords) if coords else None
        save_cache(cache_path, cache)

    # Nominatim fallback for census misses (bounded to avoid very long runs)
    misses = [k for k in keys if cache.get(k) is None]
    for k in misses[:150]:
        street, city = pending[k]
        coords = _nominatim_one(street, city)
        cache[k] = list(coords) if coords else None
    save_cache(cache_path, cache)

    for it in items:
        key = it.pop("_geokey", None)
        if key and cache.get(key):
            it["lat"], it["lon"] = cache[key]
