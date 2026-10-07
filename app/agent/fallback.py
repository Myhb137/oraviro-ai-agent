"""Database-grounded local responses used when the configured LLM is unavailable."""
import re
import unicodedata

from ..database import list_products, search_products
from ..tools.product_tools import Search_product, check_stock


ALL_CATALOG_TERMS = (
    "all", "everything", "catalog", "catalogue", "show products", "what do you have",
    "what products", "available products", "الكل", "كامل", "كاملين", "كل المنتجات",
    "وش عندكم", "واش عندكم", "شنو عندكم", "عندكم واش", "وريني المنتجات", "المنتجات كامل",
    "tous", "tout", "tous les produits", "quels produits", "vous avez quoi", "montre tout",
)

CATEGORY_ALIASES = {
    "عناية": ("عناية", "بشرة", "skin care", "skincare", "soin", "soins"),
    "الشعر": ("الشعر", "شعر", "hair care", "haircare", "cheveux"),
    "عطور": ("عطور", "عطر", "perfume", "parfum"),
    "Makeup": ("تجميل", "مكياج", "makeup", "cosmetic", "cosmetics"),
    "Clothing": ("ملابس", "لباس", "clothing", "hoodie", "vêtement", "vetement"),
    "Shoes": ("أحذية", "حذاء", "صباط", "shoes", "chaussures", "nike", "sneakers"),
    "Electronics": ("إلكترونيات", "الكترونيات", "سماعات", "electronics", "earbuds", "écouteurs", "ecouteurs"),
    "Accessories": ("إكسسوارات", "اكسسوارات", "accessories", "sac", "backpack", "حقيبة"),
}

STOP_WORDS = {
    "do", "you", "have", "is", "the", "a", "an", "how", "much", "what", "price", "available",
    "stock", "please", "tell", "me", "show", "want", "looking", "for", "got", "any", "there",
    "kayen", "kayn", "wach", "ch7al", "nheb", "n7eb", "عندكم", "عندك", "كاين", "كاينين",
    "وش", "واش", "حبيت", "نحب", "من", "فضلك", "لو", "عند", "كم", "سعر", "السعر", "هل", "في",
    "combien", "est", "ce", "que", "le", "la", "les", "des", "du", "de", "vous", "avez",
    "quoi", "je", "veux", "voir", "prix", "disponible", "produit", "produits", "svp", "s'il", "plait",
}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", text).strip()


def _is_all_request(text: str) -> bool:
    value = _normalize(text)
    return any(term in value for term in ALL_CATALOG_TERMS)


def _actual_categories(products):
    return list(dict.fromkeys(p["category"] for p in products if p.get("category")))


def _money(value):
    return f"{value:,.0f}"


def _render_catalog(products, language="en"):
    if not products:
        return "There are no products in the catalog right now."
    heading = "المنتجات المتوفرة:" if language == "ar" else "Voici les produits disponibles :" if language == "fr" else "Here are the products available:"
    lines = [f"• {p['name']} — {p['brand']} — {_money(p['price'])} DA — stock: {p['stock']}" for p in products]
    return heading + "\n" + "\n".join(lines)


def _language(text):
    if re.search(r"[\u0600-\u06ff]", text):
        return "ar"
    if any(word in _normalize(text) for word in ("bonjour", "produit", "combien", "vous", "je veux", "s'il vous")):
        return "fr"
    return "en"


