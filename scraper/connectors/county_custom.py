"""County-specific development trackers (non-agenda platforms).

Dispatches on source["id"]:
  - hillsborough-dev-tracker: ArcGIS FeatureServer of DSD zoning hearing cases.
  - broward-dev-tracker: SharePoint page with Local Planning Agency application tables.

Exposes fetch(source) -> list[RawItem] (connector contract) and
fetch_with_coords(source) -> list[(RawItem, (lat, lon) | None)] so the pipeline
can skip geocoding when a record carries its own geometry.
"""
import math
import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper import http
from scraper.connectors.base import RawItem

# --- Hillsborough (ArcGIS FeatureServer) -------------------------------------

HILLS_LINK = "https://experience.arcgis.com/experience/870491f64f9744dca53c9f54ed4b7407"
HILLS_MEETING_BODY = "Hillsborough DSD Zoning Hearing"
HILLS_PAGE_SIZE = 2000
HILLS_MAX_PAGES = 10
LOOKBACK_DAYS = 180
LOOKAHEAD_DAYS = 365

TYPE_NAMES = {
    "VAR": "Variance",
    "RZ": "Rezoning",
    "RZ-STD": "Standard Rezoning",
    "RZ-PD": "Planned Development Rezoning",
    "SU": "Special Use",
    "SU-AB": "Special Use",
    "SU-GEN": "Special Use",
    "SU-LE": "Special Use",
    "MM": "Minor Modification",
}

HEARING_DATE_FIELDS = ("ZHM_Date", "LUHO_Date", "BOCC_Date")


def _epoch_ms_to_date(ms) -> date | None:
    if not isinstance(ms, (int, float)):
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date()


def _coords_from_geometry(geometry, wkid) -> tuple[float, float] | None:
    """Return (lat, lon) WGS84 from an esri point geometry, or None."""
    if not geometry or "x" not in geometry or "y" not in geometry:
        return None
    x, y = geometry["x"], geometry["y"]
    if wkid == 4326:
        return (y, x)
    if wkid in (102100, 3857):  # Web Mercator -> WGS84
        lon = x / 6378137.0 * (180.0 / math.pi)
        lat = (2 * math.atan(math.exp(y / 6378137.0)) - math.pi / 2) * (180.0 / math.pi)
        return (lat, lon)
    return None  # unknown projected CRS; don't guess


def parse_hillsborough(source: dict, pages: list[dict],
                       today: date | None = None) -> list[tuple[RawItem, tuple[float, float] | None]]:
    """Pure mapping from ArcGIS query JSON pages to (RawItem, coords) pairs."""
    today = today or date.today()
    low = today - timedelta(days=LOOKBACK_DAYS)
    high = today + timedelta(days=LOOKAHEAD_DAYS)
    out: list[tuple[RawItem, tuple[float, float] | None]] = []
    for page in pages:
        wkid = ((page.get("spatialReference") or {}).get("latestWkid")
                or (page.get("spatialReference") or {}).get("wkid"))
        for feat in page.get("features", []):
            attrs = feat.get("attributes") or {}
            if attrs.get("Inactive"):
                continue
            hearing_dates = [d for f in HEARING_DATE_FIELDS
                             if (d := _epoch_ms_to_date(attrs.get(f))) is not None]
            in_window = sorted(d for d in hearing_dates if low <= d <= high)
            if not in_window:
                continue
            upcoming = [d for d in in_window if d >= today]
            meeting_date = upcoming[0] if upcoming else in_window[-1]

            type_code = (attrs.get("Type_") or "").strip()
            app_num = (attrs.get("AppNum") or "").strip()
            type_name = TYPE_NAMES.get(type_code)
            title = f"Zoning application {type_code} {app_num}".strip()
            if type_name:
                title += f" ({type_name})"

            folio = (attrs.get("FolioNumb") or "").strip()
            item = RawItem(
                source_id=source["id"],
                jurisdiction=source["name"],
                county=source["county"],
                meeting_body=HILLS_MEETING_BODY,
                meeting_date=meeting_date.isoformat(),
                title=title,
                body_text=f"Folio {folio}" if folio else "",
                link=HILLS_LINK,
            )
            out.append((item, _coords_from_geometry(feat.get("geometry"), wkid)))
    return out


