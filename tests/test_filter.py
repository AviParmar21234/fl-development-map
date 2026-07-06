from scraper.filter import classify


def test_rezoning_multifamily():
    r = classify("Ordinance: rezoning of 1200 NW 7th Ave to T6-8-O for a 250-unit multifamily development")
    assert r == {"project_type": "rezoning", "multifamily": True}


def test_site_plan_not_mf():
    r = classify("Site plan approval for retail warehouse at 500 Industrial Way")
    assert r["project_type"] == "site-plan"
    assert r["multifamily"] is False


def test_non_development_returns_none():
    assert classify("Approval of minutes of the June 3 meeting") is None
    assert classify("Proclamation honoring Officer Diaz") is None
    assert classify("Appointment of members to the Planning and Zoning Board") is None


def test_live_local_flags_mf():
    r = classify("Resolution regarding a Live Local Act application for workforce housing, 91 SW 3rd St")
    assert r is not None
    assert r["multifamily"] is True


def test_pud_detected():
    r = classify("Public hearing: Planned Unit Development for 300 townhome units on SR 429")
    assert r["project_type"] == "pud"
    assert r["multifamily"] is True


def test_land_use_amendment():
    r = classify("Small-scale future land use map amendment from Industrial to High Density Residential")
    assert r["project_type"] == "land-use"
    assert r["multifamily"] is True


def test_body_text_used():
    r = classify("Item PZ-5", "Request for special exception to permit a 120-unit apartment building")
    assert r["project_type"] == "special-exception"
    assert r["multifamily"] is True


def test_variance_no_mf():
    r = classify("Variance request for setback reduction, single family home at 12 Palm Ct")
    assert r["project_type"] == "variance"
    assert r["multifamily"] is False


def test_plat():
    r = classify("Final plat approval for Osprey Landing subdivision")
    assert r["project_type"] == "plat"


def test_development_agreement():
    r = classify("First amendment to the development agreement with Brickell Holdings LLC")
    assert r["project_type"] == "development-agreement"
