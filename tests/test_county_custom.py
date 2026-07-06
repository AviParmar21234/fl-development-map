import math
from datetime import date, datetime, timezone

from scraper.connectors.county_custom import parse_broward, parse_hillsborough

TODAY = date(2026, 7, 6)


def ms(y, m, d):
    return int(datetime(y, m, d, 5, tzinfo=timezone.utc).timestamp() * 1000)


HILLS_SOURCE = {
    "id": "hillsborough-dev-tracker",
    "name": "Hillsborough County Zoning Applications",
    "county": "Hillsborough",
}

ARCGIS_PAGE = {
    "spatialReference": {"wkid": 4326, "latestWkid": 4326},
    "features": [
        {  # active, upcoming BOCC + past ZHM -> next upcoming date wins
            "attributes": {"Type_": "RZ-STD", "AppNum": "25-0123", "Inactive": None,
                           "FolioNumb": "35738.0000", "ZHM_Date": ms(2026, 5, 4),
                           "LUHO_Date": None, "BOCC_Date": ms(2026, 8, 10)},
            "geometry": {"x": -82.4378, "y": 28.0721},
        },
        {  # active, only past LUHO within lookback -> most recent past used
            "attributes": {"Type_": "VAR", "AppNum": "26-0456", "Inactive": None,
                           "FolioNumb": None, "ZHM_Date": None,
                           "LUHO_Date": ms(2026, 5, 1), "BOCC_Date": None},
            "geometry": None,
        },
        {  # inactive -> skipped
            "attributes": {"Type_": "SU", "AppNum": "18-0588", "Inactive": "1",
                           "FolioNumb": "1", "BOCC_Date": ms(2026, 8, 10)},
            "geometry": {"x": -82.4, "y": 28.0},
        },
        {  # hearing dates outside 180d-back/365d-forward window -> skipped
            "attributes": {"Type_": "MM", "AppNum": "18-0601", "Inactive": None,
                           "FolioNumb": "2", "LUHO_Date": ms(2018, 5, 21)},
            "geometry": {"x": -82.4, "y": 28.0},
        },
        {  # no hearing dates at all -> skipped
            "attributes": {"Type_": "VAR", "AppNum": "26-0999", "Inactive": None,
                           "FolioNumb": "3"},
            "geometry": {"x": -82.4, "y": 28.0},
        },
        {  # unknown type code -> no parenthetical expansion
            "attributes": {"Type_": "PRS", "AppNum": "26-0777", "Inactive": None,
                           "FolioNumb": "44.0000", "ZHM_Date": ms(2026, 9, 1)},
            "geometry": {"x": -82.5, "y": 27.9},
        },
    ],
}


def test_parse_hillsborough():
    out = parse_hillsborough(HILLS_SOURCE, [ARCGIS_PAGE], today=TODAY)
    assert len(out) == 3
    (item, coords), (item2, coords2), (item3, coords3) = out

    assert item.title == "Zoning application RZ-STD 25-0123 (Standard Rezoning)"
    assert item.meeting_date == "2026-08-10"  # upcoming preferred over past ZHM
    assert item.meeting_body == "Hillsborough DSD Zoning Hearing"
    assert item.body_text == "Folio 35738.0000"
    assert item.link == "https://experience.arcgis.com/experience/870491f64f9744dca53c9f54ed4b7407"
    assert item.county == "Hillsborough"
    assert coords == (28.0721, -82.4378)  # (lat, lon) straight from wkid 4326

    assert item2.title == "Zoning application VAR 26-0456 (Variance)"
    assert item2.meeting_date == "2026-05-01"  # no upcoming -> most recent past
    assert item2.body_text == ""  # no folio
    assert coords2 is None  # no geometry

    assert item3.title == "Zoning application PRS 26-0777"  # unknown code, no expansion
    assert coords3 == (27.9, -82.5)


def test_parse_hillsborough_web_mercator():
    lat, lon = 27.95, -82.45
    r = 6378137.0
    page = {
        "spatialReference": {"wkid": 102100, "latestWkid": 3857},
        "features": [{
            "attributes": {"Type_": "SU", "AppNum": "26-0001", "Inactive": None,
                           "FolioNumb": "9", "BOCC_Date": ms(2026, 8, 1)},
            "geometry": {"x": math.radians(lon) * r,
                         "y": r * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))},
        }],
    }
    [(item, coords)] = parse_hillsborough(HILLS_SOURCE, [page], today=TODAY)
    assert item.title == "Zoning application SU 26-0001 (Special Use)"
    assert abs(coords[0] - lat) < 1e-6 and abs(coords[1] - lon) < 1e-6


