import pytest

from lead_finder.osm import build_query, parse_elements, parse_tag


def test_build_query_includes_area_and_all_tags():
    q = build_query("Florida", [("craft", "hvac"), ("shop", "hvac")], admin_level=4)
    assert 'area["name"="Florida"]["boundary"="administrative"]["admin_level"="4"]->.a;' in q
    assert 'nwr["craft"="hvac"](area.a);' in q
    assert 'nwr["shop"="hvac"](area.a);' in q
    assert q.startswith("[out:json]") and "out tags center;" in q


@pytest.mark.parametrize("area", ['Flo"rida', "a\\b", "line\nbreak"])
def test_build_query_rejects_injection(area):
    with pytest.raises(ValueError):
        build_query(area, [("craft", "hvac")])


def test_build_query_requires_tags():
    with pytest.raises(ValueError):
        build_query("Florida", [])


def test_parse_tag():
    assert parse_tag(" office = lawyer ") == ("office", "lawyer")
    with pytest.raises(ValueError):
        parse_tag("office")


def test_parse_elements():
    elements = [
        {
            "type": "node", "id": 1, "lat": 25.7, "lon": -80.2,
            "tags": {
                "name": "Cool Air Inc", "website": "coolair.com", "phone": "+1 305 555 0100; 305-555-0101",
                "email": "info@coolair.com", "addr:housenumber": "12", "addr:street": "Main St",
                "addr:city": "Miami", "addr:state": "FL", "addr:postcode": "33101",
            },
        },
        {"type": "way", "id": 2, "center": {"lat": 27.9, "lon": -82.4},
         "tags": {"name": "Bay HVAC", "contact:website": "https://bayhvac.com"}},
        {"type": "node", "id": 3, "tags": {"craft": "hvac"}},  # unnamed -> skipped
    ]
    businesses = parse_elements(elements, "hvac")
    assert [b.name for b in businesses] == ["Cool Air Inc", "Bay HVAC"]
    first, second = businesses
    assert first.website == "https://coolair.com"
    assert first.osm_phones == ["+1 305 555 0100", "305-555-0101"]
    assert first.osm_emails == ["info@coolair.com"]
    assert first.address == "12 Main St" and first.city == "Miami"
    assert first.osm_url == "https://www.openstreetmap.org/node/1"
    assert second.website == "https://bayhvac.com"
    assert (second.lat, second.lon) == (27.9, -82.4)
