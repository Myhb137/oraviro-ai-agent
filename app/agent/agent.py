import os
import re
import uuid
import logging
from time import perf_counter
from dotenv import load_dotenv
from langchain_core.messages import SystemMessage, HumanMessage, ToolMessage
from .prompts import SYSTEM_PROMPT
from ..database import (initialize_database, get_or_create_customer, update_customer, search_products,
    get_product, create_order as persist_order, save_message, get_messages,
    set_conversation_status, get_conversation_state, set_conversation_state,
    get_conversation_language, get_customer_language, set_conversation_language, DEFAULT_BUSINESS_ID,
    )
from ..tools.product_tools import Search_product, get_product_tool, check_stock
from ..tools.consultant_tools import CONSULTANT_TOOLS
from .language import detect_language, language_instruction
from ..services.leads import get_lead_profile, update_lead_profile, affirmative, share_contact_was_provided, persist_consenting_lead

log = logging.getLogger("oraviro.agent")
load_dotenv()
TOOLS = list(CONSULTANT_TOOLS)
CONTEXT_TOOLS = {"get_current_lead_profile", "update_lead_profile", "offer_lead_summary", "save_lead", "escalate_to_human", "recommend_services"}

def _model():
    provider = os.getenv("LLM_PROVIDER", "groq").lower()
    model = os.getenv("LLM_MODEL")
    key = os.getenv("GROQ_API_KEY" if provider == "groq" else "GOOGLE_API_KEY")
    if not key: return None
    if provider == "groq":
        try:
            from langchain_groq import ChatGroq
        except ImportError:
            raise RuntimeError("Install langchain-groq to use LLM_PROVIDER=groq")
        return ChatGroq(model=model or "llama-3.1-8b-instant", api_key=key, temperature=0.2, max_tokens=int(os.getenv("LLM_MAX_TOKENS", "512")))
    if provider in ("google", "gemini"):
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(model=model or "gemini-2.5-flash", google_api_key=key, temperature=0.2)
    raise RuntimeError(f"Unsupported LLM_PROVIDER: {provider}")

def _txt(content):
    if isinstance(content, str): return content
    if isinstance(content, list): return "\n".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in content)
    return str(content)

def _conversation(customer_id, conversation_id, business_id=DEFAULT_BUSINESS_ID):
    if conversation_id: return conversation_id
    identity=customer_id if business_id==DEFAULT_BUSINESS_ID else f"{business_id}:{customer_id}"
    return "conv_" + str(uuid.uuid5(uuid.NAMESPACE_URL, identity))[:12]

def _say(language, en, fr, ar):
    return {"fr": fr, "ar": ar}.get(language, en)


def _is_greeting(message):
    value = re.sub(r"[^\w\u0600-\u06ff]+", " ", message.lower()).strip()
    return value in {
        "hi", "hello", "hey", "good morning", "good afternoon", "good evening",
        "bonjour", "bonsoir", "salut", "salam", "salam alaykum", "assalamu alaikum",
        "السلام عليكم", "سلام", "مرحبا", "أهلا", "اهلا",
    }


def _greeting_response(language, message):
    normalized = message.strip().lower()
    if language == "ar":
        greeting = "وعليكم السلام 👋 مرحبا!" if "السلام عليكم" in message else "سلام 👋 مرحبا!"
        return f"{greeting} أنا Oraviro AI.\nنقدر نعاونك تفهم واش تقدر Oraviro تدير لبيزنس تاعك، ونشوفو واش من العمليات تقدر تتأتمت بالـAI.\nواش نوع البيزنس لي عندك؟"
    if language == "fr":
        greeting = "Bonjour 👋" if normalized in {"bonjour", "bonsoir"} else "Salut 👋"
        return f"{greeting} Je suis Oraviro AI. Je peux vous expliquer les solutions d'Ora Viro ou repérer les tâches de votre activité qui pourraient être automatisées avec l'IA. Quel type d'activité gérez-vous ?"
    return "Hi 👋 I'm Oraviro AI.\nI can explain what Oraviro does, or help you figure out what parts of your business could be automated with AI.\nWhat type of business do you run?"

