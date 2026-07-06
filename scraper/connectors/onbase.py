"""Hyland OnBase "Agenda Online" connector (e.g. tampagov.hylandcloud.com/251agendaonline).

The portal renders its meeting list client-side, but the search page embeds the
full result set as JSON, so no JS execution is needed.

Endpoints used:
  GET {base}/Meetings/Search?dropid=11&dropsv=M/D/YYYY&dropev=M/D/YYYY
      -> HTML page embedding the results as JSON inside
         'showSearchResults(new SearchResults({...}))'. data["Meetings"] has
         ID, Name, MeetingTypeName, Time (ISO w/ offset), IsAgendaAvailable...
         (dropid=11 selects "Custom Date Range"; server caps at 100 results)
  GET {base}/Documents/ViewAgenda?meetingId={id}&type=agenda&doctype=1
      -> full agenda HTML. Each agenda item is bookmarked '<a name="I{itemId}">'
         followed by a 'javascript:loadAgendaItem({itemId},false)' title link;
         the enclosing table cell holds the item's descriptive paragraphs.

Item link: {base}/Meetings/ViewMeetingAgendaItem?meetingId=..&itemId=..&isSection=False&type=agenda
(the public "Item Details" page for that agenda item).

Meetings without a published agenda are skipped: meeting names alone
("City Council Regular - June 18, 2026") carry no project signal.
"""
import json
import re
from datetime import date, timedelta

from bs4 import BeautifulSoup

from scraper import http
from scraper.connectors.base import RawItem

LOOKBACK_DAYS = 180
LOOKAHEAD_DAYS = 90
MAX_MEETINGS = 50
MAX_BODY_CHARS = 2000

_RESULTS_MARKER = "showSearchResults(new SearchResults("
_ITEM_ANCHOR_RE = re.compile(r"^I(\d+)$")


def extract_search_json(html: str) -> dict:
    """Pull the SearchResults JSON blob out of the Meetings/Search HTML page."""
    start = html.find(_RESULTS_MARKER)
    if start == -1:
        return {}
    start += len(_RESULTS_MARKER)
    depth = 0
    for i in range(start, len(html)):
        c = html[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(html[start:i + 1])
                except ValueError:
                    return {}
    return {}


def select_meetings(meetings: list[dict], today: date | None = None) -> list[dict]:
    """Agenda-published meetings in [today-180d, today+90d], closest-to-today
    first, capped at MAX_MEETINGS."""
    today = today or date.today()
    since = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
    until = (today + timedelta(days=LOOKAHEAD_DAYS)).isoformat()
    dated = []
    for m in meetings:
        if not m.get("IsAgendaAvailable"):
            continue
        d = (m.get("Time") or "")[:10]
        if len(d) == 10 and since <= d <= until:
            dated.append((abs((date.fromisoformat(d) - today).days), m))
    dated.sort(key=lambda t: t[0])
    return [m for _, m in dated[:MAX_MEETINGS]]


def _para_text(p) -> str:
    return p.get_text(" ", strip=True).replace("\xa0", " ").strip()


def parse_agenda(html: str) -> list[dict]:
    """Extract agenda items from a Documents/ViewAgenda HTML rendition.

    Returns [{"item_id": "24195", "title": "...", "body": "..."}]; title is the
    text of the loadAgendaItem link after the '<a name="I{id}">' bookmark, body
    is the remaining paragraph text within the same table cell.
    """
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", attrs={"name": _ITEM_ANCHOR_RE}):
        item_id = _ITEM_ANCHOR_RE.match(anchor["name"]).group(1)
        if item_id in seen:
            continue
        seen.add(item_id)
        title_link = anchor.find_next_sibling("a")
        title = re.sub(r"\s+", " ", title_link.get_text(" ", strip=True)) if title_link else ""
        if not title:
            continue
        body = ""
        td = anchor.find_parent("td")
        if td is not None:
            title_p = anchor.find_parent("p")
            parts = [t for p in td.find_all("p") if p is not title_p and (t := _para_text(p))]
            body = re.sub(r"\s+", " ", " ".join(parts)).strip()[:MAX_BODY_CHARS]
        out.append({"item_id": item_id, "title": title, "body": body})
    return out


def item_link(base: str, meeting_id, item_id) -> str:
    return (f"{base}/Meetings/ViewMeetingAgendaItem?meetingId={meeting_id}"
            f"&itemId={item_id}&isSection=False&type=agenda")


def map_meeting(source: dict, base: str, meeting: dict, items: list[dict]) -> list[RawItem]:
    """Pure mapping from one OnBase meeting (+parsed agenda items) to RawItems."""
    meeting_date = (meeting.get("Time") or "")[:10]
    body_name = meeting.get("MeetingTypeName") or meeting.get("Name") or "Meeting"
    out: list[RawItem] = []
    for it in items:
        title = (it.get("title") or "").strip()
        if not title:
            continue
        out.append(RawItem(
            source_id=source["id"],
            jurisdiction=source["name"],
            county=source["county"],
            meeting_body=body_name,
            meeting_date=meeting_date,
            title=title,
            body_text=it.get("body") or "",
            link=item_link(base, meeting.get("ID"), it.get("item_id")),
        ))
    return out


def _mdy(d: date) -> str:
    return f"{d.month}/{d.day}/{d.year}"


def fetch(source: dict) -> list[RawItem]:
    base = source["url"].rstrip("/")
    today = date.today()
    # Two ranged searches (past, future): the server caps each search at 100
    # results, so one 270-day query silently truncates the lookback window.
    ranges = [
        (today - timedelta(days=LOOKBACK_DAYS), today),
        (today, today + timedelta(days=LOOKAHEAD_DAYS)),
    ]
    meetings: dict = {}
    for start, end in ranges:
        params = {"dropid": 11, "dropsv": _mdy(start), "dropev": _mdy(end)}  # 11 = custom range
        try:
            data = extract_search_json(http.get(f"{base}/Meetings/Search", params=params).text)
        except Exception:
            continue
        for m in data.get("Meetings") or []:
            if m.get("ID") is not None:
                meetings[m["ID"]] = m
    out: list[RawItem] = []
    for m in select_meetings(list(meetings.values()), today=today):
        try:
            html = http.get(
                f"{base}/Documents/ViewAgenda",
                params={"meetingId": m["ID"], "type": "agenda", "doctype": 1},
            ).text
        except Exception:
            continue
        out += map_meeting(source, base, m, parse_agenda(html))
    return out
