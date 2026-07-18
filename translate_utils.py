"""
Translation module.

Uses deep-translator's GoogleTranslator wrapper -- free, no API key required.
Used to:
  1. Translate a non-English claim INTO English before running it through
     the NER/RAG/LLM pipeline (which is English-only under the hood)
  2. Translate the English explanation BACK into the user's language for display

Language codes match the <select> in checker.html: en, hi, mr, es
"""

from deep_translator import GoogleTranslator

SUPPORTED_LANGUAGES = {"en", "hi", "mr", "es"}


def translate_to_english(text: str, source_lang: str) -> str:
    """Translate claim text into English. No-op if already English."""
    if source_lang == "en" or not text.strip():
        return text
    try:
        return GoogleTranslator(source=source_lang, target="en").translate(text)
    except Exception:
        # If translation fails (network issue, unsupported text), fall back to
        # the original text rather than breaking the whole verification flow.
        return text


def translate_from_english(text: str, target_lang: str) -> str:
    """Translate an explanation from English into the user's language. No-op if English."""
    if target_lang == "en" or not text.strip():
        return text
    try:
        return GoogleTranslator(source="en", target=target_lang).translate(text)
    except Exception:
        return text


if __name__ == "__main__":
    # Quick manual test -- run: python translate_utils.py
    hindi_claim = "लहसुन कोविड-19 को ठीक करता है"
    english = translate_to_english(hindi_claim, "hi")
    print(f"Hindi -> English: {english}")

    back = translate_from_english("Garlic does not cure COVID-19.", "hi")
    print(f"English -> Hindi: {back}")