def _order_flow(customer_id, conversation_id, message, language="en"):
    """A small persisted confirmation gate; all order writes stay server-side."""
    persisted = get_conversation_state(conversation_id, customer_id)
    state = persisted.get("order", persisted if "items" in persisted else {})
    low = message.lower().strip()
    yes = low in {"yes", "y", "oui", "نعم", "ايه", "إيه", "نعم أكد", "confirm", "ok", "okay"}
    no = low in {"no", "non", "لا", "cancel", "لغيه"}
    if state.get("awaiting_confirmation"):
        if yes:
            result = persist_order(customer_id, state["items"], state["name"], state["phone"], state["address"])
            state = {}
            _save_state(conversation_id, customer_id, state)
            return _say(language, f"Done ✅ Your order {result['order_id']} has been created.", f"C'est fait ✅ Votre commande {result['order_id']} a été créée.", f"تم ✅ تم إنشاء طلبك رقم {result['order_id']}.") , [{"tool": "create_order", "status": "success"}]
        if no:
            _save_state(conversation_id, customer_id, {})
            return _say(language, "No problem, I cancelled that order request.", "D'accord, la demande de commande est annulée.", "ماشي مشكل، ألغيت طلب الشراء."), []
        return None
    if state.get("items") and state.get("stage"):
        stage = state["stage"]
        if stage == "name":
            state["name"] = message.strip(); state["stage"] = "phone"
            update_customer(customer_id, name=state["name"])
            _save_state(conversation_id, customer_id, state)
            return _say(language, "Thanks! What's your phone number?", "Merci ! Quel est votre numéro de téléphone ?", "شكراً! واش هو رقم هاتفك؟"), []
        if stage == "phone":
            phone = re.sub(r"[\s-]", "", message)
            if not re.fullmatch(r"\+?\d{9,15}", phone): return _say(language, "Please send a valid phone number.", "Veuillez envoyer un numéro de téléphone valide.", "من فضلك ابعث رقم هاتف صحيح."), []
            state["phone"] = phone; state["stage"] = "address"
            update_customer(customer_id, phone=phone)
            _save_state(conversation_id, customer_id, state)
            return _say(language, "And what's your delivery address?", "Quelle est votre adresse de livraison ?", "وواش هو عنوان التوصيل؟"), []
        if stage == "address":
            state["address"] = message.strip(); state.pop("stage", None)
            update_customer(customer_id, address=state["address"])
            qty = state["items"][0]["quantity"]; p = get_product(state["items"][0]["product_id"])
            state["awaiting_confirmation"] = True; _save_state(conversation_id, customer_id, state)
            return _say(language, f"Please confirm: {qty} × {p['name']} for {qty*p['price']:,.0f} DA, delivered to {state['address']}. Should I place the order?", f"Veuillez confirmer : {qty} × {p['name']} pour {qty*p['price']:,.0f} DA, livraison à {state['address']}. Je valide la commande ?", f"أكد من فضلك: {qty} × {p['name']} بـ {qty*p['price']:,.0f} دج، التوصيل إلى {state['address']}. نأكد الطلب؟"), []
    if re.search(r"\b(human|someone|representative|agent)\b|موظف|إنسان|انسان|شخص", low):
        set_conversation_status(conversation_id, customer_id, "human_required")
        return _say(language, "Of course. I'll pass this conversation to the team. No live team notification is configured yet.", "Bien sûr. Je transmets cette conversation à l'équipe. Aucune notification directe à l'équipe n'est configurée pour le moment.", "أكيد، نعلّم الفريق بالمحادثة. حالياً ما كاش إشعار مباشر للفريق."), []
    order_phrase = any(x in low for x in ("i want", "i'd like", "order", "buy", "nheb", "حاب", "اريد", "je veux", "commander"))
    qty_match = re.search(r"\b(\d+)\b", low)
    if order_phrase and not qty_match and any(x in low for x in ("order", "buy", "commander", "je veux", "nheb", "اريد")):
        return _say(language, "Which product would you like to order, and how many?", "Quel produit souhaitez-vous commander et en quelle quantité ?", "واش هو المنتج اللي حاب تطلبو وشحال من وحدة؟"), []
    if not order_phrase or not qty_match: return None
    query = re.sub(r"\b(i want|i'd like|to order|order|buy|nheb|je veux|commander)\b", " ", low)
    query = re.sub(r"\b\d+\b", " ", query).strip(" .?!")
    products = search_products(query)
    if not products: return _say(language, "Which product would you like to order? I couldn't match it in the catalog.", "Quel produit souhaitez-vous commander ? Je ne l'ai pas trouvé dans le catalogue.", "واش هو المنتج اللي حاب تطلبو؟ ما لقيتوش في الكتالوغ."), []
    if len(products) > 1 and query and not any(query in p["name"].lower() for p in products): return _say(language, "Which product would you like to order?", "Quel produit souhaitez-vous commander ?", "واش هو المنتج اللي حاب تطلبو؟"), []
    p = products[0]; qty = int(qty_match.group(1))
    if qty < 1: return _say(language, "Please tell me a valid quantity.", "Veuillez indiquer une quantité valide.", "من فضلك حدد كمية صحيحة."), []
    if p["stock"] < qty: return _say(language, f"We only have {p['stock']} units of {p['name']} in stock.", f"Il ne reste que {p['stock']} unités de {p['name']}.", f"باقي غير {p['stock']} من {p['name']} في المخزون."), [{"tool":"check_stock","status":"success"}]
    customer = get_or_create_customer(customer_id)
    name, phone, address = customer["name"], customer["phone"], customer["address"]
    digits = re.sub(r"\D", "", message)
    if not name: name = None
    if not phone: phone = None
    if not address: address = None
    # Capture explicit customer details from the current message when supplied.
    if re.search(r"\b(0\d{9})\b", message): phone = re.search(r"\b(0\d{9})\b", message).group(1)
    state = {"items":[{"product_id":p["id"],"quantity":qty}],"name":name,"phone":phone,"address":address}
    _save_state(conversation_id, customer_id, state)
    missing = [label for key,label in (("name","your name"),("phone","your phone number"),("address","your delivery address")) if not state[key]]
    if missing:
        key = {"your name":"name", "your phone number":"phone", "your delivery address":"address"}[missing[0]]
        state["stage"] = key; _save_state(conversation_id, customer_id, state)
        label = missing[0]
        question = {"name": _say(language, "What's your name?", "Quel est votre nom ?", "واش هو اسمك؟"), "phone": _say(language, "What's your phone number?", "Quel est votre numéro de téléphone ?", "واش هو رقم هاتفك؟"), "address": _say(language, "What's your delivery address?", "Quelle est votre adresse de livraison ?", "واش هو عنوان التوصيل؟")}[key]
        intro = _say(language, f"Sure 👌 {p['name']} is {p['price']:,.0f} DA each and we have {p['stock']} in stock.", f"Bien sûr 👌 {p['name']} coûte {p['price']:,.0f} DA l'unité et il en reste {p['stock']}.", f"أكيد 👌 {p['name']} بـ {p['price']:,.0f} دج للوحدة، وكاين {p['stock']} في المخزون.")
        return f"{intro} {question}", [{"tool":"search_products","status":"success"},{"tool":"check_stock","status":"success"}]
    state["awaiting_confirmation"] = True; _save_state(conversation_id, customer_id, state)
    return _say(language, f"Please confirm: {qty} × {p['name']} for {qty*p['price']:,.0f} DA, delivered to {address}. Should I place the order?", f"Veuillez confirmer : {qty} × {p['name']} pour {qty*p['price']:,.0f} DA, livraison à {address}. Je valide la commande ?", f"أكد من فضلك: {qty} × {p['name']} بـ {qty*p['price']:,.0f} دج، التوصيل إلى {address}. نأكد الطلب؟"), []

