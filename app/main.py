import logging
import hmac
import os
import uuid
from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from .database import (initialize_database, seed_products, list_products, get_product, upsert_product,
    delete_product, list_orders, get_order, add_subscription, list_lead_records,
    DEFAULT_BUSINESS_ID)
from .agent.agent import chat_result
from .channels.formatting import telegram_plain_text

@asynccontextmanager
async def lifespan(app):
    initialize_database(); seed_products()
    yield

app = FastAPI(title="Oraviro API", version="0.1.0", lifespan=lifespan)

def require_admin_key(x_admin_key: str | None = Header(default=None)):
    configured_key = os.getenv("ORAVIRO_ADMIN_API_KEY")
    if not configured_key:
        raise HTTPException(503, "Admin API is not configured")
    if not x_admin_key or not hmac.compare_digest(x_admin_key, configured_key):
        raise HTTPException(401, "Invalid or missing admin API key")

class ChatRequest(BaseModel):
    customer_id: str = Field(min_length=1, max_length=160)
    message: str = Field(min_length=1, max_length=8000)
    conversation_id: str | None = None

class Product(BaseModel):
    id: str = Field(default_factory=lambda: "prod_" + uuid.uuid4().hex[:16])
    name: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    category: str = ""
    category_id: str | None = None
    brand: str = ""
    description: str = ""
    price: float = Field(ge=0)
    stock: int = Field(ge=0)
    compare_at_price: float | None = Field(default=None, ge=0)
    cost_price: float | None = Field(default=None, ge=0)
    active: bool = True
    featured: bool = False

class Subscription(BaseModel):
    customer_id: str
    channel: str = "telegram"
    channel_user_id: str
    subscription_type: str = "new_product"

@app.get("/health")
def health(): return {"status":"ok"}

@app.post("/agent/chat")
def agent_chat(request: ChatRequest): return chat_result(request.message, request.customer_id, request.conversation_id)

@app.get("/products", dependencies=[Depends(require_admin_key)])
def products(): return list_products(DEFAULT_BUSINESS_ID)

@app.post("/products", status_code=201, dependencies=[Depends(require_admin_key)])
def create_product(product: Product):
    data=product.model_dump()
    data.pop("business_id",None)
    try:
        saved=upsert_product(data,DEFAULT_BUSINESS_ID)
    except Exception as exc: raise HTTPException(409,str(exc))
    notify_new_product(saved,DEFAULT_BUSINESS_ID)
    return saved

@app.get("/products/{product_id}", dependencies=[Depends(require_admin_key)])
def product(product_id: str):
    result=get_product(product_id,DEFAULT_BUSINESS_ID)
    if not result: raise HTTPException(404,"Product not found")
    return result

@app.put("/products/{product_id}", dependencies=[Depends(require_admin_key)])
def update_product(product_id: str, product: Product):
    data=product.model_dump(); data["id"]=product_id
    data.pop("business_id",None)
    try: return upsert_product(data,DEFAULT_BUSINESS_ID)
    except Exception as exc: raise HTTPException(409,str(exc))

@app.delete("/products/{product_id}", dependencies=[Depends(require_admin_key)])
def remove_product(product_id: str):
    try: deleted=delete_product(product_id,DEFAULT_BUSINESS_ID)
    except Exception as exc: raise HTTPException(409,str(exc))
    if not deleted: raise HTTPException(404,"Product not found")
    return {"deleted":True}

@app.get("/orders", dependencies=[Depends(require_admin_key)])
def orders(): return list_orders(DEFAULT_BUSINESS_ID)

@app.get("/orders/{order_id}", dependencies=[Depends(require_admin_key)])
def order(order_id: str):
    result=get_order(order_id,business_id=DEFAULT_BUSINESS_ID)
    if not result: raise HTTPException(404,"Order not found")
    return result

@app.get("/customers", dependencies=[Depends(require_admin_key)])
def customers():
    from .database import connect, row_dict
    with connect() as db: return [row_dict(r) for r in db.execute("SELECT * FROM customers WHERE business_id=? ORDER BY created_at DESC",(DEFAULT_BUSINESS_ID,))]

@app.get("/leads", dependencies=[Depends(require_admin_key)])
def leads(): return list_lead_records(DEFAULT_BUSINESS_ID)

@app.post("/subscriptions", status_code=201, dependencies=[Depends(require_admin_key)])
def subscribe(subscription: Subscription):
    data=subscription.model_dump(); data["id"]="sub_"+uuid.uuid4().hex[:16]
    data["business_id"]=DEFAULT_BUSINESS_ID
    subscription_id=add_subscription(data)
    return {"id":subscription_id,"active":True}

@app.delete("/subscriptions/{subscription_id}", dependencies=[Depends(require_admin_key)])
def unsubscribe(subscription_id: str):
    from .database import connect
    with connect() as db: changed=db.execute("UPDATE subscriptions SET active=0 WHERE id=? AND business_id=?",(subscription_id,DEFAULT_BUSINESS_ID)).rowcount
    if not changed: raise HTTPException(404,"Subscription not found")
    return {"active":False}

def notify_new_product(product,business_id=DEFAULT_BUSINESS_ID):
    """Deliver to active Telegram subscriptions when a Telegram token exists."""
    import os, httpx
    token=os.getenv("TELEGRAM_BOT_TOKEN")
    if not token: return {"sent":0,"configured":False}
    from .database import active_subscriptions
    sent=0
    for sub in active_subscriptions(business_id):
        if sub["channel"] != "telegram": continue
        try:
            message = telegram_plain_text(f"🔥 New product available!\n\n{product['name']}\n{product['price']:.0f} DA\n\nAvailable now.")
            httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",json={"chat_id":sub["channel_user_id"],"text":message},timeout=8).raise_for_status()
            sent+=1
        except Exception as exc:
            # HTTP exception text contains the Telegram API URL, which embeds the bot token.
            logging.error("product_notification_failed subscription=%s type=%s",sub["id"],type(exc).__name__)
    return {"sent":sent,"configured":True}
