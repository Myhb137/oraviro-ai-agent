"""Plain-text cleanup for all messages sent through Telegram."""
import html
import re


def telegram_plain_text(message) -> str:
    """Remove Markdown/HTML presentation syntax while keeping readable text."""
    text = str(message or "")
    text = html.unescape(text)
    text = re.sub(r"```[^\n]*\n?(.*?)```", r"\1", text, flags=re.S)
    text = re.sub(r"!?\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"<((?:https?://)[^>]+)>", r"\1", text, flags=re.I)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(?:p|div|li|h[1-6]|blockquote)\s*>", "\n", text)
    text = re.sub(r"</?[A-Za-z][^>]*>", "", text)
    text = re.sub(r"(?m)^\s*[*+]\s+", "- ", text)
    text = re.sub(r"(?m)^\s*[-=_*~#>]{3,}\s*$", "", text)
    text = re.sub(r"[*_~`#>]", "", text)
    text = re.sub(r"(?m)^\s*[-+]\s*$", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
