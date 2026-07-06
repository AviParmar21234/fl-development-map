"""Granicus IQM2 connector (e.g. miamifl.iqm2.com)."""
import re
from datetime import date, datetime, timedelta

from bs4 import BeautifulSoup

from scraper import http
from scraper.connectors.base import RawItem

LOOKBACK_DAYS = 180
MAX_MEETINGS = 80

_MEETING_LINK_RE = re.compile(r"Detail_Meeting\.aspx\?ID=(\d+)")
_TITLE_TAG_RE = re.compile(r"(\d{4}/\d{2}/\d{2}) \d{2}:\d{2} [AP]M (.*?) - (?:Web Outline|Agenda|Minutes) - ", re.S)


def parse_calendar(html: str) -> list[tuple[str, str]]:
    """Return [(meeting_id, iso_date)] from a Calendar.aspx page."""
    soup = BeautifulSoup(html, "html.parser")
    out, seen = [], set()
    for a in soup.find_all("a", href=_MEETING_LINK_RE):
        mid = _MEETING_LINK_RE.search(a["href"]).group(1)
        if mid in seen:
            continue
        text = a.get_text(" ", strip=True)
        m = re.search(r"([A-Z][a-z]{2} \d{1,2}, \d{4})", text)
        if not m:
            continue
        seen.add(mid)
        iso = datetime.strptime(m.group(1), "%b %d, %Y").date().isoformat()
        out.append((mid, iso))
    return out


def parse_meeting(html: str, base_url: str) -> tuple[str, list[tuple[str, str]]]:
    """Return (meeting_body, [(item_link_abs, item_title)]) from Detail_Meeting.aspx."""
    tm = _TITLE_TAG_RE.search(html)
    body_name = tm.group(2).strip() if tm else "Meeting"
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for a in soup.find_all("a", href=re.compile(r"Detail_LegiFile\.aspx")):
        title = a.get_text(" ", strip=True)
        if not title:
            continue
        items.append((f"{base_url}/Citizens/{a['href']}", title))
    return body_name, items


def fetch_detail(link: str) -> str:
    """Full text of a Detail_LegiFile item page (for address enrichment)."""
    try:
        soup = BeautifulSoup(http.get(link).text, "html.parser")
        main = soup.find(id="MainContentHolder") or soup.body or soup
        return main.get_text(" ", strip=True)[:4000]
    except Exception:
        return ""


def fetch(source: dict) -> list[RawItem]:
    base = source["url"].rstrip("/")
    if base.endswith("/Citizens") or "/Citizens/" in base:
        base = base.split("/Citizens")[0]
    today = date.today()
    since = today - timedelta(days=LOOKBACK_DAYS)
    meetings: list[tuple[str, str]] = []
    for year in sorted({since.year, today.year + 1, today.year}):
        url = f"{base}/Citizens/Calendar.aspx?From=1/1/{year}&To=12/31/{year}"
        try:
            meetings += parse_calendar(http.get(url).text)
        except Exception:
            continue
    horizon = (today + timedelta(days=90)).isoformat()
    in_window = [(mid, d) for mid, d in meetings if since.isoformat() <= d <= horizon]
    # closest-to-today first: recent past has full agendas, near future has published ones
    in_window.sort(key=lambda t: abs((date.fromisoformat(t[1]) - today).days))
    out: list[RawItem] = []
    for mid, mdate in in_window[:MAX_MEETINGS]:
        try:
            html = http.get(f"{base}/Citizens/Detail_Meeting.aspx?ID={mid}").text
        except Exception:
            continue
        body_name, items = parse_meeting(html, base)
        for link, title in items:
            out.append(RawItem(
                source_id=source["id"],
                jurisdiction=source["name"],
                county=source["county"],
                meeting_body=body_name,
                meeting_date=mdate,
                title=title,
                body_text="",
                link=link,
            ))
    return out
