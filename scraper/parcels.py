"""Parcel/folio -> lat/lon (WGS84) via county GIS ArcGIS REST endpoints.

Counties are dispatched through COUNTY_LAYERS. Four counties have their own
verified parcel layers (Miami-Dade, Broward, Palm Beach, Pinellas); Orange,
Seminole and Polk go through the FGIO statewide FDOR centroid layer, which is
only fast for indexed PARCEL_ID equality queries. Results are cached in a
persistent JSON file (parcelcache.json) keyed by "{county}|{parcel}", misses
included, mirroring scraper/geocode.py.

Parcel id formats (verified against live data):
- Miami-Dade folio "01-4137-030-0010" -> FOLIO "0141370300010" (13 digits)
- Broward folio "4741-35-01-0090"     -> FOLIO "474135010090" (12 digits)
- Palm Beach PCN "30-42-41-11-06-000-0210" -> PARID (17 digits)
- Pinellas "16-31-31-67608-004-0070"  -> PIN (18 digits)
- Orange "26-23-28-8203-00-380"       -> PARCEL_ID (15 digits)
- Polk "25-30-09-424000-001070"       -> PARCEL_ID (18 digits)
- Seminole "18-21-29-502-0D00-0180"   -> PARCEL_ID (17 chars, may contain letters)
All normalize by stripping non-alphanumerics and uppercasing.
"""
import re

from scraper import http
from scraper.geocode import load_cache, save_cache

# rough Florida bounding box to reject wild results (as in scraper/geocode.py)
FL_BOUNDS = (24.3, -87.7, 31.1, -79.8)  # lat_min, lon_min, lat_max, lon_max

_SAVE_EVERY = 20  # persist cache after this many new lookups

STATEWIDE_URL = (
    "https://services9.arcgis.com/Gh9awoU677aKree0/arcgis/rest/services/"
    "Florida_Statewide_Parcel_Centroid_Version/FeatureServer/0/query"
)

# county -> (query_url, id_field, extra_where or None)
# Only endpoints verified to return geometry for a real parcel id belong here.
COUNTY_LAYERS: dict[str, tuple[str, str, str | None]] = {
    "Miami-Dade": (
        "https://gisweb.miamidade.gov/arcgis/rest/services/CommunityServices/"
        "MD_Parcel/MapServer/1/query",
        "FOLIO", None),
    "Broward": (
        "https://gisweb.bcpa.net/arcgis/rest/services/BCPA_GIS_PROPID/"
        "MapServer/0/query",
        "FOLIO", None),
    "Palm Beach": (
        "https://gis.pbcgov.org/arcgis/rest/services/Parcels/PAO_PARCELS_WM/"
        "FeatureServer/0/query",
        "PARID", None),
    "Pinellas": (
        "https://egis.pinellas.gov/gis/rest/services/AGO/Parcels/"
        "MapServer/0/query",
        "PIN", None),
    "Orange": (STATEWIDE_URL, "PARCEL_ID", "CO_NO=58"),
    "Polk": (STATEWIDE_URL, "PARCEL_ID", "CO_NO=63"),
    "Seminole": (STATEWIDE_URL, "PARCEL_ID", "CO_NO=69"),
}

_ID_RE = re.compile(r"^[0-9A-Z]{5,25}$")


def normalize_parcel(parcel: str) -> str | None:
    """Strip separators/whitespace, uppercase. None if result is not a sane id."""
    norm = re.sub(r"[^0-9A-Za-z]", "", parcel or "").upper()
    return norm if _ID_RE.match(norm) else None


def county_config(county: str):
    """Look up COUNTY_LAYERS tolerantly ('Miami-Dade County', 'broward', ...)."""
    name = re.sub(r"\s+county$", "", (county or "").strip(), flags=re.IGNORECASE)
    for key, cfg in COUNTY_LAYERS.items():
        if key.lower() == name.lower():
            return cfg
    return None


def polygon_centroid(rings: list) -> tuple[float, float] | None:
    """(lat, lon) area centroid of the first ring; vertex mean if degenerate."""
    if not rings or not rings[0]:
        return None
    pts = rings[0]
    a = cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        cross = x1 * y2 - x2 * y1
        a += cross
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    if abs(a) > 1e-12:
        return cy / (3 * a), cx / (3 * a)  # (lat, lon)
    lon = sum(p[0] for p in pts) / len(pts)
    lat = sum(p[1] for p in pts) / len(pts)
    return lat, lon


def feature_latlon(feature: dict) -> tuple[float, float] | None:
    """Extract (lat, lon) from an ArcGIS feature (point or polygon, SR 4326)."""
    geom = feature.get("geometry") or {}
    if "x" in geom and "y" in geom:
        return geom["y"], geom["x"]
    return polygon_centroid(geom.get("rings") or [])


def _in_florida(lat: float, lon: float) -> bool:
    return FL_BOUNDS[0] <= lat <= FL_BOUNDS[2] and FL_BOUNDS[1] <= lon <= FL_BOUNDS[3]


def _fetch(county: str, parcel_norm: str) -> tuple[float, float] | None:
    """Query the county's parcel layer for one normalized id. None on any miss."""
    cfg = county_config(county)
    if cfg is None:
        return None
    url, field, extra = cfg
    where = f"{field}='{parcel_norm}'"  # parcel_norm is alnum-only (see _ID_RE)
    if extra:
        where += f" AND {extra}"
    resp = http.get(url, params={
        "f": "json",
        "where": where,
        # no outFields: only geometry is needed, and some servers (Pinellas)
        # reject unqualified field names in outFields
        "outFields": "",
        "returnGeometry": "true",
        "outSR": "4326",
        "resultRecordCount": "1",
    })
    data = resp.json()
    if "error" in data:
        return None
    feats = data.get("features") or []
    if not feats:
        return None
    coords = feature_latlon(feats[0])
    if coords and _in_florida(*coords):
        return coords
    return None


def resolve_parcels(items: list[dict], cache_path: str = "parcelcache.json") -> None:
    """Set item['lat']/item['lon'] from item['parcel'] where possible.

    Only touches items that have a parcel and lack lat/lon. Counties without a
    verified endpoint are skipped. Per-item failures never raise. Results
    (including misses) persist in a JSON cache keyed by "{county}|{parcel}".
    """
    cache = load_cache(cache_path)
    dirty = 0
    try:
        for it in items:
            if it.get("lat") is not None and it.get("lon") is not None:
                continue
            parcel = it.get("parcel")
            county = it.get("county") or ""
            if not parcel or county_config(county) is None:
                continue
            key = f"{county}|{parcel}"
            if key not in cache:
                parcel_norm = normalize_parcel(parcel)
                if parcel_norm is None:
                    coords = None
                else:
                    try:
                        coords = _fetch(county, parcel_norm)
                    except Exception:
                        coords = None
                cache[key] = list(coords) if coords else None
                dirty += 1
                if dirty % _SAVE_EVERY == 0:
                    save_cache(cache_path, cache)
            if cache.get(key):
                it["lat"], it["lon"] = cache[key]
    finally:
        if dirty:
            save_cache(cache_path, cache)
