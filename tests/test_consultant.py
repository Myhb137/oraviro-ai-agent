from app.agent import agent
from app.agent.consultant_fallback import respond
from app.database import list_lead_records
from app.services.consulting import recommend_for_business
from app.services.leads import get_lead_profile, persist_consenting_lead, update_lead_profile
from app.tools.consultant_tools import get_pricing, get_services

def test_published_pricing_tool_returns_official_package_price():
    result = get_pricing.invoke({"query": "Commerce"})
    assert result["packages"][0]["price_dzd"] == 332500

def test_service_lookup_does_not_make_up_unknown_prices():
    result = get_pricing.invoke({"query": "unlisted magic platform"})
    assert result["official_price_available"] is False
    assert get_services.invoke({"query": "AI Customer Support"})[0]["price_dzd"] == 133000

def test_recommendations_match_ecommerce_pains_to_commerce_package():
    result = recommend_for_business("E-commerce", ["Manual product and order questions"], ["Instagram", "WhatsApp"], ["Customer support automation"])
    assert result["package"]["name"] == "Commerce"
    ids = {service["id"] for service in result["services"]}
    assert {"ai-customer-support", "order-management", "inventory-management"} <= ids

def test_lead_persists_only_after_consent_and_required_contact():
    user, conv = "prospect-1", "consult-1"
    update_lead_profile(user, conv, {"industry":"E-commerce", "pain_points":["Manual support"], "contact_name":"Sam"})
    assert not persist_consenting_lead(user, conv)["success"]
    update_lead_profile(user, conv, {"lead_consent":True, "phone":"0550123456"})
    saved = persist_consenting_lead(user, conv)
    assert saved["success"]
    records = list_lead_records()
    assert len(records) == 1 and records[0]["profile"]["contact_name"] == "Sam"

def test_fallback_qualifies_business_and_saves_consenting_lead(monkeypatch):
    monkeypatch.setattr(agent, "_model", lambda: None)
    user, conv = "fallback-prospect", "fallback-consult"
    agent.chat_result("What does Oraviro do?", user, conv)
    agent.chat_result("Online clothing store", user, conv)
    agent.chat_result("Instagram and WhatsApp", user, conv)
    agent.chat_result("Yes", user, conv)
    recommendation = agent.chat_result("About 200 customer messages per day", user, conv)
    assert "Commerce" in recommendation["response"]
    assert "332,500 DZD" in recommendation["response"]
    agent.chat_result("yes", user, conv)
    agent.chat_result("Sam Example", user, conv)
    done = agent.chat_result("sam@example.com", user, conv)
    assert "saved" in done["response"].lower() or "حفظت" in done["response"]
    assert len(list_lead_records()) == 1
    profile = get_lead_profile(user, conv)
    assert profile["lead_status"] in {"QUALIFIED", "HIGH_VALUE"}

def test_consultant_fallback_gives_value_before_pricing_qualification():
    result = respond("How much does Oraviro cost?", "prospect-price", "conv-price", "en")
    assert "depends on what you need to automate" in result[0]
    assert "Starter" not in result[0]
