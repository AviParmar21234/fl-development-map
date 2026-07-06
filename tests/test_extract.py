from scraper.extract import extract_location


def test_simple_address():
    assert extract_location("rezoning of property at 1200 NW 7th Avenue, Miami")["address"] == "1200 NW 7th Avenue"


def test_folio():
    assert extract_location("Folio No. 01-4137-030-0010")["parcel"] == "01-4137-030-0010"


def test_no_address():
    r = extract_location("Discussion of the comprehensive plan generally")
    assert r["address"] is None
    assert r["parcel"] is None


def test_address_range_and_suffixes():
    assert extract_location("located at 3500-3520 Biscayne Blvd")["address"] == "3500-3520 Biscayne Blvd"


def test_directional_after_name():
    assert extract_location("property at 401 SW 2nd St for a PUD")["address"] == "401 SW 2nd St"


def test_highway():
    assert extract_location("parcel on 4600 US Highway 27")["address"] == "4600 US Highway 27"


def test_both_address_and_parcel():
    r = extract_location("1200 Brickell Bay Drive (Folio 01-4139-035-0010) rezoning")
    assert r["address"] == "1200 Brickell Bay Drive"
    assert r["parcel"] == "01-4139-035-0010"


def test_ignores_ordinance_numbers():
    r = extract_location("Ordinance No. 2026-14 amending Chapter 62")
    assert r["address"] is None


def test_multiword_street_name():
    assert extract_location("at 7811 Coral Way, Miami FL")["address"] == "7811 Coral Way"


def test_all_caps_miami_style():
    r = extract_location("LOCATED AT APPROXIMATELY 5135 NW 7 STREET, MIAMI, FLORIDA")
    assert r["address"] == "5135 NW 7 STREET"


def test_intel_units_acres_applicant():
    from scraper.extract import extract_intel
    r = extract_intel("rezoning of a 4.5-acre site for a 250-unit multifamily development, Applicant: Brickell Holdings LLC")
    assert r["units"] == 250
    assert r["acres"] == 4.5
    assert r["applicant"] == "Brickell Holdings LLC"


def test_intel_absent():
    from scraper.extract import extract_intel
    r = extract_intel("Approval of a development agreement generally")
    assert r == {"units": None, "acres": None, "applicant": None}


def test_opportunity_score():
    from scraper.extract import opportunity_score
    hot = {"multifamily": True, "units": 300, "acres": 5.0, "project_type": "rezoning", "status": "upcoming"}
    cold = {"multifamily": False, "units": None, "acres": None, "project_type": "variance", "status": "heard"}
    assert opportunity_score(hot) == 8
    assert opportunity_score(cold) == 0