def respond(message: str, preferred_language: str | None = None):
    """Return (text, tool_calls) grounded only in the persisted catalog."""
    text = _normalize(message)
    language = preferred_language or _language(message)

    if _is_all_request(text) or text in {"عندكم", "حابيت نعرف وش عندكم", "حابيت نعرف واش عندكم", "show me", "catalogue"}:
        products = list_products()
        return _render_catalog(products, language), [{"tool": "list_products", "status": "success"}]

    # Map common requested departments to actual database categories. A department
    # with no catalog matches gets a transparent answer, never invented products.
    categories = _actual_categories(list_products())
    for category, aliases in CATEGORY_ALIASES.items():
        if any(_normalize(alias) in text for alias in aliases):
            exact = [p for p in search_products(category) if p["category"].lower() == category.lower()]
            if exact:
                return _render_catalog(exact, language), [{"tool": "search_products", "status": "success"}]
            if language == "ar":
                answer = f"ما عندناش منتجات مسجلة في قسم {category} حالياً. الأقسام المتوفرة: " + "، ".join(categories) + "."
            elif language == "fr":
                answer = f"Aucun produit n'est actuellement enregistré dans la catégorie « {category} ». Catégories disponibles : " + ", ".join(categories) + "."
            else:
                answer = f"There are no products listed in {category} right now. Available categories: " + ", ".join(categories) + "."
            return answer, [{"tool": "search_products", "status": "success"}]

    # First match a complete product name, including Arabic/Darija transliterations
    # commonly used for the demo products.
    transliterations = {
        "lipstick-red": ("روج أحمر", "روج حمرا", "حمرة حمرا", "rouge a levres rouge", "rouge à lèvres rouge"),
        "hoodie-black": ("هودي أسود", "سويتر أسود", "black hoodie"),
        "air-max": ("نايك اير ماكس", "nike air max"),
        "earbuds-wireless": ("سماعات لاسلكية", "écouteurs sans fil"),
        "backpack-leather": ("حقيبة جلد", "sac à dos cuir"),
        "running-shoes": ("حذاء جري", "صباط جري", "chaussures de course"),
    }
    all_products = list_products()
    selected = None
    for p in all_products:
        if _normalize(p["name"]) in text or any(_normalize(alias) in text for alias in transliterations.get(p["id"], ())):
            selected = p
            break

    if not selected:
        tokens = [word for word in re.findall(r"[\w]+", text, flags=re.UNICODE) if word not in STOP_WORDS and len(word) > 1]
        candidates = []
        for token in tokens:
            found = Search_product.invoke({"product_name": token})
            candidates.extend(found)
        seen = set()
        candidates = [p for p in candidates if not (p["id"] in seen or seen.add(p["id"]))]
        if len(candidates) == 1:
            selected = candidates[0]

    if selected:
        product = selected
        stock = check_stock.invoke({"product_id": product["id"]})
        available = stock.get("stock", 0)
        if language == "ar":
            answer = f"نعم، {product['name']} متوفر بسعر {_money(product['price'])} دج. الكمية الحالية في المخزون: {available}." if available else f"{product['name']} غير متوفر حالياً."
        elif language == "fr":
            answer = f"Oui, {product['name']} est disponible à {_money(product['price'])} DA. Stock actuel : {available}." if available else f"{product['name']} est indisponible pour le moment."
        else:
            answer = f"Yes, {product['name']} is available for {_money(product['price'])} DA. Current stock: {available}." if available else f"{product['name']} is currently out of stock."
        return answer, [{"tool": "search_products", "status": "success"}, {"tool": "check_stock", "status": "success"}]

    greetings = ("سلام", "salam", "السلام", "bonjour", "hello", "hi")
    if any(greeting in text for greeting in greetings):
        answer = "سلام! نقدر نوريك المنتجات المتوفرة أو نعاونك تلقى منتج معين." if language == "ar" else "Bonjour ! Je peux vous montrer le catalogue ou chercher un produit." if language == "fr" else "Hello! I can show you the catalog or help find a product."
    elif language == "ar":
        answer = "نقدر نعاونك بمعلومات المنتجات الموجودة في المتجر. اكتب اسم منتج أو قل «الكل» باش نوريك الكتالوج."
    elif language == "fr":
        answer = "Je peux vous renseigner sur les produits du catalogue. Donnez-moi un nom de produit ou dites « tout » pour voir la liste."
    else:
        answer = "I can help with products in the store catalog. Tell me a product name, or ask to see all products."
    return answer, []