BROWARD_SOURCE = {
    "id": "broward-dev-tracker",
    "name": "Broward County LPA Applications",
    "county": "Broward",
    "url": "https://www.broward.org/Planning/Pages/LPA.aspx",
}

# Mirrors the live page: zero-width spaces, nbsp, M/D/YY dates, a meeting-schedule
# table with no NUMBER column, and yearly application tables.
BROWARD_HTML = """
<h2>2026 LPA Meetings:</h2>
<table><tr><td>​Wednesday, May 13, 2026, 2 P.M.</td>
<td><a href="/Planning/Documents/2026/May_13_2026AgendaPackage.pdf">Agenda</a></td></tr></table>
<h2>Local Planning Agency Pending Applications</h2>
<h3>2025​ Applications</h3>
<table>
<tr><td>​NAME</td><td>​TYPE</td><td>​NUMBER</td><td>​LPA HEARING DATE</td><td>​STATUS</td><td>​DOCUMENTS</td></tr>
<tr><td>​Broadview Gardens</td><td>​Zoning Map</td><td>​25-Z2</td><td>​9/10/25</td><td>​Approved</td>
<td><a href="/Planning/Documents/25Z2completeApplication_COPY.pdf">Application &gt;</a></td></tr>
<tr><td>Broadview\xa0Gardens</td><td>Future Land Use Map Amendment</td><td>25-M1</td><td>6/1​1/25</td><td>Approved</td>
<td><a href="/Planning/Documents/25_M1/app.pdf">Application &gt;</a>
<a href="/Planning/Documents/25_M1/25_M1StaffreportFINAL.pdf">​Staff Report &gt;</a></td></tr>
<tr><td>Pending Thing</td><td>Rezoning</td><td>25-Z9</td><td>TBD</td><td>Pending</td><td></td></tr>
<tr><td>​</td><td></td><td></td><td></td><td></td><td></td></tr>
</table>
<table>
<tr><td>NAME</td><td>TYPE</td><td>NUMBER</td><td>LPA HEARING DATE</td><td>STATUS</td><td>DOCUMENTS</td></tr>
<tr><td>2360 NW 6th Street</td><td>Rezoning</td><td>24-Z1</td><td>​8/14​/24</td><td>Approved by the County Commission</td>
<td><a href="/Planning/Documents/24_Z1PublicNotice.pdf">Public Notice &gt;</a>
<a href="/Planning/Documents/24_Z1StaffReport.pdf">Staff Report &gt;</a></td></tr>
</table>
<h3>2023 Applications</h3>
<table>
<tr><td>NAME</td><td>TYPE</td><td>NUMBER</td><td>LPA HEARING DATE</td><td>STATUS</td><td>DOCUMENTS</td></tr>
<tr><td>Old One</td><td>Rezoning</td><td>23-Z6</td><td>11/8/2023</td><td>Withdrawn</td>
<td><a href="/Planning/Documents/23_Z6.pdf">Staff Report &gt;</a></td></tr>
</table>
"""


def test_parse_broward():
    out = parse_broward(BROWARD_SOURCE, BROWARD_HTML, today=date(2025, 7, 1))
    items = [item for item, coords in out]
    assert all(coords is None for _item, coords in out)
    assert [i.title for i in items] == [
        "Zoning Map 25-Z2: Broadview Gardens",
        "Future Land Use Map Amendment 25-M1: Broadview Gardens",
        "Rezoning 25-Z9: Pending Thing",
        "Rezoning 24-Z1: 2360 NW 6th Street",
    ]  # 23-Z6 dropped (older than previous year); meetings table + blank row ignored

    z2, m1, z9, z1 = items
    assert z2.meeting_date == "2025-09-10"
    assert z2.link == "https://www.broward.org/Planning/Documents/25Z2completeApplication_COPY.pdf"
    assert z2.meeting_body == "Broward County Local Planning Agency"
    assert z2.body_text == "Approved"

    assert m1.meeting_date == "2025-06-11"  # zero-width space inside the date
    assert m1.link == "https://www.broward.org/Planning/Documents/25_M1/25_M1StaffreportFINAL.pdf"  # staff report preferred

    assert z9.meeting_date == ""  # unparseable "TBD"
    assert z9.link == BROWARD_SOURCE["url"]  # no PDF -> page link

    assert z1.meeting_date == "2024-08-14"
    assert z1.link == "https://www.broward.org/Planning/Documents/24_Z1StaffReport.pdf"
