from app.agent import agent
from app.agent.fallback import respond
from app.database import active_subscriptions, add_subscription, search_products

def test_fallback_shows_real_catalog_for_arabic_all_request():
    response, calls = respond("الكل من فضلك")
    assert "Red Lipstick" in response
    assert "Black Hoodie" in response
    assert "1,200 DZD" in response
    assert calls[0]["tool"] == "list_products"

def test_fallback_explains_unavailable_skincare_category():
    response, _ = respond("عناية")
    assert "ما عندناش منتجات" in response
    assert "Makeup" in response

def test_fallback_matches_darija_lipstick_question():
    response, calls = respond("سلام، كاين روج أحمر؟")
    assert "Red Lipstick" in response
    assert "42" in response
    assert [c["tool"] for c in calls] == ["search_products", "check_stock"]

def test_chat_uses_fallback_when_llm_fails(monkeypatch):
    def fail_model():
        raise RuntimeError("model unavailable")
    monkeypatch.setattr(agent, "_model", fail_model)
    result = agent.chat_result("What does Oraviro do?", "fallback-customer")
    assert "digital systems" in result["response"]
    assert "What type of business" in result["response"]

def test_telegram_customer_can_subscribe_to_new_product_alerts():
    agent.chat_result("Notify me when you add a new product", "telegram_12345")
    subscriptions = active_subscriptions()
    assert len(subscriptions) == 1
    assert subscriptions[0]["channel_user_id"] == "12345"

def test_new_product_notification_sends_to_subscriber(monkeypatch):
    import httpx
    from app.main import notify_new_product
    add_subscription({"id":"sub-test", "customer_id":"telegram_12345", "channel":"telegram", "channel_user_id":"12345", "subscription_type":"new_product"})
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    calls=[]
    class Response:
        def raise_for_status(self): pass
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: (calls.append((args,kwargs)) or Response()))
    result=notify_new_product({"name":"Sample Product","price":1000})
    assert result == {"sent":1,"configured":True}
    assert calls and calls[0][1]["json"]["chat_id"] == "12345"

def test_creating_product_through_api_triggers_notification(monkeypatch):
    import httpx
    from fastapi.testclient import TestClient
    from app.main import app
    add_subscription({"id":"sub-api-test", "customer_id":"telegram_54321", "channel":"telegram", "channel_user_id":"54321", "subscription_type":"new_product"})
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test-token")
    calls=[]
    class Response:
        def raise_for_status(self): pass
    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: (calls.append(kwargs["json"]) or Response()))
    with TestClient(app) as client:
        response=client.post("/products", json={"id":"expo-product","name":"Expo Tote","sku":"EXPO-001","category":"Accessories","brand":"Oraviro","description":"Canvas tote bag","price":1800,"stock":12})
    assert response.status_code == 201
    assert len(calls) == 1
    assert "Expo Tote" in calls[0]["text"]
