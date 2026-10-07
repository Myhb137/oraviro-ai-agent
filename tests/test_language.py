from app.agent import agent
from app.database import get_conversation_language

def test_conversation_keeps_french_for_ambiguous_followup(monkeypatch):
    monkeypatch.setattr(agent, "_model", lambda: None)
    first = agent.chat_result("Bonjour, je gère une boutique en ligne.", "language-fr", "conv-fr")
    assert "Comment vos clients" in first["response"]
    assert get_conversation_language("conv-fr", "language-fr") == "fr"
    followup = agent.chat_result("oui", "language-fr", "conv-fr")
    assert "Comment vos clients" in followup["response"]

def test_conversation_keeps_arabic_for_short_english_confirmation(monkeypatch):
    monkeypatch.setattr(agent, "_model", lambda: None)
    first = agent.chat_result("السلام عليكم", "language-ar", "conv-ar")
    assert "business" not in first["response"].lower()
    agent.chat_result("yes", "language-ar", "conv-ar")
    assert get_conversation_language("conv-ar", "language-ar") == "ar"

def test_explicit_language_switch_updates_preference(monkeypatch):
    monkeypatch.setattr(agent, "_model", lambda: None)
    agent.chat_result("Bonjour, je gère une boutique en ligne.", "language-switch", "conv-switch")
    response = agent.chat_result("Please tell me what you build", "language-switch", "conv-switch")
    assert "Are your team members" in response["response"]
    assert get_conversation_language("conv-switch", "language-switch") == "en"
