"""Tests for the Flask app: pages, live results, unit toggle, reports."""

import pytest

import reports

MILL_QUERY = "diameter=0.5&flutes=3&woc=0.25&doc=0.5&sfm=800&chip_load=0.002&max_rpm=10000"


def test_home_goes_to_milling(client):
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/milling")


@pytest.mark.parametrize("path", ["/milling", "/drilling", "/turning",
                                  "/formulas", "/sources", "/report"])
def test_pages_load(client, path):
    assert client.get(path).status_code == 200


def test_unknown_page(client):
    assert client.get("/grinding").status_code == 404


def test_calculator_page_shows_results(client):
    html = client.get(f"/milling?{MILL_QUERY}").get_data(as_text=True)
    assert "<html" in html
    assert "6112" in html


def test_results_partial_is_just_the_panel(client):
    html = client.get(f"/milling/results?{MILL_QUERY}").get_data(as_text=True)
    assert "<html" not in html
    assert "6112" in html


def test_materials_and_presets_listed(client):
    html = client.get("/milling").get_data(as_text=True)
    assert "Test alloy T6" in html
    assert "Test Mill" in html
    assert "Test Lathe" not in html  # lathes only show on the Turning tab


def test_unit_toggle_converts_the_form(client):
    response = client.get(f"/milling?{MILL_QUERY}&units=inch&convert_to=metric")
    assert response.status_code == 302
    location = response.headers["Location"]
    assert "diameter=12.7" in location
    assert "units=metric" in location
    assert "convert_to" not in location


def test_unit_choice_is_remembered(client):
    response = client.get("/formulas?units=metric")
    assert "units=metric" in response.headers.get("Set-Cookie", "")
    html = client.get("/milling").get_data(as_text=True)
    assert ">mm<" in html


def test_sources_page_lists_sources(client):
    assert "Test fixture" in client.get("/sources").get_data(as_text=True)


def test_report_is_saved(client, app):
    response = client.post("/report", data={
        "message": "RPM looks high", "op": "milling", "context": "diameter=0.5", "contact": "",
    })
    assert response.status_code == 302
    rows = reports.list_all(app.config["REPORTS_DATABASE"])
    assert rows[0]["message"] == "RPM looks high"
    assert rows[0]["context"] == "diameter=0.5"


def test_report_needs_a_message(client):
    assert client.post("/report", data={"message": "  "}).status_code == 400


def test_report_honeypot_drops_bots(client, app):
    client.post("/report", data={"message": "spam", "website": "http://spam.example"})
    assert reports.list_all(app.config["REPORTS_DATABASE"]) == []


def test_report_thanks_page(client):
    assert "Thanks" in client.get("/report?sent=1").get_data(as_text=True)
