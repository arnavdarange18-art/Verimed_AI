"""
PHASE 4: Medical Named Entity Recognition (NER).

Extracts medical entities (diseases, treatments, symptoms, medications) from
a health claim using a BERT-based biomedical NER model.

NOTE ON MODEL CHOICE:
`dmis-lab/biobert-v1.1` (the base BioBERT checkpoint your teacher mentioned) is a
BERT encoder pretrained on biomedical text, but it has no classification head --
it can't do NER out of the box without fine-tuning it yourself on a labeled dataset
(e.g. NCBI-disease or BC5CDR), which takes real training time.

For a working hackathon pipeline, we use `d4data/biomedical-ner-all` -- a model
that IS BioBERT, already fine-tuned for token classification (NER) on biomedical
text. Same underlying BERT/biomedical-transformer technology, just already trained
for exactly this task so it works out of the box. This satisfies the "use BERT"
requirement while being immediately usable.

First run will download the model (~400MB) -- this is normal, only happens once.
"""

from transformers import pipeline

# Load once, reuse across calls (loading the model is the slow part)
_ner_pipeline = pipeline(
    "token-classification",
    model="d4data/biomedical-ner-all",
    aggregation_strategy="simple",  # merges sub-word tokens into full entity words
)

CONFIDENCE_THRESHOLD = 0.50  # lowered slightly -- was excluding useful entities like food/drug terms


def extract_entities(claim_text: str) -> list[dict]:
    """
    Extract medical entities from a claim.

    Returns a list of dicts like:
    [
        {"text": "COVID-19", "label": "Disease_disorder", "confidence": 0.97},
        {"text": "garlic", "label": "Food", "confidence": 0.81},
        ...
    ]
    """
    raw_entities = _ner_pipeline(claim_text)

    entities = []
    for ent in raw_entities:
        if ent["score"] >= CONFIDENCE_THRESHOLD:
            entities.append({
                "text": ent["word"].strip(),
                "label": ent["entity_group"],
                "confidence": round(float(ent["score"]), 2),
            })

    return entities


def entities_to_search_query(claim_text: str, entities: list[dict]) -> str:
    """
    Build a search query that COMBINES the original claim with extracted
    entities (not replace it). This keeps full sentence context for the
    embedding model while giving extra weight to the key medical terms.

    Replacing the claim entirely with just entity words was losing context
    and hurting retrieval accuracy -- combining is more robust.
    """
    if not entities:
        return claim_text

    entity_terms = " ".join(e["text"] for e in entities)
    return f"{claim_text} {entity_terms}"  # original context + entity emphasis


if __name__ == "__main__":
    # Quick manual test -- run: python ner_utils.py
    test_claims = [
        "Garlic cures COVID-19",
        "Vitamin C supplements prevent the common cold",
        "Ibuprofen worsens coronavirus symptoms",
    ]

    for claim in test_claims:
        print(f"\nClaim: '{claim}'")
        entities = extract_entities(claim)
        if entities:
            for e in entities:
                print(f"  -> {e['text']}  [{e['label']}]  confidence={e['confidence']}")
            print(f"  Search query: '{entities_to_search_query(claim, entities)}'")
        else:
            print("  No entities extracted above confidence threshold.")