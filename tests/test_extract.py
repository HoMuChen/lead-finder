from pathlib import Path

from lead_finder.extract import decode_cfemail, is_valid_email, normalize_phone, parse_page

HOME = (Path(__file__).parent / "fixtures" / "home.html").read_text()
URL = "https://www.sunshinecooling.com/"


def test_emails_from_mailto_cloudflare_and_text_with_junk_filtered():
    emails = parse_page(HOME, URL, "US")["emails"]
    assert emails[0] == "service@sunshinecooling.com"  # mailto, lowercased, query string dropped
    assert "info@sunshinecooling.com" in emails  # Cloudflare-protected address decoded
    assert not any("example.com" in e or "sentry" in e or e.endswith(".png") for e in emails)


def test_phones_normalized_to_e164_tel_links_first():
    phones = parse_page(HOME, URL, "US")["phones"]
    assert phones[0] == "+13055550142"
    assert "+13055550199" in phones
    assert len(phones) == len(set(phones))


def test_socials_skip_share_buttons():
    socials = parse_page(HOME, URL, "US")["socials"]
    assert socials == {
        "facebook": "https://www.facebook.com/sunshinecoolingmiami",
        "instagram": "https://instagram.com/sunshinecooling/",
        "linkedin": "https://www.linkedin.com/company/sunshine-cooling",
    }


def test_social_query_kept_only_for_profile_php():
    html = ('<a href="https://www.facebook.com/profile.php?id=1000123">fb</a>'
            '<a href="https://www.instagram.com/acme/?utm_source=site">ig</a>')
    socials = parse_page(html, URL, "US")["socials"]
    assert socials["facebook"] == "https://www.facebook.com/profile.php?id=1000123"
    assert socials["instagram"] == "https://www.instagram.com/acme/"


def test_contact_pages_same_site_only():
    pages = parse_page(HOME, URL, "US")["contact_pages"]
    assert pages == ["https://www.sunshinecooling.com/contact-us/", "https://www.sunshinecooling.com/about"]


def test_malformed_links_are_ignored():
    html = '<a href="http://[request-service-menu-url]">Contact</a><a href="https://[bad]/x">fb</a><a href="/contact">Contact</a>'
    found = parse_page(html, URL, "US")
    assert found["contact_pages"] == ["https://www.sunshinecooling.com/contact"]
    assert found["socials"] == {}


def test_decode_cfemail():
    assert decode_cfemail("1b72757d745b686e75687372757e7874747772757c35787476") == "info@sunshinecooling.com"
    assert decode_cfemail("zz") == ""


def test_is_valid_email():
    assert is_valid_email("owner@acme-hvac.com")
    assert not is_valid_email("icon@2x.png")
    assert not is_valid_email("you@example.com")
    assert not is_valid_email("0123456789abcdef0123@acme.com")
    assert not is_valid_email("not-an-email")


def test_normalize_phone():
    assert normalize_phone("(305) 555-0142", "US") == "+13055550142"
    assert normalize_phone("+44 20 7946 0958", "US") == "+442079460958"
    assert normalize_phone("12345", "US") == ""
    assert normalize_phone("call us", "US") == ""