def _save_state(conversation_id, customer_id, state):
    root = get_conversation_state(conversation_id, customer_id)
    # Migrate any old flat order state while preserving the consultant's lead profile.
    for key in ("items", "name", "phone", "address", "stage", "awaiting_confirmation"):
        root.pop(key, None)
    if state:
        root["order"] = state
    else:
        root.pop("order", None)
    set_conversation_state(conversation_id, customer_id, root)

def _subscribe_request(message):
    text = message.lower()
    mentions_notification = any(term in text for term in ("notify", "notification", "alert me", "خبروني", "خبرني", "علمني", "علّموني", "علمني", "كي تزيدو", "كي تضيفو", "كي يجي", "منتج جديد", "produit nouveau", "nouveau produit", "prévenez", "prevenez", "notifiez"))
    mentions_products = any(term in text for term in ("product", "products", "منتج", "منتجات", "produit", "produits"))
    return mentions_notification and mentions_products

def chat_result(user_message: str, user_id: str, conversation_id: str | None = None, business_id: str = DEFAULT_BUSINESS_ID):
    started = perf_counter(); initialize_database()
    customer=get_or_create_customer(user_id,business_id)
    user_id=customer["id"]
    conv = _conversation(user_id, conversation_id, business_id)
    # Conversation preference takes precedence; customer preference carries the
    # language over if a channel/client starts a fresh conversation ID.
    saved_language = get_conversation_language(conv, user_id, business_id) or get_customer_language(user_id,business_id)
    # A short greeting is ambiguous; keep the established language in an active
    # conversation and only infer from it when no preference exists yet.
    detected = None if saved_language and _is_greeting(user_message) else detect_language(user_message)
    language = detected or saved_language or "en"
    if detected or not saved_language:
        set_conversation_language(conv, user_id, language, business_id)
    lead_profile = get_lead_profile(user_id, conv)
    if lead_profile.get("lead_summary_offered") and (affirmative(user_message) or share_contact_was_provided(user_message)):
        lead_profile = update_lead_profile(user_id, conv, {"lead_consent": True})
    is_first_turn = not get_messages(conv, 1, business_id, user_id)
    save_message(conv, user_id, "user", user_message, business_id)
    try:
        if is_first_turn and _is_greeting(user_message):
            response = _greeting_response(language, user_message)
            calls = []
            save_message(conv, user_id, "assistant", response, business_id)
            return {"response": response, "conversation_id": conv, "tool_calls": calls}
        try:
            model = _model()
            if model is None:
                raise RuntimeError("No LLM provider configured")
            bound = model.bind_tools(TOOLS)
            profile_context = {k: v for k, v in lead_profile.items() if k not in {"lead_score", "lead_status"}}
            import json
            history = [
                SystemMessage(content=SYSTEM_PROMPT + language_instruction(language)),
                SystemMessage(content="Verified lead profile for this conversation (known facts only; null means not collected): " + json.dumps(profile_context, ensure_ascii=False)),
            ]
            history.extend(HumanMessage(content=m["content"]) if m["role"] == "user" else __import__("langchain_core.messages", fromlist=["AIMessage"]).AIMessage(content=m["content"]) for m in get_messages(conv, 10, business_id, user_id)[:-1])
            history.append(HumanMessage(content=user_message))
            calls = []
            response_msg = bound.invoke(history)
            for _ in range(4):
                if not response_msg.tool_calls: break
                history.append(response_msg)
                for call in response_msg.tool_calls:
                    tool = next((t for t in TOOLS if t.name == call["name"]), None)
                    if not tool: continue
                    args = call["args"]
                    if call["name"] in CONTEXT_TOOLS:
                        args["customer_id"] = user_id
                        args["conversation_id"] = conv
                    result = tool.invoke(args)
                    calls.append({"tool":call["name"],"status":"success" if not (isinstance(result,dict) and result.get("error")) else "error"})
                    history.append(ToolMessage(content=str(result), tool_call_id=call["id"]))
                    if call["name"] == "update_lead_profile":
                        latest_profile = get_lead_profile(user_id, conv)
                        if latest_profile.get("lead_consent") and (latest_profile.get("email") or latest_profile.get("phone")) and latest_profile.get("contact_name"):
                            persist_result = persist_consenting_lead(user_id, conv)
                            if persist_result.get("success"):
                                history.append(SystemMessage(content="The customer's consented lead summary has been saved for the Oraviro team."))
                response_msg = bound.invoke(history)
            response = _txt(response_msg.content)
        except Exception as llm_error:
            log.warning("llm_unavailable customer=%s conversation=%s error=%s", user_id, conv, type(llm_error).__name__)
            from .consultant_fallback import respond as fallback_respond
            response, calls = fallback_respond(user_message, user_id, conv, language)
        save_message(conv, user_id, "assistant", response, business_id)
        log.info("agent_request customer=%s conversation=%s tool_calls=%s latency_ms=%d",user_id,conv,calls,round((perf_counter()-started)*1000))
        return {"response":response,"conversation_id":conv,"tool_calls":calls}
    except Exception:
        log.exception("agent_error customer=%s conversation=%s latency_ms=%d",user_id,conv,round((perf_counter()-started)*1000))
        safe = _say(language, "Sorry, the consultant is temporarily unavailable. Please try again shortly.", "Désolé, le conseiller est temporairement indisponible. Réessayez dans quelques instants.", "سمحلي، المساعد الاستشاري غير متوفر مؤقتاً. عاود جرّب بعد شوية.")
        save_message(conv,user_id,"assistant",safe,business_id)
        return {"response":safe,"conversation_id":conv,"tool_calls":[]}

def chat(user_message: str, user_id: str):
    return chat_result(user_message,user_id)["response"]
