from scraper.connectors.granicus_mm import parse_agenda, parse_listing

PAGE_URL = "https://bocaraton.granicus.com/ViewPublisher.php?view_id=9"

LISTING_HTML = """
<h2>Upcoming Events</h2>
<table>
<tr class="listingRow">
  <td class="listItem" headers="Name">Planning and Zoning Board</td>
  <td class="listItem" headers="Date">Jul\xa016,\xa02026 - 06:00\xa0PM</td>
  <td class="listItem" id="AgendaLink not Available"></td>
</tr>
</table>
<h2>Available Archives</h2>
<table>
<tr class="listingRow">
  <td class="listItem" headers="Name">Special Meeting</td>
  <td class="listItem" headers="Date">Jun 18, 2026 - 01:20 PM</td>
  <td class="listItem"><a href="//bocaraton.granicus.com/AgendaViewer.php?view_id=9&amp;clip_id=3080">Agenda</a></td>
</tr>
<tr class="listingRow">
  <td class="listItem" headers="Name">C.R.A Regular Meeting</td>
  <td class="listItem" headers="Date">Jun  9, 2026</td>
  <td class="listItem"><a href="//bocaraton.granicus.com/AgendaViewer.php?view_id=9&amp;clip_id=3071">Agenda</a></td>
</tr>
<tr class="listingRow">
  <td class="listItem" headers="Name">Special Meeting</td>
  <td class="listItem" headers="Date">Jun 18, 2026</td>
  <td class="listItem"><a href="//bocaraton.granicus.com/AgendaViewer.php?view_id=9&amp;clip_id=3080">Agenda</a></td>
</tr>
</table>
"""

AGENDA_HTML = """
<table>
<tr><td class="numberspace">1.</td><td>
  <a name="agenda237443" class="Agenda Agenda" href="https://x/MediaPlayer.php?meta_id=237443">CALL TO ORDER:</a>
</td></tr>
<tr><td class="numberspace">4.</td><td>
  <a name="agenda237447" class="Agenda Agenda0" href="https://x/MediaPlayer.php?meta_id=237447">FY 2026-27 BUDGET DISCUSSION:</a>
  <a class="Document Document1" href="https://x/doc">Preliminary Proposed Budget</a>
</td></tr>
<tr><td><a class="Agenda" href="#">   </a></td></tr>
</table>
"""


def test_parse_listing_skips_rows_without_agenda_and_dedups():
    ms = parse_listing(LISTING_HTML, PAGE_URL)
    assert len(ms) == 2
    name, iso, url = ms[0]
    assert name == "Special Meeting"
    assert iso == "2026-06-18"
    # protocol-relative href normalized to absolute https
    assert url == "https://bocaraton.granicus.com/AgendaViewer.php?view_id=9&clip_id=3080"


def test_parse_listing_handles_double_space_dates():
    ms = parse_listing(LISTING_HTML, PAGE_URL)
    assert ms[1] == (
        "C.R.A Regular Meeting",
        "2026-06-09",
        "https://bocaraton.granicus.com/AgendaViewer.php?view_id=9&clip_id=3071",
    )


def test_parse_agenda_items_with_anchors():
    items = parse_agenda(AGENDA_HTML)
    assert items == [
        ("agenda237443", "CALL TO ORDER"),
        ("agenda237447", "FY 2026-27 BUDGET DISCUSSION"),
    ]
