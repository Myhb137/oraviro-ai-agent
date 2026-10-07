"""Small multilingual consultant flow for provider outages, grounded in site data."""
import re

from ..services.consulting import company_knowledge, recommend_for_business, find_offerings
from ..services.leads import (
    get_lead_profile, update_lead_profile, mark_summary_offered,
    persist_consenting_lead,
)


def _lang(language, en, fr, ar):
    return {"fr": fr, "ar": ar}.get(language, en)


def _contains(text, terms):
    value = text.lower()
    return any(term in value for term in terms)


def _parse_business(message):
    text = message.lower()
    if _contains(text, ("online store", "e-commerce", "ecommerce", "clothing store", "shopify", "متجر إلكتروني", "متجر ملابس", "boutique en ligne", "e-commerce")):
        return "E-commerce / retail"
    if _contains(text, ("restaurant", "café", "cafe", "مطعم", "restaurant")):
        return "Restaurant / food service"
    if _contains(text, ("clinic", "clinique", "عيادة", "cabinet médical")):
        return "Healthcare / clinic"
    if _contains(text, ("agency", "agence", "وكالة")):
        return "Agency"
    if _contains(text, ("salon", "صالون")):
        return "Salon / personal services"
    return None


def _parse_channels(message):
    text = message.lower()
    aliases = {
        "Instagram": ("instagram", "إنستغرام", "انستغرام"),
        "WhatsApp": ("whatsapp", "واتساب"),
        "Website": ("website", "site web", "web chat", "الموقع"),
        "Facebook": ("facebook", "فيسبوك"),
        "Telegram": ("telegram", "تيليغرام"),
        "Phone": ("phone", "telephone", "téléphone", "هاتف", "بالهاتف"),
    }
    return [name for name, words in aliases.items() if any(word in text for word in words)]


def _format_recommendation(result, language):
    package = result["package"]
    services = result["services"][:3]
    if language == "ar":
        lines = ["بناءً على اللي قلتلي عليه، هاذو أنسب حلول:"]
        lines.extend(f"• {s['name']} — {s['price_dzd']:,} دج" for s in services)
        lines.append(f"الباقة المقترحة: {package['name']} — {package['price_dzd']:,} دج.")
        lines.append("السعر المنشور في موقع Ora Viro؛ السعر النهائي والشروط يتأكدوا مع الفريق.")
        lines.append("تحب نحضّر ملخص لاحتياجاتك لفريق Ora Viro؟")
        return "\n".join(lines)
    if language == "fr":
        lines = ["D'après ce que vous m'avez expliqué, voici les options les plus adaptées :"]
        lines.extend(f"• {s['name']} — {s['price_dzd']:,} DA" for s in services)
        lines.append(f"Pack recommandé : {package['name']} — {package['price_dzd']:,} DA.")
        lines.append("Il s'agit du tarif publié par Ora Viro ; le périmètre et les conditions finales sont à confirmer avec l'équipe.")
        lines.append("Souhaitez-vous que je prépare un résumé de vos besoins pour l'équipe Ora Viro ?")
        return "\n".join(lines)
    lines = ["Based on what you shared, these options look relevant:"]
    lines.extend(f"• {s['name']} — {s['price_dzd']:,} DA" for s in services)
    lines.append(f"Recommended package: {package['name']} — {package['price_dzd']:,} DA.")
    lines.append("That is the price published by Ora Viro; final scope and terms should be confirmed with the team.")
    lines.append("Would you like me to prepare a short requirements summary for the Ora Viro team?")
    return "\n".join(lines)


