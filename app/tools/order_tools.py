from langchain_core.tools import tool
from ..database import get_order, DEFAULT_BUSINESS_ID

@tool
def get_order_status(order_id: str, customer_id: str,business_id: str = DEFAULT_BUSINESS_ID):
    """Retrieve an order only when it belongs to this customer ID."""
    order = get_order(order_id, customer_id, business_id)
    return {"order_id": order_id, "status": order["status"]} if order else {"error": "Order not found for this customer"}

# Retained import name for older prototype callers. Real order placement is handled
# by the agent service after its explicit confirmation gate.
Order_tool = get_order_status
