"""CivicPlus AgendaCenter connector (PDF agendas, HTML preview preferred when present)."""
import io
import re
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scraper import http
from scraper.connectors.base import RawItem

LOOKBACK_DAYS = 180
LOOKAHEAD_DAYS = 90
MAX_MEETINGS = 40
MAX_PDF_DOWNLOADS = 15
TITLE_MAX = 200
BODY_MAX = 1000

_AGENDA_HREF_RE = re.compile(r"/AgendaCenter/ViewFile/Agenda/_(\d{8})-\d+$")
# item start: "1." / "12)" / "A." / "IV." at line start
_ITEM_START_RE = re.compile(r"^\s*(\d{1,3}|[A-Z]{1,4})[.)]\s+(\S.*)$")


def parse_listing(html: str, base_url: str) -> list[dict]:
    """Return [{committee, date, agenda_url, html_url}] from an AgendaCenter listing page."""
    soup = BeautifulSoup(html, "html.parser")
    out, seen = [], set()
    for section in soup.find_all("div", class_="listing"):
        h2 = section.find("h2")
        committee = h2.get_text(" ", strip=True) if h2 else "Meeting"
        for a in section.find_all("a", href=_AGENDA_HREF_RE):
            path = a["href"]
            if path in seen:
                continue
            seen.add(path)
            mmddyyyy = _AGENDA_HREF_RE.search(path).group(1)
            try:
                iso = datetime.strptime(mmddyyyy, "%m%d%Y").date().isoformat()
            except ValueError:
                continue
            html_url = None
            row = a.find_parent("tr")
            if row is not None:
                hv = row.find("a", href=re.compile(r"html=true"))
                if hv is not None:
                    html_url = urljoin(base_url, hv["href"])
            out.append({
                "committee": committee,
                "date": iso,
                "agenda_url": urljoin(base_url, path),
                "html_url": html_url,
            })
    return out


def collapse_doubled(text: str) -> str:
    """Undo fake-bold PDF artifacts where every char of a token is doubled (CCAALLLL -> CALL)."""
    def fix(tok: str) -> str:
        if len(tok) >= 4 and len(tok) % 2 == 0 and all(tok[i] == tok[i + 1] for i in range(0, len(tok), 2)):
            return tok[::2]
        return tok
    return "\n".join(
        " ".join(fix(t) for t in line.split(" ")) for line in text.split("\n")
    )


def parse_agenda_text(text: str) -> list[str]:
    """Extract agenda item blocks from plain agenda text (numbered/lettered lines)."""
    items: list[list[str]] = []
    current: list[str] | None = None
    for line in text.split("\n"):
        line = line.strip()
        m = _ITEM_START_RE.match(line)
        if m:
            current = [m.group(2).strip()]
            items.append(current)
        elif current is not None and line:
            if sum(len(s) for s in current) < BODY_MAX:
                current.append(line)
        elif not line:
            current = None
    return [" ".join(block)[:BODY_MAX] for block in items if len(" ".join(block)) >= 4]


def html_agenda_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return soup.get_text("\n")


def pdf_agenda_text(content: bytes) -> str:
    import pdfplumber
    parts = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            try:
                page = page.dedupe_chars()
            except Exception:
                pass
            parts.append(page.extract_text() or "")
    return collapse_doubled("\n".join(parts))


def fetch(source: dict) -> list[RawItem]:
    listing_url = source["url"]
    meetings = parse_listing(http.get(listing_url).text, listing_url)
    today = date.today()
    since = (today - timedelta(days=LOOKBACK_DAYS)).isoformat()
    until = (today + timedelta(days=LOOKAHEAD_DAYS)).isoformat()
    in_window = [m for m in meetings if since <= m["date"] <= until]
    in_window.sort(key=lambda m: abs((date.fromisoformat(m["date"]) - today).days))
    out: list[RawItem] = []
    pdf_budget = MAX_PDF_DOWNLOADS
    for m in in_window[:MAX_MEETINGS]:
        try:
            if m["html_url"]:
                link = m["html_url"]
                text = html_agenda_text(http.get(link).text)
            else:
                if pdf_budget <= 0:
                    continue
                pdf_budget -= 1
                link = m["agenda_url"]
                resp = http.get(link)
                text = pdf_agenda_text(resp.content)
        except Exception:
            continue
        if not text.strip():
            continue  # scanned/image PDF or empty agenda
        for block in parse_agenda_text(text):
            out.append(RawItem(
                source_id=source["id"],
                jurisdiction=source["name"],
                county=source["county"],
                meeting_body=m["committee"],
                meeting_date=m["date"],
                title=block[:TITLE_MAX],
                body_text=block,
                link=link,
            ))
    return out
