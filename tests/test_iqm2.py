from scraper.connectors.iqm2 import parse_calendar, parse_meeting

CAL_HTML = """
<div><a href="Detail_Meeting.aspx?ID=4305">May 28, 2026 6:00 PM</a></div>
<div><a href="/Citizens/Detail_Meeting.aspx?ID=4310&Type=1">Jan 5, 2026 9:00 AM</a></div>
<div><a href="Detail_Meeting.aspx?ID=4305">May 28, 2026 6:00 PM</a></div>
"""

MEETING_HTML = """
<html><head><title>
\t2026/05/28 06:00 PM Public Art Professional Advisory Committee Regular Meeting - Web Outline - Miami, FL</title></head>
<body><table>
<tr><td class='Num'>1. </td><td class='Title' colspan='9'><a target='_top' class='Link'
href='Detail_LegiFile.aspx?Frame=&MeetingID=4305&MediaPosition=&ID=19366&CssClass='>A RESOLUTION ... AT 5135 NW 7 STREET, MIAMI</a></td></tr>
</table></body></html>
"""


def test_parse_calendar_dedup_and_dates():
    ms = parse_calendar(CAL_HTML)
    assert ms == [("4305", "2026-05-28"), ("4310", "2026-01-05")]


def test_parse_meeting():
    body, items = parse_meeting(MEETING_HTML, "https://miamifl.iqm2.com")
    assert body == "Public Art Professional Advisory Committee Regular Meeting"
    assert len(items) == 1
    link, title = items[0]
    assert link.startswith("https://miamifl.iqm2.com/Citizens/Detail_LegiFile.aspx?")
    assert "5135 NW 7 STREET" in title
