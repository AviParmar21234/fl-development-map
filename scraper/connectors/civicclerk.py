"""CivicClerk (CivicPlus) connector: OData API at https://{tenant}.api.civicclerk.com/v1.

Endpoints used:
  GET {base}/v1/Events?$filter=startDateTime ge ... and startDateTime le ...
      -> paged (15/page, follow @odata.nextLink); each event embeds publishedFiles
         [{fileId, type: 'Agenda'|'Agenda Packet'|'Minutes', ...}].
  GET {base}/v1/Meetings/GetMeetingFileStream(fileId={id},plainText=true)
      -> plain-text rendition of the published agenda; numbered agenda items are
         parsed out of it for item-level granularity.

Human link: https://{tenant}.portal.civicclerk.com/event/{id}/overview
"""
import re
from datetime import date, timedelta
from urllib.parse import urlparse

from scraper import http
from scraper.connectors.base import RawItem

LOOKBACK_DAYS = 180
LOOKAHEAD_DAYS = 90
MAX_MEETINGS = 60  # per source, closest-to-today first
MAX_PAGES = 40  # safety cap on @odata.nextLink paging (15 events/page)

# "1.  Title", "3.A Title", "3.A. Title", "4.1 Title" all start a new item
_ITEM_RE = re.compile(r"^\s*(\d{1,3}\.(?:[A-Za-z0-9]{1,3}\.?)?)\s+(\S.*)$")
# Centered ALL-CAPS agenda section headers, e.g. "PROCLAMATION", "CITIZEN COMMENTS"
_SECTION_RE = re.compile(r"^[A-Z][A-Z0-9\s\-–&/'.,():;]*$")


def tenant_from_url(url: str) -> str:
    """'https://jupiterfl.api.civicclerk.com' -> 'jupiterfl'."""
    host = urlparse(url).netloc or urlparse("//" + url).netloc or url
    return host.split(".")[0]


def event_link(tenant: str, event_id) -> str:
    return f"https://{tenant}.portal.civicclerk.com/event/{event_id}/overview"


def pick_agenda_file_id(event: dict):
    """fileId of the published 'Agenda' file (not the packet), or None."""
    for f in event.get("publishedFiles") or []:
        if (f.get("type") or "").strip().lower() == "agenda" and f.get("fileId"):
            return f["fileId"]
    return None


def _is_section_header(line: str) -> bool:
    s = line.strip()
    if len(s) < 3 or len(s) > 80:
        return False
    if sum(c.isupper() for c in s) < 3:
        return False
    return bool(_SECTION_RE.match(s))


def _clean_title(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s*#\s*$", "", text).strip()


def parse_agenda_text(text: str) -> list[dict]:
    """Extract numbered agenda items from a plain-text agenda rendition.

    Returns [{"number": "1", "section": "PROCLAMATION", "title": "..."}].
    Wrapped item lines are joined; a blank line, a new numbered item, or an
    ALL-CAPS section header terminates the current item.
    """
    items: list[dict] = []
    section = ""
    current: dict | None = None
    parts: list[str] = []

    def close():
        nonlocal current, parts
        if current is not None:
            title = _clean_title(" ".join(parts))
            if title:
                current["title"] = title
                items.append(current)
        current, parts = None, []

    for line in text.splitlines():
        if not line.strip():
            close()
            continue
        m = _ITEM_RE.match(line)
        if m:
            close()
            current = {"number": m.group(1).rstrip("."), "section": section, "title": ""}
            parts = [m.group(2)]
            continue
        if _is_section_header(line):
            close()
            section = _clean_title(line)
            continue
        if current is not None:
            parts.append(line.strip())
    close()
    return items


def map_event(source: dict, tenant: str, event: dict, agenda_items: list[dict]) -> list[RawItem]:
    """Pure mapping from one CivicClerk event (+parsed agenda items) to RawItems.

    Falls back to a single event-level RawItem when no item-level data exists.
    """
    meeting_date = (event.get("startDateTime") or event.get("eventDate") or "")[:10]
    body = (
        event.get("eventCategoryName")
        or event.get("categoryName")
        or event.get("eventName")
        or ""
    )
    link = event_link(tenant, event.get("id"))
    common = dict(
        source_id=source["id"],
        jurisdiction=source["name"],
        county=source["county"],
        meeting_body=body,
        meeting_date=meeting_date,
        link=link,
    )
    out: list[RawItem] = []
    for it in agenda_items:
        title = (it.get("title") or "").strip()
        if not title:
            continue
        out.append(RawItem(title=title, body_text=it.get("description") or "", **common))
    if not out:
        title = (event.get("eventName") or "").strip()
        if title:
            out.append(RawItem(
                title=title,
                body_text=(event.get("eventDescription") or ""),
                **common,
            ))
    return out


def select_events(events: list[dict], today: date | None = None) -> list[dict]:
    """Window to [today-180d, today+90d], closest-to-today first, cap MAX_MEETINGS."""
    today = today or date.today()
    since = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
    until = (today + timedelta(days=LOOKAHEAD_DAYS)).isoformat()
    dated = []
    for ev in events:
        d = (ev.get("startDateTime") or ev.get("eventDate") or "")[:10]
        if since <= d <= until:
            dated.append((abs((date.fromisoformat(d) - today).days), ev))
    dated.sort(key=lambda t: t[0])
    return [ev for _, ev in dated[:MAX_MEETINGS]]


def _events(base: str, today: date | None = None) -> list[dict]:
    today = today or date.today()
    since = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
    until = (today + timedelta(days=LOOKAHEAD_DAYS)).isoformat()
    params = {
        "$filter": (
            f"startDateTime ge {since}T00:00:00Z and startDateTime le {until}T23:59:59Z"
        ),
    }
    out: list[dict] = []
    resp = http.get(f"{base}/v1/Events", params=params).json()
    out += resp.get("value") or []
    next_link = resp.get("@odata.nextLink")
    pages = 1
    while next_link and pages < MAX_PAGES:
        resp = http.get(next_link).json()
        out += resp.get("value") or []
        next_link = resp.get("@odata.nextLink")
        pages += 1
    return out


def _agenda_items(base: str, file_id) -> list[dict]:
    url = f"{base}/v1/Meetings/GetMeetingFileStream(fileId={file_id},plainText=true)"
    resp = http.get(url)
    ctype = resp.headers.get("Content-Type", "")
    if "pdf" in ctype.lower() or resp.content[:4] == b"%PDF":
        return []  # plain-text rendition not available for this file
    return parse_agenda_text(resp.text)


def fetch(source: dict) -> list[RawItem]:
    base = source["url"].rstrip("/")
    tenant = tenant_from_url(base)
    events = select_events(_events(base))
    out: list[RawItem] = []
    for ev in events:
        agenda_items: list[dict] = []
        file_id = pick_agenda_file_id(ev)
        if file_id:
            try:
                agenda_items = _agenda_items(base, file_id)
            except Exception:
                agenda_items = []
        out += map_event(source, tenant, ev, agenda_items)
    return out
