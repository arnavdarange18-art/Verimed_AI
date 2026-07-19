"""
PHASE 7: OCR module for screenshot/image claim input.

Extracts text from uploaded images (e.g. WhatsApp forward screenshots) using
EasyOCR so claims that arrive as pictures -- not just typed text -- can be
verified.

The OCR path now supports the same language selections as the checker UI.
"""

from functools import lru_cache
import easyocr

# Below this confidence, EasyOCR's guess is unreliable enough that including
# it does more harm than good to the downstream claim text.
MIN_CONFIDENCE = 0.4
SUPPORTED_LANGUAGES = {"en", "hi", "mr", "es"}


@lru_cache(maxsize=8)
def _get_reader(language_code: str):
    """Create and cache an EasyOCR reader for the requested language."""
    normalized = (language_code or "en").lower()
    if normalized not in SUPPORTED_LANGUAGES:
        normalized = "en"

    candidate_langs = [normalized]
    if normalized != "en":
        candidate_langs.append("en")

    last_error = None
    for langs in candidate_langs:
        try:
            return easyocr.Reader([langs], gpu=False)
        except Exception as exc:  # pragma: no cover - depends on runtime model availability
            last_error = exc

    # Final fallback to English if the requested language pack is unavailable.
    return easyocr.Reader(["en"], gpu=False)


def extract_text_from_image(image_bytes: bytes, language_code: str = "en") -> str:
    """
    Runs OCR on raw image bytes and returns the concatenated recognized text,
    in reading order top-to-bottom as EasyOCR detects it.

    Returns an empty string if nothing readable was found above the
    confidence threshold -- callers should treat that as "OCR failed" and
    not silently pass empty text further down the pipeline.
    """
    reader = _get_reader(language_code)
    results = reader.readtext(image_bytes)

    lines = [text.strip() for (_bbox, text, confidence) in results if confidence >= MIN_CONFIDENCE]
    if not lines and language_code != "en":
        fallback_reader = _get_reader("en")
        fallback_results = fallback_reader.readtext(image_bytes)
        lines = [text.strip() for (_bbox, text, confidence) in fallback_results if confidence >= MIN_CONFIDENCE]

    return " ".join(lines).strip()


if __name__ == "__main__":
    # Quick manual test -- run: python ocr_utils.py path/to/screenshot.png
    import sys

    if len(sys.argv) < 2:
        print("Usage: python ocr_utils.py <path_to_image>")
        sys.exit(1)

    with open(sys.argv[1], "rb") as f:
        image_bytes = f.read()

    text = extract_text_from_image(image_bytes)
    if text:
        print(f"Extracted text:\n{text}")
    else:
        print("No readable text found above confidence threshold.")
