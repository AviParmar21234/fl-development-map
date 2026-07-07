import json

from scraper.build import finalize, item_id, write_outputs
from scraper.run import city_hint


def _item(**over):
    base = {
        "source": "miami", "jurisdiction": "City of Miami", "county": "Miami-Dade",
        "meeting_body": "PZAB", "meeting_date": "2026-08-01", "title": "Rezoning at 1 Main St",
        "summary": "", "link": "https://x/1", "project_type": "rezoning", "multifamily": True,
        "address": "1 Main St", "parcel": None, "lat": 25.7, "lon": -80.2,
    }
    base.update(over)
    return base


def test_finalize_dedups_and_stable_ids():
    a, b = _item(), _item()
    out = finalize([a, b], today="2026-07-06")
    assert len(out) == 1
    assert out[0]["id"] == item_id("miami", "https://x/1", "Rezoning at 1 Main St")


def test_status_assignment():
    out = finalize([_item(meeting_date="2026-07-06"), _item(link="https://x/2", meeting_date="2026-01-02")],
                   today="2026-07-06")
    assert out[0]["status"] == "upcoming"
    assert out[1]["status"] == "heard"


def test_write_outputs_splits_mapped(tmp_path):
    items = finalize([_item(), _item(link="https://x/3", lat=None, lon=None)], today="2026-07-06")
    meta = write_outputs(items, [{"source_id": "miami", "ok": True}], str(tmp_path))
    fc = json.loads((tmp_path / "projects.geojson").read_text())
    unmapped = json.loads((tmp_path / "unmapped.json").read_text())
    assert len(fc["features"]) == 1
    assert fc["features"][0]["geometry"]["coordinates"] == [-80.2, 25.7]
    assert len(unmapped) == 1
    assert meta["totals"]["projects_mapped"] == 1


def test_city_hint():
    assert city_hint("City of Miami") == "Miami"
    assert city_hint("Broward County") == ""
    assert city_hint("Doral") == "Doral"


def test_plain_summary():
    from scraper.build import plain_summary
    it = {"project_type": "rezoning", "multifamily": True, "units": 250, "acres": 4.5,
          "address": "1200 NW 7th Ave", "jurisdiction": "City of Fort Lauderdale"}
    assert plain_summary(it) == "Multifamily rezoning · 250 units · 4.5 ac — at 1200 NW 7th Ave, Fort Lauderdale"
    thin = {"project_type": "variance", "multifamily": False, "jurisdiction": "Doral", "parcel": "01-1"}
    assert plain_summary(thin) == "Variance — parcel 01-1, Doral"


def test_finalize_sets_plain():
    out = finalize([_item()], today="2026-07-06")
    assert "Multifamily rezoning" in out[0]["plain"]
    assert "1 Main St" in out[0]["plain"]


def test_polish_promotes_header_titles():
    from scraper.build import polish
    items = [_item(title="NEW BUSINESS", summary="Rezoning of 361 Los Pinos Blvd for townhomes")]
    polish(items)
    assert items[0]["title"].startswith("Rezoning of 361 Los Pinos")


def test_polish_drops_venue_address():
    from scraper.build import polish
    venue = [_item(link=f"https://x/{i}", address="601 City Center Way") for i in range(4)]
    real = [_item(link="https://x/r", address="123 Project Site Rd")]
    items = venue + real
    polish(items)
    assert all(i["address"] is None and i["lat"] is None for i in items[:4])
    assert items[4]["address"] == "123 Project Site Rd"
    assert items[4]["lat"] == 25.7


def test_polish_drops_out_of_county_geocode():
    from scraper.build import polish
    wrong = _item(lat=29.2, lon=-82.1)  # "Miami-Dade" item geocoded near Ocala
    right = _item(link="https://x/ok", lat=25.77, lon=-80.19)
    items = [wrong, right]
    polish(items)
    assert wrong["lat"] is None and wrong["lon"] is None
    assert right["lat"] == 25.77


def test_polish_keeps_parcel_coords_when_venue_dropped():
    from scraper.build import polish
    items = [_item(link=f"https://x/{i}", address="601 City Center Way", parcel="01-4137-030-0010") for i in range(3)]
    polish(items)
    assert all(i["address"] is None and i["lat"] == 25.7 for i in items)


def test_site_stats_groups_by_normalized_address():
    from scraper.build import site_stats
    items = [
        _item(address="110 Phoenetia Avenue", jurisdiction="Coral Gables", meeting_date="2026-08-01"),
        _item(link="https://x/2", address="110 PHOENETIA AVE.", jurisdiction="Coral Gables",
              multifamily=False, meeting_date="2026-01-01"),
        _item(link="https://x/3", address="500 Ocean Dr", jurisdiction="Miami Beach", multifamily=False,
              meeting_date="2026-01-01"),
    ]
    s = site_stats(items, today="2026-07-07")
    assert s["sites"] == 2              # the two Phoenetia spellings are one site
    assert s["mf_sites"] == 1
    assert s["upcoming_sites"] == 1
    assert s["counties"]["Miami-Dade"] == {"sites": 2, "mf": 1, "upcoming": 1}


def test_norm_addr_matches_js_rules():
    from scraper.build import norm_addr
    assert norm_addr("1890 NE 146th Street") == "1890 NE 146TH ST"
    assert norm_addr("110  Phoenetia Avenue.") == "110 PHOENETIA AVE"


def test_first_seen_carries_forward(tmp_path):
    from scraper.build import load_first_seen
    old = finalize([_item()], today="2026-07-01")
    write_outputs(old, [], str(tmp_path))
    prev = load_first_seen(str(tmp_path))
    out = finalize([_item(), _item(link="https://x/new")], today="2026-07-06", first_seen=prev)
    by_link = {o["link"]: o for o in out}
    assert by_link["https://x/1"]["first_seen"] == "2026-07-01"  # kept from previous run
    assert by_link["https://x/new"]["first_seen"] == "2026-07-06"  # new item stamped today
