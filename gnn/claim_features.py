"""
PHASE 6b: Claim -> numeric feature vector.

Turns the output of your existing verify_claim() pipeline (verdict,
confidence, entities, claim text) into a 5-dim feature vector the GNN
uses to condition its spread prediction.

Grounded in real misinformation research: false and emotionally
sensational claims spread faster than true, neutral ones (this is a
well-documented pattern, not something we invented for this feature).
"""

SENSATIONAL_KEYWORDS = [
    "cure", "miracle", "secret", "shocking", "doctors hate",
    "banned", "conspiracy", "instantly", "100%", "guaranteed",
    "they don't want you to know", "big pharma", "breakthrough",
]

VERDICT_RISK = {
    "False": 1.0,
    "Misleading": 0.6,
    "Unverified": 0.3,
    "True": 0.0,
    "Processing Error": 0.3,
}


def sensational_score(claim_text: str) -> float:
    """0-1 score for how many 'viral bait' phrases appear in the claim."""
    text_lower = claim_text.lower()
    hits = sum(1 for kw in SENSATIONAL_KEYWORDS if kw in text_lower)
    return min(hits / 3, 1.0)


def build_claim_feature_vector(
    claim_text: str,
    verdict: str,
    confidence: float,
    entities: list[dict],
) -> list[float]:
    """
    Returns a 5-dim feature vector:
      [verdict_risk, confidence_norm, entity_density, length_norm, sensational_score]
    """
    verdict_risk = VERDICT_RISK.get(verdict, 0.3)
    confidence_norm = (confidence or 0) / 100
    entity_density = min(len(entities or []) / 5, 1.0)
    length_norm = min(len(claim_text.split()) / 25, 1.0)
    sensational = sensational_score(claim_text)

    return [verdict_risk, confidence_norm, entity_density, length_norm, sensational]


if __name__ == "__main__":
    # Quick manual test -- run: python gnn/claim_features.py
    test_cases = [
        ("Garlic cures COVID-19 instantly, doctors hate this secret!", "False", 92, [{"text": "garlic"}, {"text": "COVID-19"}]),
        ("Regular exercise is good for your heart", "True", 88, [{"text": "exercise"}, {"text": "heart"}]),
    ]

    for claim, verdict, conf, entities in test_cases:
        vec = build_claim_feature_vector(claim, verdict, conf, entities)
        print(f"Claim: '{claim}'")
        print(f"  Feature vector: {[round(v, 2) for v in vec]}\n")
