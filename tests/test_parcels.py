import json

from scraper import parcels


def test_normalize_parcel_strips_separators():
    assert parcels.normalize_parcel("01-4137-030-0010") == "0141370300010"
    assert parcels.normalize_parcel("16 31 31 67608 004 0070") == "163131676080040070"
    assert parcels.normalize_parcel("18-21-29-502-0d00-0180") == "1821295020D000180"
    assert parcels.normalize_parcel("  474135010090 ") == "474135010090"


def test_normalize_parcel_rejects_garbage():
    assert parcels.normalize_parcel("") is None
    assert parcels.normalize_parcel(None) is None
    assert parcels.normalize_parcel("n/a") is None  # too short
    assert parcels.normalize_parcel("x" * 30) is None  # too long


def test_county_config_tolerant_names():
    assert parcels.county_config("Miami-Dade") is not None
    assert parcels.county_config("Miami-Dade County") is not None
    assert parcels.county_config("broward") is not None
    assert parcels.county_config("Hillsborough") is None  # handled elsewhere
    assert parcels.county_config("") is None
    assert parcels.county_config(None) is None


def test_polygon_centroid_unit_square():
    ring = [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
    lat, lon = parcels.polygon_centroid([ring])
    assert abs(lat - 0.5) < 1e-9 and abs(lon - 0.5) < 1e-9


def test_polygon_centroid_degenerate_falls_back_to_mean():
    ring = [[0, 0], [2, 2], [0, 0]]  # zero-area
    lat, lon = parcels.polygon_centroid([ring])
    assert abs(lon - 2 / 3) < 1e-9 and abs(lat - 2 / 3) < 1e-9
    assert parcels.polygon_centroid([]) is None
    assert parcels.polygon_centroid([[]]) is None


def test_feature_latlon_point_and_polygon():
    assert parcels.feature_latlon({"geometry": {"x": -80.2, "y": 25.8}}) == (25.8, -80.2)
    feat = {"geometry": {"rings": [[[-80.0, 25.0], [-80.0, 25.2], [-80.2, 25.2],
                                    [-80.2, 25.0], [-80.0, 25.0]]]}}
    lat, lon = parcels.feature_latlon(feat)
    assert abs(lat - 25.1) < 1e-9 and abs(lon - (-80.1)) < 1e-9
    assert parcels.feature_latlon({}) is None


def test_resolve_sets_latlon_and_caches(tmp_path, monkeypatch):
    p = tmp_path / "parcelcache.json"
    calls = []

    def fake_fetch(county, parcel_norm):
        calls.append((county, parcel_norm))
        return (25.7755, -80.1950)

    monkeypatch.setattr(parcels, "_fetch", fake_fetch)
    items = [{"parcel": "01-4137-030-0010", "county": "Miami-Dade"}]
    parcels.resolve_parcels(items, cache_path=str(p))
    assert items[0]["lat"] == 25.7755 and items[0]["lon"] == -80.1950
    assert calls == [("Miami-Dade", "0141370300010")]
    cached = json.loads(p.read_text())
    assert cached["Miami-Dade|01-4137-030-0010"] == [25.7755, -80.1950]

    # second run: cache hit, no fetch
    items2 = [{"parcel": "01-4137-030-0010", "county": "Miami-Dade"}]
    parcels.resolve_parcels(items2, cache_path=str(p))
    assert len(calls) == 1
    assert items2[0]["lat"] == 25.7755


def test_resolve_caches_misses(tmp_path, monkeypatch):
    p = tmp_path / "parcelcache.json"
    calls = []
    monkeypatch.setattr(parcels, "_fetch", lambda c, n: calls.append(n) or None)
    items = [{"parcel": "474135010090", "county": "Broward"}]
    parcels.resolve_parcels(items, cache_path=str(p))
    assert "lat" not in items[0]
    assert json.loads(p.read_text())["Broward|474135010090"] is None
    # miss is cached: no second fetch
    parcels.resolve_parcels([{"parcel": "474135010090", "county": "Broward"}],
                            cache_path=str(p))
    assert len(calls) == 1


def test_resolve_skips_unknown_county_existing_coords_and_missing_parcel(tmp_path, monkeypatch):
    monkeypatch.setattr(parcels, "_fetch",
                        lambda c, n: (_ for _ in ()).throw(AssertionError("no fetch")))
    items = [
        {"parcel": "123456789", "county": "Hillsborough"},          # not dispatched
        {"parcel": "0141370300010", "county": "Miami-Dade",
         "lat": 25.0, "lon": -80.0},                                # already resolved
        {"county": "Miami-Dade"},                                   # no parcel
        {"parcel": "0141370300010"},                                # no county
    ]
    parcels.resolve_parcels(items, cache_path=str(tmp_path / "c.json"))
    assert "lat" not in items[0]
    assert items[1]["lat"] == 25.0 and items[1]["lon"] == -80.0


def test_resolve_fetch_errors_do_not_raise(tmp_path, monkeypatch):
    def boom(county, parcel_norm):
        raise RuntimeError("network down")

    monkeypatch.setattr(parcels, "_fetch", boom)
    p = tmp_path / "c.json"
    items = [{"parcel": "262328820300380", "county": "Orange"},
             {"parcel": "253009424000001070", "county": "Polk"}]
    parcels.resolve_parcels(items, cache_path=str(p))  # must not raise
    assert all("lat" not in it for it in items)
    cached = json.loads(p.read_text())
    assert cached["Orange|262328820300380"] is None


def test_out_of_florida_coords_rejected():
    assert parcels._in_florida(25.77, -80.19)
    assert not parcels._in_florida(40.7, -74.0)  # NYC


def test_fetch_builds_query_and_parses_point(monkeypatch):
    seen = {}

    class FakeResp:
        @staticmethod
        def json():
            return {"features": [{"attributes": {"PARCEL_ID": "262328820300380"},
                                  "geometry": {"x": -81.4786, "y": 28.4598}}]}

    def fake_get(url, *, params=None, headers=None):
        seen["url"], seen["params"] = url, params
        return FakeResp()

    monkeypatch.setattr(parcels.http, "get", fake_get)
    coords = parcels._fetch("Orange", "262328820300380")
    assert coords == (28.4598, -81.4786)
    assert seen["url"] == parcels.STATEWIDE_URL
    assert seen["params"]["where"] == "PARCEL_ID='262328820300380' AND CO_NO=58"
    assert seen["params"]["outSR"] == "4326"


def test_fetch_handles_arcgis_error_body(monkeypatch):
    class FakeResp:
        @staticmethod
        def json():
            return {"error": {"code": 400, "message": "bad"}}

    monkeypatch.setattr(parcels.http, "get", lambda url, *, params=None, headers=None: FakeResp())
    assert parcels._fetch("Broward", "474135010090") is None
