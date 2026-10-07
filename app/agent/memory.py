"""Compatibility helpers; customer data is persisted in SQLite."""
from ..database import get_or_create_customer, update_customer

def get_user(user_id):
    customer = get_or_create_customer(user_id)
    return {"product": None, "quantity": None, "full_name": customer["name"], "phone": customer["phone"], "state": customer["address"], "email": None}

def update_user(user_id, field, value):
    fields = {"full_name": "name", "phone": "phone", "state": "address"}
    if field in fields: update_customer(user_id, **{fields[field]: value})

def get_user_data(user_id):
    return get_user(user_id)
