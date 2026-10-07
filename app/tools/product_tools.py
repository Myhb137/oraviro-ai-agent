from langchain_core.tools import tool
from ..database import search_products, get_product, list_products, DEFAULT_BUSINESS_ID

def get_products():
    """Return the persisted product catalog (legacy helper)."""
    return list_products()

@tool
def Search_product(product_name: str,business_id: str = DEFAULT_BUSINESS_ID):
    """Search real store products by name, category, brand, description, or SKU."""
    return search_products(product_name,business_id)

@tool
def get_product_tool(product_id: str,business_id: str = DEFAULT_BUSINESS_ID):
    """Get a product by its exact store ID."""
    return get_product(product_id,business_id)

@tool
def check_stock(product_id: str,business_id: str = DEFAULT_BUSINESS_ID):
    """Check current stock for a product ID."""
    product = get_product(product_id,business_id)
    return {"product_id": product_id, "stock": product["stock"], "available": product["stock"] > 0} if product else {"error": "Product not found"}
