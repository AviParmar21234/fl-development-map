from datetime import date

from scraper.connectors.civicclerk import (
    event_link,
    map_event,
    parse_agenda_text,
    pick_agenda_file_id,
    select_events,
    tenant_from_url,
)

SOURCE = {
    "id": "jupiter",
    "name": "Jupiter",
    "county": "Palm Beach",
    "platform": "civicclerk",
    "url": "https://jupiterfl.api.civicclerk.com",
}

EVENT = {
    "id": 1486,
    "eventName": "Town Council Meeting",
    "eventDescription": "Regular session",
    "startDateTime": "2026-05-05T19:00:00Z",
    "eventDate": "2026-05-05T19:00:00Z",
    "categoryName": "Town Council",
    "eventCategoryName": "Town Council",
    "hasAgenda": True,
    "publishedFiles": [
        {"fileId": 1925, "type": "Agenda", "name": "05052026 TC AGENDA"},
        {"fileId": 1926, "type": "Agenda Packet", "name": "05052026 TC PACKET"},
        {"fileId": 1955, "type": "Minutes", "name": "05052026 TC MINUTES"},
    ],
}

AGENDA_TEXT = """\

                                  AGENDA
                             TOWN OF JUPITER
                          TOWN COUNCIL MEETING
                           TUESDAY, MAY 5, 2026
                                   7:00 PM
Call To Order

Invocation; Moment of Silence; and Pledge of Allegiance

                              PROCLAMATION
1.  National Drinking Water Week, May 3 - May 9, 2026. #

2.  Historic Preservation Month. #

                               PRESENTATION
3.  Update on Ongoing Scams in the County - Palm Beach County Clerk of Court and
    Comptroller, Mike Caruso. #

4.  Drop Savers Poster Contest Awards.

                             CITIZEN COMMENTS
All Non-agenda items are limited to three (3) minutes. Anyone wishing to speak is asked
to state his/her name and address for the record prior to addressing the Town Council.

5.  CONSENT AGENDA
5.A Approval of Minutes - June 16, 2026
5.B Award of Contract for Road Resurfacing
"""


def test_tenant_from_url():
    assert tenant_from_url("https://jupiterfl.api.civicclerk.com") == "jupiterfl"
    assert tenant_from_url("https://kissimmeefl.api.civicclerk.com/") == "kissimmeefl"


def test_event_link():
    assert event_link("jupiterfl", 1486) == "https://jupiterfl.portal.civicclerk.com/event/1486/overview"


def test_pick_agenda_file_id():
    assert pick_agenda_file_id(EVENT) == 1925  # 'Agenda', not the packet or minutes
    assert pick_agenda_file_id({"publishedFiles": []}) is None
    assert pick_agenda_file_id({}) is None


def test_parse_agenda_text():
    items = parse_agenda_text(AGENDA_TEXT)
    titles = [i["title"] for i in items]
    assert titles == [
        "National Drinking Water Week, May 3 - May 9, 2026.",  # trailing '#' stripped
        "Historic Preservation Month.",
        "Update on Ongoing Scams in the County - Palm Beach County Clerk of Court and Comptroller, Mike Caruso.",  # wrapped line joined
        "Drop Savers Poster Contest Awards.",
        "CONSENT AGENDA",
        "Approval of Minutes - June 16, 2026",  # sub-item split from parent, kissimmee style
        "Award of Contract for Road Resurfacing",
    ]
    assert items[0]["section"] == "PROCLAMATION"
    assert items[2]["section"] == "PRESENTATION"
    assert items[0]["number"] == "1"
    assert items[5]["number"] == "5.A"
    # section headers and boilerplate prose are not items
    assert all("CITIZEN" not in t for t in titles)


def test_map_event_item_level():
    items = parse_agenda_text(AGENDA_TEXT)
    out = map_event(SOURCE, "jupiterfl", EVENT, items)
    assert len(out) == 7
    first = out[0]
    assert first.source_id == "jupiter"
    assert first.jurisdiction == "Jupiter"
    assert first.county == "Palm Beach"
    assert first.meeting_body == "Town Council"
    assert first.meeting_date == "2026-05-05"
    assert first.title == "National Drinking Water Week, May 3 - May 9, 2026."
    assert first.body_text == ""
    assert first.link == "https://jupiterfl.portal.civicclerk.com/event/1486/overview"


def test_map_event_fallback_to_event_level():
    out = map_event(SOURCE, "jupiterfl", EVENT, [])
    assert len(out) == 1
    assert out[0].title == "Town Council Meeting"
    assert out[0].body_text == "Regular session"
    assert out[0].meeting_body == "Town Council"


def test_map_event_skips_blank_titles():
    out = map_event(SOURCE, "jupiterfl", EVENT, [{"title": "   "}, {"title": "Real item"}])
    assert [r.title for r in out] == ["Real item"]


def test_select_events_window_priority_and_cap():
    today = date(2026, 7, 6)
    events = [
        {"id": 1, "startDateTime": "2026-07-01T19:00:00Z"},   # 5 days back
        {"id": 2, "startDateTime": "2026-07-20T19:00:00Z"},   # 14 days ahead
        {"id": 3, "startDateTime": "2026-02-01T19:00:00Z"},   # inside 180d lookback
        {"id": 4, "startDateTime": "2025-12-01T19:00:00Z"},   # outside window (past)
        {"id": 5, "startDateTime": "2026-10-30T19:00:00Z"},   # outside window (future)
        {"id": 6, "startDateTime": "2026-07-06T09:00:00Z"},   # today
    ]
    picked = select_events(events, today=today)
    assert [e["id"] for e in picked] == [6, 1, 2, 3]  # closest-to-today first