def _fetch_hillsborough_pages(url: str) -> list[dict]:
    pages: list[dict] = []
    offset = 0
    for _ in range(HILLS_MAX_PAGES):
        params = {
            "where": "1=1",
            "outFields": "*",
            "f": "json",
            "outSR": "4326",  # server reprojects to WGS84 lat/lon
            "resultRecordCount": str(HILLS_PAGE_SIZE),
            "resultOffset": str(offset),
        }
        page = http.get(url, params=params).json()
        if page.get("error"):
            raise RuntimeError(f"ArcGIS error: {page['error']}")
        feats = page.get("features", [])
        pages.append(page)
        offset += len(feats)
        if not feats or not page.get("exceededTransferLimit"):
            break
    return pages


# --- Broward (LPA SharePoint page) --------------------------------------------

BROWARD_MEETING_BODY = "Broward County Local Planning Agency"
_ZWSP_RE = re.compile("[​‌‍‎‏﻿]")  # zero-width chars in the CMS markup


def _clean(text: str) -> str:
    return " ".join(_ZWSP_RE.sub("", text).replace("\xa0", " ").split())


def _parse_us_date(text: str) -> str:
    """'9/10/25' or '4/10/2024' -> ISO date string, else ''."""
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{2,4})$", text.strip())
    if not m:
        return ""
    month, day, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if year < 100:
        year += 2000
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return ""


def _app_year(number: str, iso_date: str) -> int | None:
    """Application year from number like '25-Z2' / '1-Z-22', else hearing date."""
    m = re.match(r"^(\d{2})-", number)
    if m:
        return 2000 + int(m.group(1))
    m = re.search(r"-(\d{2})$", number)
    if m:
        return 2000 + int(m.group(1))
    if iso_date:
        return int(iso_date[:4])
    return None


def _row_link(row, page_url: str) -> str:
    anchors = [a for a in row.find_all("a", href=True) if a["href"].strip()]
    for wanted in ("staff report", "application"):
        for a in anchors:
            if wanted in _clean(a.get_text()).lower():
                return urljoin(page_url, a["href"])
    for a in anchors:
        if ".pdf" in a["href"].lower():
            return urljoin(page_url, a["href"])
    return page_url


def parse_broward(source: dict, html: str,
                  today: date | None = None) -> list[tuple[RawItem, None]]:
    """Pure parse of the LPA page: application rows for current + previous year."""
    today = today or date.today()
    keep_years = {today.year, today.year - 1}
    page_url = source["url"]
    soup = BeautifulSoup(html, "html.parser")
    out: list[tuple[RawItem, None]] = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        header = [_clean(c.get_text(" ", strip=True)).upper()
                  for c in rows[0].find_all(["th", "td"])]
        if "NUMBER" not in header or not any("HEARING" in h for h in header):
            continue  # meeting-schedule table, not an applications table
        for row in rows[1:]:
            cells = [_clean(c.get_text(" ", strip=True)) for c in row.find_all(["th", "td"])]
            if len(cells) < 5 or not cells[2]:
                continue
            name, app_type, number, hearing, status = cells[:5]
            meeting_date = _parse_us_date(hearing)
            year = _app_year(number, meeting_date)
            if year is None or year not in keep_years:
                continue
            item = RawItem(
                source_id=source["id"],
                jurisdiction=source["name"],
                county=source["county"],
                meeting_body=BROWARD_MEETING_BODY,
                meeting_date=meeting_date,
                title=f"{app_type} {number}: {name}",
                body_text=status,
                link=_row_link(row, page_url),
            )
            out.append((item, None))
    return out


# --- Dispatch ------------------------------------------------------------------


def fetch_with_coords(source: dict) -> list[tuple[RawItem, tuple[float, float] | None]]:
    sid = source["id"]
    if sid == "hillsborough-dev-tracker":
        return parse_hillsborough(source, _fetch_hillsborough_pages(source["url"]))
    if sid == "broward-dev-tracker":
        return parse_broward(source, http.get(source["url"]).text)
    raise ValueError(f"county_custom: unknown source id {sid!r}")


def fetch(source: dict) -> list[RawItem]:
    return [item for item, _coords in fetch_with_coords(source)]
