"""eScribe connector (e.g. pub-orlando.escribemeetings.com).

Endpoints used:
  POST {base}/MeetingsCalendarView.aspx/GetCalendarMeetings
       JSON body {"calendarStartDate": "YYYY-MM-DDT00:00:00",
                  "calendarEndDate": "YYYY-MM-DDT00:00:00"}
       -> {"d": [{ID (guid), MeetingName, MeetingType,
                  StartDate "YYYY/MM/DD HH:MM:SS", HasAgenda, Location, ...}]}
       (ASP.NET page method; POST + Content-Type: application/json required.
        scraper.http exposes only get(), so _post_json below reuses its
        session/throttle/retry plumbing to keep the same politeness.)
  GET  {base}/Meeting.aspx?Id={guid}&Agenda=Agenda&lang=English
       -> server-rendered agenda HTML. Each agenda item is an <h2>/<h3>/<h4>
          with id="AgendaItemAgendaItem{N}TitleHeader" containing
          .AgendaItemCounter (e.g. "3.a.1") and .AgendaItemTitle; an optional
          .AgendaItemDescription div lives in the same .AgendaItem container.

Item link: the agenda page URL + '#AgendaItemAgendaItem{N}TitleHeader'
(the heading's element id, so browsers scroll straight to the item).
"""
import re
import time
from datetime import date, timedelta
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from scraper import http
from scraper.connectors.base import RawItem

LOOKBACK_DAYS = 180
LOOKAHEAD_DAYS = 90
MAX_MEETINGS = 50
MAX_BODY_CHARS = 2000

_HEAD_ID_RE = re.compile(r"^AgendaItemAgendaItem(\d+)TitleHeader$")


def _post_json(url: str, payload: dict) -> dict:
    """POST JSON with scraper.http's session, throttle, timeout and retries."""
    host = urlparse(url).netloc
    err: Exception | None = None
    for attempt in range(http.RETRIES + 1):
        http._throttle(host)
        try:
            resp = http._session.post(
                url, json=payload, timeout=http.TIMEOUT_S,
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code >= 500 and attempt < http.RETRIES:
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            err = e
            if attempt < http.RETRIES:
                time.sleep(1 + attempt)
    raise err  # type: ignore[misc]


def meeting_iso_date(meeting: dict) -> str:
    """'2026/06/08 14:00:23' -> '2026-06-08' ('' when absent/malformed)."""
    raw = (meeting.get("StartDate") or "").strip()[:10].replace("/", "-")
    return raw if re.match(r"^\d{4}-\d{2}-\d{2}$", raw) else ""


def agenda_url(base: str, meeting_id) -> str:
    return f"{base}/Meeting.aspx?Id={meeting_id}&Agenda=Agenda&lang=English"


def select_meetings(meetings: list[dict], today: date | None = None) -> list[dict]:
    """Window to [today-180d, today+90d], closest-to-today first, cap MAX_MEETINGS."""
    today = today or date.today()
    since = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
    until = (today + timedelta(days=LOOKAHEAD_DAYS)).isoformat()
    dated = []
    for m in meetings:
        d = meeting_iso_date(m)
        if d and since <= d <= until:
            dated.append((abs((date.fromisoformat(d) - today).days), m))
    dated.sort(key=lambda t: t[0])
    return [m for _, m in dated[:MAX_MEETINGS]]


def parse_agenda(html: str) -> list[dict]:
    """Extract agenda items from a Meeting.aspx?...&Agenda=Agenda HTML view.

    Returns [{"item_id": "9840", "number": "3.a.1", "title": "...", "body": "..."}].
    """
    soup = BeautifulSoup(html, "html.parser")
    out: list[dict] = []
    seen: set[str] = set()
    for h in soup.find_all(["h2", "h3", "h4"], id=_HEAD_ID_RE):
        item_id = _HEAD_ID_RE.match(h["id"]).group(1)
        if item_id in seen:
            continue
        seen.add(item_id)
        title_div = h.find("div", class_="AgendaItemTitle")
        title = re.sub(r"\s+", " ", title_div.get_text(" ", strip=True)) if title_div else ""
        if not title:
            continue
        counter_div = h.find("div", class_="AgendaItemCounter")
        number = counter_div.get_text(" ", strip=True) if counter_div else ""
        body = ""
        container = h.find_parent("div", class_="AgendaItem")
        if container is not None:
            desc = container.find("div", class_="AgendaItemDescription")
            if desc is not None:
                body = re.sub(r"\s+", " ", desc.get_text(" ", strip=True))[:MAX_BODY_CHARS]
        out.append({"item_id": item_id, "number": number, "title": title, "body": body})
    return out


def map_meeting(source: dict, base: str, meeting: dict, items: list[dict]) -> list[RawItem]:
    """Pure mapping from one eScribe meeting (+parsed agenda items) to RawItems.

    Falls back to a single meeting-level RawItem when no item-level data exists.
    """
    mid = meeting.get("ID")
    common = dict(
        source_id=source["id"],
        jurisdiction=source["name"],
        county=source["county"],
        meeting_body=meeting.get("MeetingType") or meeting.get("MeetingName") or "",
        meeting_date=meeting_iso_date(meeting),
    )
    url = agenda_url(base, mid)
    out: list[RawItem] = []
    for it in items:
        title = (it.get("title") or "").strip()
        if not title:
            continue
        out.append(RawItem(
            title=title,
            body_text=it.get("body") or "",
            link=f"{url}#AgendaItemAgendaItem{it.get('item_id')}TitleHeader",
            **common,
        ))
    if not out:
        title = (meeting.get("MeetingName") or "").strip()
        if title:
            location = re.sub(r"<[^>]+>", " ", meeting.get("Description") or "")
            out.append(RawItem(
                title=title,
                body_text=re.sub(r"\s+", " ", location).strip(),
                link=meeting.get("Url") or url,
                **common,
            ))
    return out


def fetch(source: dict) -> list[RawItem]:
    base = source["url"].rstrip("/")
    today = date.today()
    payload = {
        "calendarStartDate": f"{(today - timedelta(days=LOOKBACK_DAYS)).isoformat()}T00:00:00",
        "calendarEndDate": f"{(today + timedelta(days=LOOKAHEAD_DAYS)).isoformat()}T00:00:00",
    }
    resp = _post_json(f"{base}/MeetingsCalendarView.aspx/GetCalendarMeetings", payload)
    meetings = resp.get("d") or []
    out: list[RawItem] = []
    for m in select_meetings(meetings, today=today):
        items: list[dict] = []
        if m.get("HasAgenda"):
            try:
                items = parse_agenda(http.get(agenda_url(base, m["ID"])).text)
            except Exception:
                items = []
        out += map_meeting(source, base, m, items)
    return out
