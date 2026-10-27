from lead_finder.clean import dedupe, finalize, rank_emails
from lead_finder.models import Business


def biz(**kw) -> Business:
    return Business(osm_type="node", osm_id=kw.pop("osm_id", 1), name=kw.pop("name", "Acme"), **kw)


def test_rank_prefers_own_domain_then_generic_inbox():
    emails = ["acme.hvac@gmail.com", "john@acmehvac.com", "info@acmehvac.com"]
    assert rank_emails(emails, "https://www.acmehvac.com") == [
        "info@acmehvac.com", "john@acmehvac.com", "acme.hvac@gmail.com",
    ]


def test_finalize_prefers_osm_email_and_merges_phones():
    b = biz(website="https://acmehvac.com", osm_emails=["Owner@AcmeHVAC.com"], osm_phones=["(305) 555-0142"],
            site_emails=["info@acmehvac.com"], site_phones=["+13055550142", "+13055550199"])
    finalize(b)
    assert (b.best_email, b.email_source) == ("owner@acmehvac.com", "osm")
    assert b.all_emails == ["info@acmehvac.com", "owner@acmehvac.com"]
    assert b.best_phone == "+13055550142"
    assert b.all_phones == ["+13055550142", "+13055550199"]


def test_finalize_falls_back_to_website_email():
    b = biz(website="https://acmehvac.com", site_emails=["sales@acmehvac.com", "info@acmehvac.com"])
    finalize(b)
    assert (b.best_email, b.email_source) == ("info@acmehvac.com", "website")


def test_finalize_without_contacts():
    b = finalize(biz())
    assert b.best_email == "" and b.email_source == "" and b.best_phone == ""


def test_dedupe_by_domain_and_name_city():
    items = [
        biz(osm_id=1, name="Acme HVAC", city="Miami", website="https://acmehvac.com"),
        biz(osm_id=2, name="Acme Heating & Air", city="Doral", website="https://www.acmehvac.com/"),
        biz(osm_id=3, name="acme hvac", city="miami"),
        biz(osm_id=4, name="Acme HVAC", city="Tampa"),
    ]
    assert [b.osm_id for b in dedupe(items)] == [1, 4]
