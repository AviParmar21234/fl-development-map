from scraper.connectors.civicplus import (
    collapse_doubled,
    html_agenda_text,
    parse_agenda_text,
    parse_listing,
)

BASE = "https://www.hialeahfl.gov/AgendaCenter"

LISTING_HTML = """
<div class="listing listingCollapse noHeader" id="cat9">
<h2>City Council</h2>
<table id="table9">
<tr class="catAgendaRow">
  <td><h3 id="h406232026-1366"><strong>Jun 23, 2026</strong></h3>
  <p><a href="/AgendaCenter/ViewFile/Agenda/_06232026-1366">City Council Meeting June 23, 2026</a></p></td>
  <td class="downloads">
    <ol><li><a class="pdf" href="/AgendaCenter/ViewFile/Agenda/_06232026-1366">Agenda</a></li></ol>
  </td>
</tr>
<tr class="catAgendaRow">
  <td><p><a href="/AgendaCenter/ViewFile/Agenda/_10112022-271">CRA Agenda Packet</a></p></td>
  <td class="downloads">
    <ol><li><a class="html" href="/AgendaCenter/ViewFile/Agenda/_10112022-271?html=true">HTML</a></li></ol>
  </td>
</tr>
</table>
</div>
<div class="listing listingCollapse noHeader" id="cat14">
<h2>Planning &amp; Zoning Board</h2>
<table id="table14">
<tr class="catAgendaRow">
  <td><p><a href="/AgendaCenter/ViewFile/Agenda/_07152026-1370">PZ Board Meeting</a></p></td>
</tr>
</table>
</div>
"""

AGENDA_TEXT = """City Council Meeting Agenda
June 23, 2026
5:30 p.m.
1. CALL TO ORDER
2. ROLL CALL
9. BOARD APPOINTMENTS
A. RESOLUTION: Proposed resolution appointing Jason Hernandez to the Youth Advisory Committee.
(OFFICE OF THE MAYOR)
B. RESOLUTION: Proposed resolution approving a rezoning at 123 Main Street
from R-1 to R-3 to allow a 40-unit multifamily development.

unrelated trailing paragraph that is not an item
"""


def test_parse_listing_committees_dates_and_html_variant():
    ms = parse_listing(LISTING_HTML, BASE)
    assert len(ms) == 3
    council = ms[0]
    assert council["committee"] == "City Council"
    assert council["date"] == "2026-06-23"
    assert council["agenda_url"] == "https://www.hialeahfl.gov/AgendaCenter/ViewFile/Agenda/_06232026-1366"
    assert council["html_url"] is None
    cra = ms[1]
    assert cra["html_url"] == "https://www.hialeahfl.gov/AgendaCenter/ViewFile/Agenda/_10112022-271?html=true"
    pz = ms[2]
    assert pz["committee"] == "Planning & Zoning Board"
    assert pz["date"] == "2026-07-15"


def test_parse_listing_dedups_repeated_links():
    ms = parse_listing(LISTING_HTML, BASE)
    urls = [m["agenda_url"] for m in ms]
    assert len(urls) == len(set(urls))


def test_parse_agenda_text_numbered_and_lettered_items():
    items = parse_agenda_text(AGENDA_TEXT)
    assert "CALL TO ORDER" in items[0]
    apt = [i for i in items if "Jason Hernandez" in i]
    assert len(apt) == 1
    assert "(OFFICE OF THE MAYOR)" in apt[0]  # continuation line joined
    rz = [i for i in items if "123 Main Street" in i]
    assert len(rz) == 1
    assert "40-unit multifamily" in rz[0]
    assert not any("unrelated trailing" in i for i in items)


def test_collapse_doubled_fake_bold():
    assert collapse_doubled("CCAALLLL TTOO OORRDDEERR normal 22002266") == "CALL TO ORDER normal 2026"
    # non-doubled tokens untouched
    assert collapse_doubled("ROLL CALL 5:30") == "ROLL CALL 5:30"


def test_html_agenda_text_strips_scripts():
    text = html_agenda_text("<div>1. CALL TO ORDER</div><script>var x=1;</script><div>2. ROLL CALL</div>")
    assert "CALL TO ORDER" in text
    assert "var x" not in text
    assert parse_agenda_text(text) == ["CALL TO ORDER", "ROLL CALL"]
