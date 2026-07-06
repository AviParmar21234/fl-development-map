"""Legistar Web API connector: https://webapi.legistar.com/v1/{client}."""
from datetime import date, timedelta

from scraper import http
from scraper.connectors.base import RawItem

API = "https://webapi.legistar.com/v1"
LOOKBACK_DAYS = 180
MAX_EVENTS = 120  # per source, newest-window first


def _events(client: str) -> list[dict]:
    since = (date.today() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%dT00:00:00")
    url = f"{API}/{client}/Events"
    params = {"$filter": f"EventDate ge datetime'{since}'", "$orderby": "EventDate desc"}
    return http.get(url, params=params).json()[:MAX_EVENTS]


def _event_items(client: str, event_id: int) -> list[dict]:
    url = f"{API}/{client}/Events/{event_id}/EventItems"
    return http.get(url, params={"AgendaNote": "1", "MinutesNote": "1"}).json()


def map_items(source: dict, events: list[dict], items_by_event) -> list[RawItem]:
    """Pure mapping from Legistar JSON to RawItems (fixture-testable)."""
    client = source["legistar_client"]
    out: list[RawItem] = []
    for ev in events:
        ev_date = (ev.get("EventDate") or "")[:10]
        body = ev.get("EventBodyName") or ""
        fallback_link = ev.get("EventInSiteURL") or f"https://{client}.legistar.com"
        for it in items_by_event.get(ev["EventId"], []):
            title = (it.get("EventItemTitle") or "").strip()
            if not title:
                continue
            matter_id = it.get("EventItemMatterId")
            link = (
                f"https://{client}.legistar.com/LegislationDetail.aspx?ID={matter_id}"
                if matter_id else fallback_link
            )
            out.append(RawItem(
                source_id=source["id"],
                jurisdiction=source["name"],
                county=source["county"],
                meeting_body=body,
                meeting_date=ev_date,
                title=title,
                body_text=(it.get("EventItemAgendaNote") or ""),
                link=link,
            ))
    return out


def fetch(source: dict) -> list[RawItem]:
    client = source["legistar_client"]
    events = _events(client)
    items_by_event = {}
    for ev in events:
        try:
            items_by_event[ev["EventId"]] = _event_items(client, ev["EventId"])
        except Exception:
            items_by_event[ev["EventId"]] = []
    return map_items(source, events, items_by_event)
