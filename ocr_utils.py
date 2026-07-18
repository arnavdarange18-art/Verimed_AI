"""
PHASE 7: OCR module for screenshot/image claim input.

Extracts text from uploaded images (e.g. WhatsApp forward screenshots) using
EasyOCR, so claims that arrive as pictures -- not just typed text -- can be
verified.

NOTE ON LANGUAGE SCOPE:
English only for now. EasyOCR requires language packs to be loaded together
into one Reader, and not all language combinations are compatible with each
other -- so "just add every language" isn't a one-line change. Supporting
Hindi/Marathi screenshots properly means loading a second Reader instance for
those languages and routing to it based on the user's language selection.
That's flagged as follow-up work, not done here.

First run downloads EasyOCR's detection + recognition models (~100MB) --
same one-time-download pattern as the NER model in ner_utils.py.
"""

import easyocr

# Load once at import time, reuse across calls (loading the reader is the
# slow part -- don't do this per-request).
_reader = easyocr.Reader(['en'], gpu=False)

# Below this confidence, EasyOCR's guess is unreliable enough that including
# it does more harm than good to the downstream claim text.
MIN_CONFIDENCE = 0.4


def extract_text_from_image(image_bytes: bytes) -> str:
    """
    Runs OCR on raw image bytes and returns the concatenated recognized text,
    in reading order top-to-bottom as EasyOCR detects it.

    Returns an empty string if nothing readable was found above the
    confidence threshold -- callers should treat that as "OCR failed" and
    not silently pass empty text further down the pipeline.
    """
    results = _reader.readtext(image_bytes)

    lines = [text.strip() for (_bbox, text, confidence) in results if confidence >= MIN_CONFIDENCE]
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
