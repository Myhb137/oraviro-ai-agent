from app.database import create_order, get_order, get_product
from app.agent.agent import chat_result

def test_order_validates_and_updates_stock():
    result = create_order("customer-a", [{"product_id":"lipstick-red","quantity":2}], "Yahia", "0550123456", "Boufarik, Blida")
    assert result["success"] and get_order(result["order_id"], "customer-a")["status"] == "pending"
    assert get_product("lipstick-red")["stock"] == 40

def test_order_conversation_requires_confirmation():
    user="order-customer"
    chat_result("I want 2 Red Lipstick", user)
    chat_result("Yahia", user); chat_result("0550123456", user); summary=chat_result("Boufarik, Blida", user)
    assert "confirm" in summary["response"].lower()
    assert not __import__("app.database", fromlist=["list_orders"]).list_orders()
    done=chat_result("yes", user)
    assert "ORD-" in done["response"]

def test_customer_order_isolation():
    result=create_order("customer-a", [{"product_id":"lipstick-red","quantity":1}], "Yahia", "0550123456", "Blida")
    assert get_order(result["order_id"], "customer-b") is None

def test_missing_product_is_requested():
    response=chat_result("I want to order", "customer-missing")["response"]
    assert "product" in response.lower()
