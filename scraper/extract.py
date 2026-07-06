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
