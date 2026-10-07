"""Lead profile and consented lead handoff services."""
import re

from ..database import get_conversation_state, set_conversation_state, save_lead_record

PROFILE_FIELDS = {
    "business_name", "industry", "business_size", "customer_volume", "channels",
    "current_tools", "workflow", "pain_points", "automation_needs", "data_needs",
    "budget", "timeline", "urgency", "contact_name", "email", "phone",
    "recommended_services", "recommended_package", "reasons",
    "lead_score", "lead_status", "lead_summary_offered", "lead_consent", "fallback_next",
}
LIST_FIELDS = {"channels", "current_tools", "pain_points", "automation_needs", "data_needs", "recommended_services", "reasons"}
DEFAULT_PROFILE = {
    "business_name": None, "industry": None, "business_size": None, "customer_volume": None,
    "channels": [], "current_tools": [], "workflow": None, "pain_points": [],
    "automation_needs": [], "data_needs": [], "budget": None, "timeline": None,
    "urgency": None, "contact_name": None, "email": None, "phone": None,
    "recommended_services": [], "recommended_package": None, "reasons": [],
    "lead_score": None, "lead_status": None, "lead_summary_offered": False,
    "lead_consent": False, "fallback_next": None,
}


def get_lead_profile(customer_id, conversation_id):
    state = get_conversation_state(conversation_id, customer_id)
    profile = dict(DEFAULT_PROFILE)
    profile.update(state.get("lead_profile", {}))
    return profile


def update_lead_profile(customer_id, conversation_id, patch):
    state = get_conversation_state(conversation_id, customer_id)
    profile = dict(DEFAULT_PROFILE)
    profile.update(state.get("lead_profile", {}))
    for key, value in patch.items():
        if key not in PROFILE_FIELDS or value is None:
            continue
        if key in LIST_FIELDS:
            current = profile.get(key) or []
            values = value if isinstance(value, list) else [value]
            profile[key] = list(dict.fromkeys([*current, *(str(v).strip() for v in values if str(v).strip())]))
        elif key in {"lead_summary_offered", "lead_consent"}:
            profile[key] = bool(value) or bool(profile.get(key))
        else:
            profile[key] = str(value).strip()
    score, status = calculate_lead_score(profile)
    profile["lead_score"], profile["lead_status"] = score, status
    state["lead_profile"] = profile
    set_conversation_state(conversation_id, customer_id, state)
    return profile


def calculate_lead_score(profile):
    """Return a private 0–100 qualification score and status."""
    score = 0
    if profile.get("pain_points"): score += 25
    if profile.get("automation_needs"): score += 20
    if profile.get("business_name"): score += 5
    if profile.get("industry"): score += 5
    if profile.get("channels"): score += min(15, 5 * len(profile["channels"]))
    if profile.get("customer_volume"): score += 10
    if profile.get("budget"): score += 10
    urgency = str(profile.get("urgency") or profile.get("timeline") or "").lower()
    if urgency and any(term in urgency for term in ("urgent", "soon", "this month", "asap", "urgent", "عاجل", "قريب")): score += 15
    elif urgency: score += 8
    if score >= 75: status = "HIGH_VALUE"
    elif score >= 55: status = "QUALIFIED"
    elif score >= 25: status = "POTENTIAL"
    else: status = "LOW_INTENT"
    return min(score, 100), status


def mark_summary_offered(customer_id, conversation_id):
    return update_lead_profile(customer_id, conversation_id, {"lead_summary_offered": True})


def share_contact_was_provided(message):
    """Detect contact details supplied in response to a previously offered summary."""
    return bool(re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", message, re.I) or re.search(r"(?:\+?\d[\d ()-]{7,}\d)", message))


def affirmative(message):
    return message.strip().lower() in {"yes", "yes please", "sure", "okay", "ok", "oui", "d'accord", "نعم", "ايه", "إيه", "أكيد", "اكيد", "موافق", "نعم من فضلك"}


def persist_consenting_lead(customer_id, conversation_id):
    profile = get_lead_profile(customer_id, conversation_id)
    has_contact = bool(profile.get("email") or profile.get("phone"))
    if not profile.get("lead_consent"):
        return {"success": False, "reason": "Customer has not consented to sharing their details."}
    if not profile.get("contact_name") or not has_contact:
        return {"success": False, "reason": "Collect the contact name and at least one of email or phone first."}
    score, status = calculate_lead_score(profile)
    profile["lead_score"], profile["lead_status"] = score, status
    lead_id = save_lead_record(customer_id, conversation_id, profile, score, status)
    return {"success": True, "lead_id": lead_id, "lead_status": status}
