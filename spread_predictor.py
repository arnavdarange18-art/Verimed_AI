"""
PHASE 6 (Option A): Spread risk scoring -- real, explainable, NOT a trained GNN.

IMPORTANT CONTEXT -- read this before changing the scoring weights:
The original project plan called for "a GAT trained on SciFact" to power
this feature. That doesn't work: SciFact contains scientific claims paired
with paper abstracts labeled Supports/Contradicts/NotEnoughInfo -- it has
zero data about how claims spread through networks (no engagement counts,
no share/forward chains, no timing). A model trained on SciFact cannot
learn virality, no matter how it's wired up. Rather than pretend to train
a GNN that couldn't have learned this task, this module computes a real,
inspectable spread-risk estimate from three signals we can actually and
honestly measure:

  1. Misinformation pattern match -- how closely this claim resembles
     already-known False/Misleading claims in your 16k+ fact ChromaDB
     knowledge base (via retrieval.py's real similarity search).
  2. Sensationalism score -- a keyword/punctuation heuristic based on
     well-documented misinformation-spread research (claims using urgency,
     secrecy, and emotional language spread faster -- see Vosoughi, Roy &
     Aral, "The spread of true and false news online", Science 2018).
  3. Entity embeddedness -- how connected this claim's medical entities are
     within a NetworkX graph built from the claim + its extracted entities
     + retrieved evidence, using real graph centrality math.

This is a heuristic scoring system, not a machine-learned model. It is
labeled as such everywhere it surfaces (API response, UI). If you later
get access to real network/engagement data (e.g. CoAID's ~296k social
engagement records), that would be the right foundation for an actual
trained spread-prediction GNN -- SciFact never was.
"""

import re
import networkx as nx

# Sensational/urgency language commonly seen in misinformation forwards.
# Not exhaustive -- a real production system would derive this list from
# labeled data rather than a hand-picked set.
SENSATIONAL_KEYWORDS = [
    "cure", "miracle", "secret", "they don't want you to know",
    "doctors hate", "banned", "shocking", "guaranteed", "100% effective",
    "forward this", "share before", "urgent", "breaking", "must read",
    "wake up", "big pharma", "cover up", "conspiracy", "instant relief",
]


def _sensationalism_score(claim_text: str) -> float:
    """
    Returns 0.0-1.0. Combines keyword presence, exclamation density, and
    ALL-CAPS word ratio -- all directly measurable from the claim text
    itself, no black box.
    """
    text_lower = claim_text.lower()
    keyword_hits = sum(1 for kw in SENSATIONAL_KEYWORDS if kw in text_lower)
    keyword_score = min(keyword_hits / 3, 1.0)  # 3+ hits already maxes this out

    exclamations = claim_text.count("!")
    exclamation_score = min(exclamations / 3, 1.0)

    words = re.findall(r"[A-Za-z]+", claim_text)
    caps_words = [w for w in words if len(w) > 2 and w.isupper()]
    caps_ratio = (len(caps_words) / len(words)) if words else 0.0
    caps_score = min(caps_ratio * 2, 1.0)

    return round(0.5 * keyword_score + 0.25 * exclamation_score + 0.25 * caps_score, 3)


def _misinformation_pattern_score(evidence: list[dict]) -> float:
    """
    Returns 0.0-1.0. Looks at the real evidence your retrieval.py already
    pulled from ChromaDB: if this claim sits close (low similarity_distance)
    to facts your knowledge base has already labeled False/Misleading,
    that's a genuine, data-grounded signal that it fits a known
    misinformation pattern -- not a guess.
    """
    if not evidence:
        return 0.0

    weighted_total = 0.0
    weight_sum = 0.0
    for e in evidence:
        # similarity_distance: lower = more similar. Convert to a similarity
        # weight in [0, 1] (clamped) so closer matches count more.
        distance = e.get("similarity_distance", 1.0)
        similarity_weight = max(0.0, 1.0 - min(distance, 1.0))
        is_misinfo = e.get("verdict") in ("False", "Misleading")
        weighted_total += similarity_weight * (1.0 if is_misinfo else 0.0)
        weight_sum += similarity_weight

    if weight_sum == 0:
        return 0.0
    return round(weighted_total / weight_sum, 3)


