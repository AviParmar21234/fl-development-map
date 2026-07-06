import json

from scraper import geocode


def test_cache_roundtrip(tmp_path):
    p = tmp_path / "cache.json"
    cache = geocode.load_cache(str(p))
    assert cache == {}
    cache["1 Main St, Miami, FL"] = [25.7, -80.2]
    cache["bad addr, Nowhere, FL"] = None
    geocode.save_cache(str(p), cache)
    again = geocode.load_cache(str(p))
    assert again["1 Main St, Miami, FL"] == [25.7, -80.2]
    assert again["bad addr, Nowhere, FL"] is None


def test_census_batch_csv():
    rows = geocode.build_batch_csv([("k1", "1200 NW 7th Ave", "Miami"), ("k2", "500 Main St", "Doral")])
    lines = rows.strip().split("\n")
    assert lines[0] == '1,"1200 NW 7th Ave","Miami","FL",""'
    assert lines[1] == '2,"500 Main St","Doral","FL",""'


def test_parse_census_response():
    body = (
        '"1","1200 NW 7th Ave, Miami, FL, ","Match","Exact","1200 NW 7TH AVE, MIAMI, FL, 33136","-80.2085,25.78659","636035","L"\n'
        '"2","500 Main St, Doral, FL, ","No_Match"\n'
    )
    out = geocode.parse_census_response(body)
    assert out["1"] == (25.78659, -80.2085)
    assert out["2"] is None


def test_geocode_all_uses_cache(tmp_path, monkeypatch):
    p = tmp_path / "cache.json"
    geocode.save_cache(str(p), {"1200 NW 7th Ave, Miami, FL": [25.78, -80.20]})
    calls = []
    monkeypatch.setattr(geocode, "_census_batch", lambda batch: calls.append(batch) or {})
    monkeypatch.setattr(geocode, "_nominatim_one", lambda a, c: None)
    items = [{"address": "1200 NW 7th Ave", "jurisdiction": "City of Miami", "city_hint": "Miami", "lat": None, "lon": None}]
    geocode.geocode_all(items, cache_path=str(p))
    assert items[0]["lat"] == 25.78 and items[0]["lon"] == -80.20
    assert calls == []  # cache hit, no network
