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


def test_first_seen_carries_forward(tmp_path):
    from scraper.build import load_first_seen
    old = finalize([_item()], today="2026-07-01")
    write_outputs(old, [], str(tmp_path))
    prev = load_first_seen(str(tmp_path))
    out = finalize([_item(), _item(link="https://x/new")], today="2026-07-06", first_seen=prev)
    by_link = {o["link"]: o for o in out}
    assert by_link["https://x/1"]["first_seen"] == "2026-07-01"  # kept from previous run
    assert by_link["https://x/new"]["first_seen"] == "2026-07-06"  # new item stamped today
