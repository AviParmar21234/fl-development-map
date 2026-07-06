from datetime import date

from scraper.connectors.escribe import (
    agenda_url,
    map_meeting,
    meeting_iso_date,
    parse_agenda,
    select_meetings,
)

BASE = "https://pub-orlando.escribemeetings.com"

SOURCE = {
    "id": "orlando",
    "name": "City of Orlando",
    "county": "Orange",
    "platform": "escribe",
    "url": BASE + "/",
}

MEETING = {
    "ID": "836b84d8-8eda-4276-a4e8-d70b55696963",
    "MeetingName": "City Council Meeting",
    "MeetingType": "City Council Meeting",
    "StartDate": "2026/06/08 14:00:23",
    "Description": "Hybrid via Zoom<br/>Council Chambers, 2nd Floor<br/>400 S Orange Ave.",
    "Url": BASE + "/MeetingsCalendarView.aspx/Meeting?Id=836b84d8-8eda-4276-a4e8-d70b55696963",
    "Location": "Hybrid via Zoom",
    "HasAgenda": True,
}

# Mirrors the real Meeting.aspx?...&Agenda=Agenda markup: hN headings with
# AgendaItemAgendaItem{N}TitleHeader ids, counter + title divs, optional
# AgendaItemDescription in the surrounding .AgendaItem container.
AGENDA_HTML = """
<html><body>
<div class="AgendaItem AgendaItem8949 ">
 <div class="AgendaItemTitleRow">
  <h3 class="AgendaItemAgendaItem8949TitleHeader" id="AgendaItemAgendaItem8949TitleHeader">
   <div class="AgendaItemCounter">3.a</div>
   <div class="AgendaItemNavigate indent"><div class="AgendaItemTitle">
    <a href="javascript:SelectItem(8949);">Mayor
</a></div></div>
  </h3>
 </div>
</div>
<div class="AgendaItemContainer indent">
 <div class="AgendaItem AgendaItem9840 ">
  <div class="AgendaItemTitleRow">
   <h4 class="AgendaItemAgendaItem9840TitleHeader" id="AgendaItemAgendaItem9840TitleHeader">
    <div class="AgendaItemCounter">3.a.1</div>
    <div class="AgendaItemNavigate indent"><div class="AgendaItemTitle">
     <a href="javascript:SelectItem(9840);">Appointment of Sonia Carnaval as Department Director,
Housing and Community Development
</a></div></div>
   </h4>
  </div>
  <div class="AgendaItemDescription RichText"><div><p>This item appoints the new
  director effective July 1.</p></div></div>
 </div>
</div>
<div class="AgendaItem AgendaItem9999 ">
 <h4 class="AgendaItemAgendaItem9999TitleHeader" id="AgendaItemAgendaItem9999TitleHeader">
  <div class="AgendaItemCounter">9.z</div>
  <div class="AgendaItemTitle"><a href="javascript:SelectItem(9999);">   </a></div>
 </h4>
</div>
</body></html>
"""


def test_meeting_iso_date():
    assert meeting_iso_date(MEETING) == "2026-06-08"
    assert meeting_iso_date({"StartDate": ""}) == ""
    assert meeting_iso_date({}) == ""
    assert meeting_iso_date({"StartDate": "garbage"}) == ""


def test_agenda_url():
    assert agenda_url(BASE, MEETING["ID"]) == (
        BASE + "/Meeting.aspx?Id=836b84d8-8eda-4276-a4e8-d70b55696963&Agenda=Agenda&lang=English"
    )


def test_select_meetings_window_order_and_cap():
    today = date(2026, 7, 6)
    meetings = [
        {"ID": 1, "StartDate": "2026/06/08 14:00:23"},  # 28d back
        {"ID": 2, "StartDate": "2026/07/13 10:00:00"},  # 7d ahead
        {"ID": 3, "StartDate": "2025/11/01 10:00:00"},  # outside lookback
        {"ID": 4, "StartDate": "2026/10/30 10:00:00"},  # outside lookahead
        {"ID": 5, "StartDate": "2026/07/06 09:00:00"},  # today
        {"ID": 6, "StartDate": ""},                     # undated -> skipped
    ]
    picked = select_meetings(meetings, today=today)
    assert [m["ID"] for m in picked] == [5, 2, 1]  # closest-to-today first


def test_parse_agenda_items():
    items = parse_agenda(AGENDA_HTML)
    # blank-title heading 9999 dropped
    assert [it["item_id"] for it in items] == ["8949", "9840"]
    assert items[0]["number"] == "3.a"
    assert items[0]["title"] == "Mayor"
    assert items[0]["body"] == ""
    assert items[1]["number"] == "3.a.1"
    # wrapped title joined onto one line
    assert items[1]["title"] == (
        "Appointment of Sonia Carnaval as Department Director, Housing and Community Development"
    )
    assert items[1]["body"] == "This item appoints the new director effective July 1."


def test_map_meeting_item_level():
    out = map_meeting(SOURCE, BASE, MEETING, parse_agenda(AGENDA_HTML))
    assert len(out) == 2
    item = out[1]
    assert item.source_id == "orlando"
    assert item.jurisdiction == "City of Orlando"
    assert item.county == "Orange"
    assert item.meeting_body == "City Council Meeting"
    assert item.meeting_date == "2026-06-08"
    assert item.title.startswith("Appointment of Sonia Carnaval")
    assert item.body_text == "This item appoints the new director effective July 1."
    assert item.link == agenda_url(BASE, MEETING["ID"]) + "#AgendaItemAgendaItem9840TitleHeader"


def test_map_meeting_fallback_to_meeting_level():
    out = map_meeting(SOURCE, BASE, MEETING, [])
    assert len(out) == 1
    assert out[0].title == "City Council Meeting"
    assert "Council Chambers" in out[0].body_text  # html tags stripped
    assert "<br/>" not in out[0].body_text
    assert out[0].link == MEETING["Url"]


def test_map_meeting_skips_blank_titles():
    out = map_meeting(SOURCE, BASE, MEETING, [{"item_id": "1", "title": "  "},
                                              {"item_id": "2", "title": "Real item"}])
    assert [r.title for r in out] == ["Real item"]
