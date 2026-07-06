"""Street-address and parcel/folio extraction from agenda item text."""
import re

_SUFFIXES = (
    r"Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|Drive|Dr|Court|Ct|Terrace|Ter|"
    r"Way|Place|Pl|Lane|Ln|Trail|Trl|Parkway|Pkwy|Circle|Cir|Highway|Hwy"
)
_DIR = r"(?:NE|NW|SE|SW|N|S|E|W|North|South|East|West)"

# number (or range), optional directional, street name words (incl. ordinals like 7th), suffix
_ADDR_RE = re.compile(
    rf"\b(\d{{1,6}}(?:-\d{{1,6}})?)\s+"
    rf"((?:{_DIR}\.?\s+)?"
    rf"(?:US\s+)?"
    rf"(?:[A-Z0-9][A-Za-z0-9']*\s+){{0,4}}?"
    rf"(?:{_SUFFIXES})\b\.?"
    rf"(?:\s+{_DIR}\b)?"
    rf"(?:\s+\d{{1,4}}\b)?)",
    re.IGNORECASE,
)

# FL folio/parcel formats: 01-4137-030-0010, 30-2029-005-1050, and long digit runs with dashes
_PARCEL_RE = re.compile(r"\b(\d{2}-\d{4}-\d{3}-\d{4}|\d{2}-\d{2}-\d{2}-\d{2,}-\d{3,}-\d{3,})\b")

_WS_RE = re.compile(r"\s+")


_UNITS_RE = re.compile(r"\b(\d{1,4})\s*[- ]?\s*(?:unit|dwelling unit|residential unit|du\b|apartment(?:s| unit)|townho(?:me|use))", re.I)
_ACRES_RE = re.compile(r"\b(\d{1,4}(?:\.\d{1,3})?)\s*[±+/-]*\s*[- ]?acres?\b", re.I)
_APPLICANT_RE = re.compile(
    r"(?:applicant|applied for by|on behalf of|submitted by)[,:\s]+([A-Z][A-Za-z0-9 .,&'\-]{2,60}?(?:LLC|L\.L\.C\.|Inc\.?|Corp\.?|Company|LP|LLLP|Ltd\.?|Trust|Partners(?:hip)?))",
    re.I,
)


def extract_intel(text: str) -> dict:
    """Pull unit count, acreage, applicant entity from item text."""
    um = _UNITS_RE.search(text or "")
    am = _ACRES_RE.search(text or "")
    pm = _APPLICANT_RE.search(text or "")
    return {
        "units": int(um.group(1)) if um else None,
        "acres": float(am.group(1)) if am else None,
        "applicant": pm.group(1).strip().rstrip(".,") if pm else None,
    }


def opportunity_score(item: dict) -> int:
    """0-8 heuristic: how interesting is this to a multifamily developer."""
    s = 0
    if item.get("multifamily"):
        s += 3
    units = item.get("units") or 0
    if units >= 100:
        s += 2
    elif units >= 25:
        s += 1
    if item.get("project_type") in ("rezoning", "pud", "land-use"):
        s += 1
    if item.get("status") == "upcoming":
        s += 1
    if (item.get("acres") or 0) >= 2:
        s += 1
    return s


def extract_location(text: str) -> dict:
    """Return {"address": str|None, "parcel": str|None} from free text."""
    address = None
    m = _ADDR_RE.search(text or "")
    if m:
        address = _WS_RE.sub(" ", f"{m.group(1)} {m.group(2)}").strip().rstrip(".,")
    parcel = None
    pm = _PARCEL_RE.search(text or "")
    if pm:
        parcel = pm.group(1)
    return {"address": address, "parcel": parcel}
