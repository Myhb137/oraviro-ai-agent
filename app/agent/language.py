"""Lightweight language preference detection for conversation continuity."""
import re

LANGUAGE_LABELS = {
    "ar": "Arabic / Algerian Darija",
    "fr": "French",
    "en": "English",
}

_FRENCH = re.compile(r"\b(bonjour|bonsoir|merci|combien|produit|produits|vous|votre|je|veux|cherche|prix|disponible|commande|s'il|plait|svp|est-ce|montrez|affichez|veuillez|catalogue|une|boutique|commerce|activité|activite|entreprise|gère|gere|ligne)\b", re.I)
_DARIJA = re.compile(r"\b(salam|kayen|kayn|wach|nheb|n7eb|ch7al|win|rah|rani|bghit|saha|bezaf|kifach|wech)\b", re.I)
_ENGLISH = re.compile(r"\b(hello|hi|please|thanks|thank|how|what|where|do|does|have|want|need|show|all|everything|price|order|available|stock|can|could|the|this|that)\b", re.I)


def detect_language(message: str) -> str | None:
    """Detect an explicit language signal; return None for short/ambiguous turns."""
    value = message.strip()
    if not value:
        return None
    # A direct language preference is explicit even when the instruction itself
    # is written in another language (for example, “answer in French”).
    preference = value.lower()
    if re.search(r"\b(french|français|francais|en français|en francais)\b", preference):
        return "fr"
    if re.search(r"\b(english|anglais|in english|en anglais)\b", preference):
        return "en"
    if re.search(r"\b(arabic|darija|العربية|بالعربية|الدارجة|بالدارجة)\b", preference):
        return "ar"
    if re.search(r"[\u0600-\u06ff]", value):
        return "ar"
    french = len(_FRENCH.findall(value))
    darija = len(_DARIJA.findall(value))
    english = len(_ENGLISH.findall(value))
    # In mixed Latin-script messages, prefer the language with the strongest cue.
    if french and french >= max(darija, english):
        return "fr"
    if darija and darija >= english:
        return "ar"
    if english:
        return "en"
    # A longer sentence in Latin script provides a reasonable English signal;
    # names, SKUs, and one-word replies should preserve the saved preference.
    words = re.findall(r"[A-Za-zÀ-ÿ']+", value)
    if len(words) >= 4:
        return "en"
    return None


def language_instruction(language: str | None) -> str:
    label = LANGUAGE_LABELS.get(language or "")
    if not label:
        return ""
    return f"\n\nConversation language preference: {label}. Keep replying in this language when the customer's message is brief or ambiguous. If they clearly switch languages, follow their new language and update this preference."
