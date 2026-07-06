"""Legistar Web API connector: https://webapi.legistar.com/v1/{client}."""
import re
from datetime import date, timedelta

from scraper import http
from scraper.connectors.base import RawItem

API = "https://webapi.legistar.com/v1"
LOOKBACK_DAYS = 180
MAX_EVENTS = 120  # per source, newest-window first

# The web UI's LegislationDetail IDs are a different id-space than the API's MatterIds,
# so real item links must be harvested from the meeting's InSite page and matched by File #.
_LEGI_HREF_RE = re.compile(r"LegislationDetail\.aspx", re.I)


def insite_file_links(html: str, base: str) -> dict:
    """Map of File # (anchor text, e.g. '26-0653') -> absolute LegislationDetail URL."""
    from bs4 import BeautifulSoup
    out = {}
    for a in BeautifulSoup(html, "html.parser").find_all("a", href=_LEGI_HREF_RE):
        file_no = a.get_text(" ", strip=True)
        if file_no and file_no not in out:
            out[file_no] = f"{base}/{a['href']}"
    return out


def _events(client: str) -> list[dict]:
    since = (date.today() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%dT00:00:00")
    url = f"{API}/{client}/Events"
    params = {"$filter": f"EventDate ge datetime'{since}'", "$orderby": "EventDate desc"}
    return http.get(url, params=params).json()[:MAX_EVENTS]


def _event_items(client: str, event_id: int) -> list[dict]:
    url = f"{API}/{client}/Events/{event_id}/EventItems"
    return http.get(url, params={"AgendaNote": "1", "MinutesNote": "1"}).json()


def map_items(source: dict, events: list[dict], items_by_event, web_links=None) -> list[RawItem]:
    """Pure mapping from Legistar JSON to RawItems (fixture-testable).

    web_links: {event_id: {file_no: url}} harvested from InSite pages; items whose
    MatterFile matches get a direct legislation link, others fall back to the
    meeting page (EventInSiteURL), which always works.
    """
    client = source["legistar_client"]
    web_links = web_links or {}
    out: list[RawItem] = []
    for ev in events:
        ev_date = (ev.get("EventDate") or "")[:10]
        body = ev.get("EventBodyName") or ""
        fallback_link = ev.get("EventInSiteURL") or f"https://{client}.legistar.com"
        file_map = web_links.get(ev["EventId"], {})
        for it in items_by_event.get(ev["EventId"], []):
            title = (it.get("EventItemTitle") or "").strip()
            if not title:
                continue
            link = file_map.get((it.get("EventItemMatterFile") or "").strip(), fallback_link)
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


def fetch_detail(link: str) -> str:
    """Text of a LegislationDetail web page (for address enrichment)."""
    if "LegislationDetail.aspx" not in link:
        return ""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(http.get(link).text, "html.parser")
        main = soup.find(id="ctl00_ContentPlaceHolder1_pageDetails") or soup.body or soup
        return main.get_text(" ", strip=True)[:4000]
    except Exception:
        return ""


def fetch(source: dict) -> list[RawItem]:
    client = source["legistar_client"]
    base = f"https://{client}.legistar.com"
    events = _events(client)
    items_by_event, web_links = {}, {}
    for ev in events:
        try:
            items_by_event[ev["EventId"]] = _event_items(client, ev["EventId"])
        except Exception:
            items_by_event[ev["EventId"]] = []
        insite = ev.get("EventInSiteURL")
        if insite and items_by_event[ev["EventId"]]:
            try:
                web_links[ev["EventId"]] = insite_file_links(http.get(insite).text, base)
            except Exception:
                pass
    return map_items(source, events, items_by_event, web_links)
