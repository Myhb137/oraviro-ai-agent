"""Typed, bounded tools for the Oraviro business-consultant agent."""
from langchain_core.tools import tool

from ..database import set_conversation_status
from ..services.consulting import company_knowledge, find_offerings, recommend_for_business
from ..services.leads import (
    get_lead_profile as read_profile,
    mark_summary_offered,
    persist_consenting_lead,
    update_lead_profile as patch_profile,
)


def _public_profile(profile):
    return {key: value for key, value in profile.items() if key not in {"lead_score", "lead_status", "lead_consent", "lead_summary_offered", "fallback_next"}}


@tool
def get_company_information():
    """Get verified Oraviro company positioning and the official website."""
    return company_knowledge()["company"]


@tool
def get_services(query: str = ""):
    """Search Oraviro's verified services by name or category; results include official DZD prices."""
    return find_offerings(query)["services"]


@tool
def get_pricing(query: str):
    """Find the official published price for a named Ora Viro package or service. Never infer an unlisted price."""
    result = find_offerings(query)
    if result["packages"] or result["services"]:
        return result
    return {"official_price_available": False, "message": "No matching official price was found. Explain that you cannot confirm a price and offer to save a lead for the team."}


@tool
def recommend_services(industry: str, problems: list[str], channels: list[str], needs: list[str], customer_id: str, conversation_id: str):
    """Match explicitly stated business needs to verified Ora Viro services and the closest published package."""
    result = recommend_for_business(industry, problems or [], channels or [], needs or [])
    if result.get("enough_information"):
        patch_profile(customer_id, conversation_id, {
            "recommended_services": [item["name"] for item in result["services"]],
            "recommended_package": result["package"]["name"],
            "reasons": result["reasons"],
        })
    return result


@tool
def get_current_lead_profile(customer_id: str, conversation_id: str):
    """Read facts the customer has already shared in this conversation. Context IDs are enforced by the agent."""
    return _public_profile(read_profile(customer_id, conversation_id))


@tool
def update_lead_profile(
    customer_id: str,
    conversation_id: str,
    business_name: str | None = None,
    industry: str | None = None,
    business_size: str | None = None,
    customer_volume: str | None = None,
    channels: list[str] | None = None,
    current_tools: list[str] | None = None,
    workflow: str | None = None,
    pain_points: list[str] | None = None,
    automation_needs: list[str] | None = None,
    data_needs: list[str] | None = None,
    budget: str | None = None,
    timeline: str | None = None,
    urgency: str | None = None,
    contact_name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    recommended_services: list[str] | None = None,
    recommended_package: str | None = None,
    reasons: list[str] | None = None,
):
    """Save only facts the customer explicitly provided; do not infer missing details."""
    profile = patch_profile(customer_id, conversation_id, locals())
    return _public_profile(profile)


@tool
def offer_lead_summary(customer_id: str, conversation_id: str):
    """Record that the customer was offered a requirements summary for the Oraviro team."""
    profile = mark_summary_offered(customer_id, conversation_id)
    return {"offered": bool(profile["lead_summary_offered"])}


@tool
def save_lead(customer_id: str, conversation_id: str):
    """Save a qualified lead only after explicit consent and collection of contact name plus email or phone."""
    return persist_consenting_lead(customer_id, conversation_id)


@tool
def escalate_to_human(customer_id: str, conversation_id: str, reason: str = "Customer requested human support"):
    """Mark a conversation for human follow-up. No live team notification is configured."""
    set_conversation_status(conversation_id, customer_id, "human_required")
    return {"status": "human_required", "notification_sent": False, "reason": reason[:300]}


CONSULTANT_TOOLS = [
    get_company_information, get_services, get_pricing, recommend_services,
    get_current_lead_profile, update_lead_profile, offer_lead_summary, save_lead,
    escalate_to_human,
]