def respond(message, customer_id, conversation_id, language="en"):
    text = message.strip()
    low = text.lower()
    profile = get_lead_profile(customer_id, conversation_id)
    stage = profile.get("fallback_next")
    patch = {}

    # Capture an answer only against a question the fallback actually asked.
    if stage == "industry":
        if low not in {"yes", "y", "oui", "نعم", "ايه", "ok", "okay", "sure"}:
            patch["industry"] = _parse_business(text) or text[:120]
            patch["fallback_next"] = None
    elif stage == "channels":
        parsed = _parse_channels(text)
        if parsed: patch["channels"] = parsed
        elif len(text.split()) > 1: patch["channels"] = [text[:120]]
        patch["fallback_next"] = None
    elif stage == "manual":
        if _contains(low, ("yes", "oui", "نعم", "ايه", "manually", "manual", "يدويا", "يدوي")):
            patch["pain_points"] = ["Customer conversations are handled manually"]
            patch["automation_needs"] = ["Customer conversation automation"]
        elif _contains(low, ("no", "non", "لا")):
            patch["pain_points"] = ["Customer workflow needs improvement"]
        else:
            patch["pain_points"] = [text[:300]]
            patch["automation_needs"] = [text[:200]]
        patch["fallback_next"] = None
    elif stage == "needs":
        patch["pain_points"] = [text[:300]]
        patch["automation_needs"] = [text[:200]]
        patch["fallback_next"] = None
    elif stage == "volume":
        patch["customer_volume"] = text[:120]
        patch["fallback_next"] = None
    elif stage == "contact_name" and profile.get("lead_consent"):
        patch["contact_name"] = text[:160]
        patch["fallback_next"] = "contact_method"
    elif stage == "contact_method" and profile.get("lead_consent"):
        email = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.I)
        phone = re.search(r"(?:\+?\d[\d ()-]{7,}\d)", text)
        if email: patch["email"] = email.group(0)
        if phone: patch["phone"] = phone.group(0)
        patch["fallback_next"] = None

    # Also capture explicit industry/channel/problem details when volunteered.
    if not profile.get("industry"):
        industry = _parse_business(text)
        if industry: patch.setdefault("industry", industry)
    channels = _parse_channels(text)
    if channels: patch["channels"] = list(dict.fromkeys([*(profile.get("channels") or []), *channels]))
    if _contains(low, ("manually", "manual", "repetitive", "same questions", "copy and paste", "copy-paste", "يدويا", "متكررة")):
        patch.setdefault("pain_points", [text[:300]])
        patch.setdefault("automation_needs", [text[:200]])
    if patch:
        profile = update_lead_profile(customer_id, conversation_id, patch)

    data = company_knowledge()
    if _contains(low, ("what is oraviro", "what does oraviro", "what do you do", "about oraviro", "واش تديرو", "شنو تديرو", "وش هي oraviro", "c'est quoi oraviro", "que fait oraviro")):
        if language == "ar":
            answer = "Ora Viro تبني أنظمة رقمية، أتمتة للعمليات، حلول ذكاء اصطناعي ومنتجات رقمية قابلة للتوسع. واش نوع النشاط تاعك؟"
        elif language == "fr":
            answer = "Ora Viro conçoit des systèmes numériques, des automatisations, des solutions d'IA et des produits digitaux évolutifs. Quel type d'activité gérez-vous ?"
        else:
            answer = f"{data['company']['summary']} What type of business do you run?"
        update_lead_profile(customer_id, conversation_id, {"fallback_next": "industry"})
        return answer, []

    # If the customer agreed to a summary, collect only the minimum contact details.
    if profile.get("lead_consent"):
        if not profile.get("contact_name"):
            update_lead_profile(customer_id, conversation_id, {"fallback_next": "contact_name"})
            return _lang(language, "What name should I put on the summary?", "Quel nom dois-je indiquer sur le résumé ?", "واش هو الاسم اللي نحطو في الملخص؟"), []
        if not (profile.get("email") or profile.get("phone")):
            update_lead_profile(customer_id, conversation_id, {"fallback_next": "contact_method"})
            return _lang(language, "Thanks. What's the best email address or phone number to reach you?", "Merci. Quelle adresse e-mail ou quel numéro de téléphone peut-on utiliser pour vous contacter ?", "شكراً. واش هو الإيميل ولا رقم الهاتف المناسب باش يتواصلوا معاك؟"), []
        saved = persist_consenting_lead(customer_id, conversation_id)
        if saved.get("success"):
            return _lang(language, "Thanks — your summary is saved for the Ora Viro team. No one has been directly notified.", "Merci — votre résumé est enregistré pour l'équipe Ora Viro. Personne n'a été notifié directement.", "شكراً — حفظت الملخص لفريق Ora Viro. ما تبعث حتى إشعار مباشر للفريق."), [{"tool": "save_lead", "status": "success"}]

    # An explicitly named package/service price is answered from the website catalog.
    if _contains(low, ("price", "pricing", "cost", "how much", "prix", "tarif", "combien", "السعر", "شحال", "بشحال")):
        named = next((p["name"] for p in data["packages"] if p["name"].lower() in low), None)
        named = named or next((s["name"] for s in data["services"] if s["name"].lower() in low), None)
        if named:
            matches = find_offerings(named)
            offering = (matches["packages"] or matches["services"])[0]
            price = offering.get("price_dzd")
            return _lang(language, f"{offering['name']} has an official published price of {price:,} DA. Final scope and terms should be confirmed with Ora Viro.", f"{offering['name']} a un tarif officiel publié de {price:,} DA. Le périmètre et les conditions sont à confirmer avec Ora Viro.", f"السعر المنشور لـ {offering['name']} هو {price:,} دج. الفريق يأكد النطاق والشروط النهائية."), [{"tool": "get_pricing", "status": "success"}]
        return _lang(language, "Pricing depends on what you need to automate. What type of business do you run?", "Le tarif dépend de ce que vous souhaitez automatiser. Quel type d'activité gérez-vous ?", "السعر يختلف حسب واش حاب تأتمت. واش نوع النشاط تاعك؟"), []

    if not profile.get("industry"):
        if _parse_business(text):
            # The profile update above already saved this business type.
            profile = get_lead_profile(customer_id, conversation_id)
        else:
            update_lead_profile(customer_id, conversation_id, {"fallback_next": "industry"})
            return _lang(language, "What type of business do you run?", "Quel type d'activité gérez-vous ?", "واش نوع النشاط التجاري تاعك؟"), []
    if not profile.get("channels"):
        update_lead_profile(customer_id, conversation_id, {"fallback_next": "channels"})
        return _lang(language, "How do customers usually contact you — Instagram, WhatsApp, your website, or another channel?", "Comment vos clients vous contactent-ils — Instagram, WhatsApp, votre site ou un autre canal ?", "كيفاش يتواصلوا معاك الزبائن غالباً — إنستغرام، واتساب، الموقع ولا قناة أخرى؟"), []
    if not profile.get("pain_points"):
        update_lead_profile(customer_id, conversation_id, {"fallback_next": "manual"})
        return _lang(language, "Are your team members handling those messages manually today?", "Votre équipe traite-t-elle ces messages manuellement aujourd'hui ?", "الفريق تاعك يجاوب على هاذ الرسائل يدوياً حالياً؟"), []
    if not profile.get("customer_volume"):
        update_lead_profile(customer_id, conversation_id, {"fallback_next": "volume"})
        return _lang(language, "Roughly how many customer conversations do you handle in a typical day or month?", "Environ combien de conversations clients gérez-vous par jour ou par mois ?", "تقريباً شحال من محادثة مع الزبائن تتعاملو معاها في نهار ولا شهر عادي؟"), []

    result = recommend_for_business(profile.get("industry") or "", profile.get("pain_points") or [], profile.get("channels") or [], profile.get("automation_needs") or [])
    if result.get("enough_information"):
        package = result["package"]
        services = [s["name"] for s in result["services"][:3]]
        profile = update_lead_profile(customer_id, conversation_id, {"recommended_services": services, "recommended_package": package["name"], "reasons": result["reasons"]})
        mark_summary_offered(customer_id, conversation_id)
        return _format_recommendation(result, language), [{"tool": "recommend_services", "status": "success"}]
    return _lang(language, "What workflow would you most like to improve first?", "Quel processus souhaitez-vous améliorer en premier ?", "واش هو المسار اللي حاب تحسّنو أولاً؟"), []
