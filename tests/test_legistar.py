from scraper.connectors.legistar import map_items

SOURCE = {"id": "fll", "name": "Fort Lauderdale", "county": "Broward", "legistar_client": "fortlauderdale"}

EVENTS = [
    {"EventId": 1, "EventDate": "2026-08-04T00:00:00", "EventBodyName": "City Commission",
     "EventInSiteURL": "https://fortlauderdale.legistar.com/MeetingDetail.aspx?ID=1"},
]

ITEMS = {1: [
    {"EventItemTitle": "Rezoning of 500 SW 1st Ave to RMM-25", "EventItemMatterId": 777,
     "EventItemMatterFile": "26-0653", "EventItemAgendaNote": "250 multifamily units"},
    {"EventItemTitle": "", "EventItemMatterId": None},  # skipped: no title
    {"EventItemTitle": "Approval of minutes", "EventItemMatterId": None},
]}

WEB_LINKS = {1: {"26-0653": "https://fortlauderdale.legistar.com/LegislationDetail.aspx?ID=8121163&GUID=F86E33AC&Options=&Search="}}


def test_map_items_uses_web_links():
    out = map_items(SOURCE, EVENTS, ITEMS, WEB_LINKS)
    assert len(out) == 2  # empty-title skipped; filtering happens later in pipeline
    first = out[0]
    assert first.link == WEB_LINKS[1]["26-0653"]  # real web-side legislation link
    assert first.meeting_date == "2026-08-04"
    assert first.meeting_body == "City Commission"
    assert first.body_text == "250 multifamily units"
    # unmatched items fall back to the meeting page, which always works
    assert out[1].link == "https://fortlauderdale.legistar.com/MeetingDetail.aspx?ID=1"


def test_insite_file_links():
    from scraper.connectors.legistar import insite_file_links
    html = '<a href="LegislationDetail.aspx?ID=8121163&amp;GUID=F86E&amp;Options=&amp;Search=">26-0653</a>'
    m = insite_file_links(html, "https://fortlauderdale.legistar.com")
    assert m == {"26-0653": "https://fortlauderdale.legistar.com/LegislationDetail.aspx?ID=8121163&GUID=F86E&Options=&Search="}
