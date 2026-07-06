from datetime import date

from scraper.connectors.onbase import (
    extract_search_json,
    item_link,
    map_meeting,
    parse_agenda,
    select_meetings,
)

BASE = "https://tampagov.hylandcloud.com/251agendaonline"

SOURCE = {
    "id": "tampa",
    "name": "City of Tampa",
    "county": "Hillsborough",
    "platform": "onbase",
    "url": BASE + "/",
}

SEARCH_HTML = """
<html><body>
<script>
    showSearchResults(new SearchResults({"MeetingTypes":[{"ID":"104","Name":"Council Regular","DisplayName":"Council Regular"}],
    "Meetings":[
      {"ID":2654,"Name":"City Council Regular - June 18, 2026","MeetingTypeName":"Council Regular",
       "IsAgendaAvailable":true,"Time":"2026-06-18T09:00:00-04:00","Documents":[],"LatestDocumentType":1},
      {"ID":2933,"Name":"City Council Reguar - October 1, 2026","MeetingTypeName":"Council Regular",
       "IsAgendaAvailable":false,"Time":"2026-10-01T09:00:00-04:00","Documents":[],"LatestDocumentType":1}
    ],"NoMoreResults":false,"HasError":false}));
</script>
</body></html>
"""

# Mirrors the real Documents/ViewAgenda markup: item bookmark anchor + title
# link inside the first <p> of a table cell, description paragraphs after it.
AGENDA_HTML = """
<html><body>
<table><tr><td>
  <p><a name="S12480"></a><a href="javascript:loadAgendaItem(12480,true);">PUBLIC HEARINGS</a></p>
</td></tr></table>
<table><tr>
 <td><p><span>5.</span></p></td>
 <td>
  <p><a name="I24195"></a><a href="javascript:loadAgendaItem(24195,false);"><span>File No. VAC-26-09</span></a></p>
  <p><span>Continued Public Hearing</span><span> on application by Ybor Nuccio, LLC requesting to vacate
     alleys lying South of E. 5th Avenue, West of N. 22nd Street</span></p>
  <p><span>&#xa0;</span></p>
  <p><span>(Ordinance being presented for first reading consideration)</span></p>
 </td>
</tr></table>
<table><tr>
 <td><p><span>6.</span></p></td>
 <td>
  <p><a name="I24205"></a><a href="javascript:loadAgendaItem(24205,false);"><span>File No. REZ-26-22</span></a></p>
  <p><span>Rezoning from Light Industrial (LI) to urban Mixed Use-60 (UMU-60)</span></p>
 </td>
</tr></table>
<table><tr>
 <td>
  <p><a name="I99999"></a></p>
 </td>
</tr></table>
</body></html>
"""


def test_extract_search_json():
    data = extract_search_json(SEARCH_HTML)
    assert len(data["Meetings"]) == 2
    assert data["Meetings"][0]["ID"] == 2654
    assert data["Meetings"][0]["MeetingTypeName"] == "Council Regular"


def test_extract_search_json_no_results_marker():
    assert extract_search_json("<html><body>no meetings here</body></html>") == {}
    assert extract_search_json("") == {}


def test_select_meetings_window_agenda_flag_and_order():
    today = date(2026, 7, 6)
    meetings = [
        {"ID": 1, "IsAgendaAvailable": True, "Time": "2026-06-18T09:00:00-04:00"},   # 18d back
        {"ID": 2, "IsAgendaAvailable": True, "Time": "2026-07-08T13:00:00-04:00"},   # 2d ahead
        {"ID": 3, "IsAgendaAvailable": False, "Time": "2026-07-07T09:00:00-04:00"},  # no agenda -> skipped
        {"ID": 4, "IsAgendaAvailable": True, "Time": "2025-11-01T09:00:00-04:00"},   # outside window
        {"ID": 5, "IsAgendaAvailable": True, "Time": "2026-10-30T09:00:00-04:00"},   # outside window
        {"ID": 6, "IsAgendaAvailable": True, "Time": "2026-02-01T09:00:00-05:00"},   # inside lookback
    ]
    picked = select_meetings(meetings, today=today)
    assert [m["ID"] for m in picked] == [2, 1, 6]  # closest-to-today first


def test_parse_agenda_items_titles_and_bodies():
    items = parse_agenda(AGENDA_HTML)
    # section anchors (S...) and title-less bookmarks are not items
    assert [it["item_id"] for it in items] == ["24195", "24205"]
    assert items[0]["title"] == "File No. VAC-26-09"
    assert "requesting to vacate" in items[0]["body"]
    assert "(Ordinance being presented for first reading consideration)" in items[0]["body"]
    assert "File No. VAC-26-09" not in items[0]["body"]  # title paragraph excluded
    assert items[1]["title"] == "File No. REZ-26-22"
    assert items[1]["body"] == "Rezoning from Light Industrial (LI) to urban Mixed Use-60 (UMU-60)"


def test_item_link():
    assert item_link(BASE, 2654, "24195") == (
        BASE + "/Meetings/ViewMeetingAgendaItem?meetingId=2654"
               "&itemId=24195&isSection=False&type=agenda"
    )


def test_map_meeting_item_level():
    meeting = {"ID": 2654, "Name": "City Council Regular - June 18, 2026",
               "MeetingTypeName": "Council Regular", "Time": "2026-06-18T09:00:00-04:00"}
    out = map_meeting(SOURCE, BASE, meeting, parse_agenda(AGENDA_HTML))
    assert len(out) == 2
    first = out[0]
    assert first.source_id == "tampa"
    assert first.jurisdiction == "City of Tampa"
    assert first.county == "Hillsborough"
    assert first.meeting_body == "Council Regular"
    assert first.meeting_date == "2026-06-18"
    assert first.title == "File No. VAC-26-09"
    assert "Ybor Nuccio" in first.body_text
    assert first.link == item_link(BASE, 2654, "24195")


def test_map_meeting_no_items_yields_nothing():
    # meeting-name-only RawItems carry no project signal -> skip entirely
    meeting = {"ID": 2933, "Name": "City Council Regular - October 1, 2026",
               "MeetingTypeName": "Council Regular", "Time": "2026-10-01T09:00:00-04:00"}
    assert map_meeting(SOURCE, BASE, meeting, []) == []
