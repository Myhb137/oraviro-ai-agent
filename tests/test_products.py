from app.database import search_products, get_product
from app.agent.agent import chat_result
from app.services.consulting import company_knowledge, find_offerings

def test_catalog_search_returns_real_seed_data():
    p = search_products("red lipstick")
    assert p and p[0]["price"] == 1200 and p[0]["stock"] == 42

def test_oraviro_consultant_explains_company():
    result = chat_result("What does Oraviro do?", "customer-a")
    assert "digital systems" in result["response"]
    assert "What type of business" in result["response"]

def test_official_package_pricing_is_loaded_from_knowledge():
    data = company_knowledge()
    package = next(p for p in data["packages"] if p["id"] == "pkg-commerce")
    assert package["price_dzd"] == 332500
    assert find_offerings("Growth")["packages"][0]["price_dzd"] == 239400


def test_groq_default_model_is_supported(monkeypatch):
    from app.agent import agent
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    model = agent._model()
    assert model.model_name == "llama-3.1-8b-instant"