def _entity_embeddedness_score(claim_text: str, entities: list[dict], evidence: list[dict]) -> float:
    """
    Returns 0.0-1.0. Builds a real graph: claim node -> entity nodes ->
    evidence nodes (edge added when an entity's text appears inside a
    retrieved evidence claim). Uses NetworkX's degree_centrality on that
    graph as a genuine structural signal -- more-connected entities mean
    this claim's topic is more "embedded" in your existing knowledge base,
    which correlates with it being a well-trodden (and thus more shareable)
    topic rather than a completely novel one-off statement.
    """
    G = nx.Graph()
    claim_node = "CLAIM"
    G.add_node(claim_node)

    if not entities:
        return 0.0

    for ent in entities:
        entity_node = f"ENT::{ent['text'].lower()}"
        G.add_node(entity_node)
        G.add_edge(claim_node, entity_node)

        for i, e in enumerate(evidence):
            evidence_node = f"EVID::{i}"
            if ent["text"].lower() in e.get("matched_claim", "").lower():
                G.add_node(evidence_node)
                G.add_edge(entity_node, evidence_node)

    if G.number_of_nodes() <= 1:
        return 0.0

    centrality = nx.degree_centrality(G)
    entity_nodes = [n for n in G.nodes if n.startswith("ENT::")]
    if not entity_nodes:
        return 0.0

    avg_centrality = sum(centrality[n] for n in entity_nodes) / len(entity_nodes)
    return round(min(avg_centrality * 2, 1.0), 3)  # scaled -- small graphs rarely hit 1.0 raw


def analyze_spread_risk(claim_text: str, entities: list[dict], evidence: list[dict]) -> dict:
    """
    Combines the three signals above into a single explainable spread-risk
    estimate. Every number in the output is either directly measured from
    real data (your ChromaDB knowledge base, the claim's own text) or a
    disclosed heuristic formula -- nothing here is a black-box prediction.
    """
    misinfo_score = _misinformation_pattern_score(evidence)
    sensational_score = _sensationalism_score(claim_text)
    embeddedness_score = _entity_embeddedness_score(claim_text, entities, evidence)

    virality_score = round(
        100 * (0.5 * misinfo_score + 0.3 * sensational_score + 0.2 * embeddedness_score)
    )
    virality_score = max(0, min(100, virality_score))

    if virality_score >= 70:
        risk_level = "High Risk"
    elif virality_score >= 40:
        risk_level = "Medium Risk"
    else:
        risk_level = "Low Risk"

    # Illustrative, order-of-magnitude reach estimate -- NOT a forecast.
    # Scaled directly off virality_score with a disclosed formula, so it's
    # honest about being derived, not measured.
    if virality_score >= 70:
        reach_bucket = "Tens of thousands"
        reach_midpoint = 25000
    elif virality_score >= 40:
        reach_bucket = "Thousands"
        reach_midpoint = 3000
    else:
        reach_bucket = "Hundreds"
        reach_midpoint = 300

    # Higher risk -> assumed faster peak. Also just a disclosed heuristic.
    time_to_peak_hours = max(2, round(48 * (1 - virality_score / 100)))

    return {
        "virality_score": virality_score,
        "risk_level": risk_level,
        "predicted_nodes_reached": reach_midpoint,
        "reach_estimate_bucket": reach_bucket,
        "time_to_peak_hours": time_to_peak_hours,
        "network_hubs_vulnerable": [
            "WhatsApp Forwards (general risk channel, not claim-specific)",
            "Public Facebook Groups (general risk channel, not claim-specific)",
        ],
        "signal_breakdown": {
            "misinformation_pattern_match": misinfo_score,
            "sensational_language_score": sensational_score,
            "entity_embeddedness_score": embeddedness_score,
        },
        "is_heuristic": True,
        "methodology": (
            "Heuristic estimate combining: (1) similarity to known False/"
            "Misleading claims in the knowledge base, (2) sensational-language "
            "scoring of the claim text, (3) NetworkX graph centrality of the "
            "claim's medical entities. Not a trained machine learning model -- "
            "see spread_predictor.py for the full disclosed formula."
        ),
    }
