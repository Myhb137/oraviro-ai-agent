"""Verified Ora Viro catalog lookup and deterministic package matching."""
import json
from pathlib import Path

KNOWLEDGE_PATH = Path(__file__).resolve().parents[1] / "knowledge" / "oraviro.json"


def company_knowledge():
    return json.loads(KNOWLEDGE_PATH.read_text(encoding="utf-8"))


def find_offerings(query=""):
    data = company_knowledge()
    query = query.strip().lower()
    if not query:
        return {"packages": data["packages"], "services": data["services"]}
    packages = [p for p in data["packages"] if query in p["name"].lower() or query in p["summary"].lower() or query in p["fit"].lower()]
    services = [s for s in data["services"] if query in s["name"].lower() or query in s["category"].lower() or query in s.get("summary", "").lower()]
    return {"packages": packages, "services": services}


def recommend_for_business(industry="", problems=None, channels=None, needs=None):
    data = company_knowledge()
    context = " ".join([industry, *(problems or []), *(channels or []), *(needs or [])]).lower()
    rules = data["recommendation_rules"]
    matched = []
    if any(term in context for term in ("e-commerce", "ecommerce", "online store", "shop", "retail", "inventory", "orders", "order processing", "store")):
        matched.append("e_commerce")
    if any(term in context for term in ("lead", "prospect", "sales", "follow-up", "follow up", "crm", "qualification")):
        matched.append("lead_management")
    if any(term in context for term in ("support", "customer questions", "customer service", "faq", "messages", "inquiries", "inquiries")):
        matched.append("customer_support")
    if any(term in context for term in ("manual", "repetitive", "workflow", "automation", "copy paste", "copy-paste")):
        matched.append("repetitive_operations")
    if any(term in context for term in ("finance", "branches", "end-to-end", "business system", "multiple departments")):
        matched.append("connected_operations")
    matched = list(dict.fromkeys(matched))
    if not matched:
        return {"enough_information": False, "follow_up": "What repetitive task or customer workflow takes the most time in your business?", "services": [], "package": None}

    service_ids = list(dict.fromkeys(sid for key in matched for sid in rules[key]["service_ids"]))
    service_index = {s["id"]: s for s in data["services"]}
    services = [service_index[sid] for sid in service_ids if sid in service_index]
    # Choose the package aligned with the dominant business requirement. A multi-system
    # integration is explicitly routed to the custom Enterprise conversation.
    if "connected_operations" in matched:
        package_id = "pkg-enterprise"
    elif "e_commerce" in matched:
        package_id = "pkg-commerce"
    elif "lead_management" in matched and "repetitive_operations" in matched:
        package_id = "pkg-growth"
    elif "lead_management" in matched:
        package_id = "pkg-growth"
    elif "repetitive_operations" in matched:
        package_id = "pkg-automation"
    else:
        package_id = "pkg-ai-business"
    package = next(p for p in data["packages"] if p["id"] == package_id)
    reasons = []
    if "e_commerce" in matched: reasons.append("The workflow involves online products, orders, or inventory.")
    if "lead_management" in matched: reasons.append("Lead capture, qualification, or sales follow-up is a stated need.")
    if "customer_support" in matched: reasons.append("The team is handling recurring customer questions or messages.")
    if "repetitive_operations" in matched: reasons.append("The business identified repetitive manual tasks.")
    if "connected_operations" in matched: reasons.append("The requirements span several connected business systems.")
    return {"enough_information": True, "services": services, "package": package, "reasons": reasons, "matched_needs": matched}
