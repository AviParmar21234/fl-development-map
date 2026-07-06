"""Granicus MediaManager connector (ViewPublisher.php listings + AgendaViewer.php agendas)."""
import re
from datetime import date, datetime, timedelta
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from scraper import http
from scraper.connectors.base import RawItem

LOOKBACK_DAYS = 180
LOOKAHEAD_DAYS = 90
MAX_MEETINGS = 40

# Some Granicus views 403 the default bot UA; retry with a browser UA.
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
}

_DATE_RE = re.compile(r"([A-Z][a-z]{2})[\s\xa0]+(\d{1,2}),[\s\xa0]+(\d{4})")


def _get(url: str):
    try:
        return http.get(url)
    except Exception as e:
        if "403" in str(e):
            return http.get(url, headers=BROWSER_HEADERS)
        raise


def _abs(href: str, page_url: str) -> str:
    if href.startswith("//"):
        return f"{urlparse(page_url).scheme or 'https'}:{href}"
    return urljoin(page_url, href)


def parse_listing(html: str, page_url: str) -> list[tuple[str, str, str]]:
    """Return [(meeting_name, iso_date, agenda_viewer_url)] from a ViewPublisher.php page."""
    soup = BeautifulSoup(html, "html.parser")
    out, seen = [], set()
    for tr in soup.find_all("tr"):
        a = tr.find("a", href=re.compile(r"AgendaViewer\.php"))
        if a is None:
            continue
        url = _abs(a["href"], page_url)
        if url in seen:
            continue
        cells = tr.find_all("td")
        if not cells:
            continue
        name = cells[0].get_text(" ", strip=True)
        m = _DATE_RE.search(tr.get_text(" ", strip=True))
        if not name or not m:
            continue
        try:
            iso = datetime.strptime(f"{m.group(1)} {m.group(2)}, {m.group(3)}", "%b %d, %Y").date().isoformat()
        except ValueError:
            continue
        seen.add(url)
        out.append((name, iso, url))
    return out


def parse_agenda(html: str) -> list[tuple[str | None, str]]:
    """Return [(anchor_name_or_None, item_title)] from an AgendaViewer.php page."""
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for a in soup.find_all("a", class_="Agenda"):
        title = a.get_text(" ", strip=True).rstrip(":").strip()
        if not title:
            continue
        items.append((a.get("name") or None, title))
    return items


def fetch(source: dict) -> list[RawItem]:
    view_url = source["url"]
    listing = parse_listing(_get(view_url).text, view_url)
    today = date.today()
    since = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
    until = (today + timedelta(days=LOOKAHEAD_DAYS)).isoformat()
    in_window = [m for m in listing if since <= m[1] <= until]
    in_window.sort(key=lambda m: abs((date.fromisoformat(m[1]) - today).days))
    out: list[RawItem] = []
    for name, mdate, agenda_url in in_window[:MAX_MEETINGS]:
        try:
            html = _get(agenda_url).text
        except Exception:
            continue
        for anchor, title in parse_agenda(html):
            link = f"{agenda_url}#{anchor}" if anchor else agenda_url
            out.append(RawItem(
                source_id=source["id"],
                jurisdiction=source["name"],
                county=source["county"],
                meeting_body=name,
                meeting_date=mdate,
                title=title,
                body_text="",
                link=link,
            ))
    return out
