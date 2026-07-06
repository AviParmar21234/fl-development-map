"""PrimeGov connector (e.g. miamibeachfl.primegov.com)."""
from datetime import date, timedelta

from bs4 import BeautifulSoup

from scraper import http
from scraper.connectors.base import RawItem

LOOKBACK_DAYS = 180
HORIZON_DAYS = 90
MAX_MEETINGS = 40
_BUTTON_NOISE = "Combine item's attachments into one PDF and view"


def parse_agenda(html: str, link_base: str) -> list[tuple[str, str]]:
    """[(item_link, item_text)] from a PrimeGov compiled HTML agenda.

    Agenda items are tables with class item-table-fromdocx and a data-itemid
    attribute (section headers carry data-sectionid instead).
    """
    soup = BeautifulSoup(html, "html.parser")
    out, seen = [], set()
    for table in soup.find_all("table", class_="item-table-fromdocx"):
        item_id = table.get("data-itemid")
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        text = table.get_text(" ", strip=True).replace(_BUTTON_NOISE, " ")
        text = " ".join(text.split())
        if not text:
            continue
        out.append((f"{link_base}#AgendaItem_{item_id}", text))
    return out


def _meetings(base: str) -> list[dict]:
    today = date.today()
    since = today - timedelta(days=LOOKBACK_DAYS)
    horizon = today + timedelta(days=HORIZON_DAYS)
    raw: dict[int, dict] = {}
    try:
        for m in http.get(f"{base}/api/v2/PublicPortal/ListUpcomingMeetings").json():
            raw[m["id"]] = m
    except Exception:
        pass
    for year in sorted({since.year, today.year, horizon.year}):
        try:
            for m in http.get(f"{base}/api/v2/PublicPortal/ListArchivedMeetings", params={"year": year}).json():
                raw.setdefault(m["id"], m)
        except Exception:
            continue
    keep = []
    for m in raw.values():
        d = (m.get("dateTime") or "")[:10]
        if not d or not (since.isoformat() <= d <= horizon.isoformat()):
            continue
        if (m.get("title") or "").startswith("Canceled"):
            continue
        keep.append(m)
    keep.sort(key=lambda m: abs((date.fromisoformat(m["dateTime"][:10]) - today).days))
    return keep[:MAX_MEETINGS]


def fetch(source: dict) -> list[RawItem]:
    base = source["url"].rstrip("/")
    out: list[RawItem] = []
    for m in _meetings(base):
        doc = next((d for d in (m.get("documentList") or []) if d.get("templateName") == "HTML Agenda"), None)
        if not doc:
            continue
        link_base = f"{base}/Portal/Meeting?compiledMeetingDocumentFileId={doc['id']}"
        try:
            items = parse_agenda(http.get(link_base).text, link_base)
        except Exception:
            continue
        for link, text in items:
            out.append(RawItem(
                source_id=source["id"],
                jurisdiction=source["name"],
                county=source["county"],
                meeting_body=m.get("title") or "Meeting",
                meeting_date=m["dateTime"][:10],
                title=text[:300],
                body_text=text[300:1300],
                link=link,
            ))
    return out
