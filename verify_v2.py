"""
PHASE 4b: Verification pipeline v2 -- now with NER.

Pipeline: NER (extract entities) -> Retrieval (search using entities) -> LLM verdict

Test with: python verify_v2.py

Once you confirm this works, this REPLACES verify.py as your main pipeline
(Streamlit in Phase 5 will import from this file).
"""

import os
import json
from dotenv import load_dotenv
from groq import Groq

from ner_utils import extract_entities, entities_to_search_query
from retrieval import retrieve_evidence, format_evidence_for_prompt

load_dotenv()
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))


def build_prompt(claim: str, entities: list[dict], evidence_text: str) -> str:
    entity_summary = (
        ", ".join(f"{e['text']} ({e['label']})" for e in entities)
        if entities else "none confidently detected"
    )

    return f"""You are a medical fact-checking assistant. Analyze the health claim
below using the retrieved evidence provided as your primary grounding. If the
retrieved evidence discusses the same topic, treatment, or condition as the claim,
use it to reach a verdict even if the wording isn't identical -- use reasonable
medical judgment to connect them. Only respond "Unverified" if the evidence is
genuinely about a different topic with no meaningful overlap.

Claim to check: "{claim}"

Medical entities detected in this claim: {entity_summary}

Retrieved evidence from trusted medical sources:
{evidence_text}

Respond ONLY with valid JSON, no other text, no markdown formatting:
{{
  "verdict": "True" | "False" | "Misleading" | "Unverified",
  "confidence": <number 0-100>,
  "explanation": "<2-3 sentence plain-language explanation citing the evidence>",
  "sources": ["<source_name 1>", "<source_name 2>"]
}}
"""


def verify_claim(claim: str, top_k: int = 3) -> dict:
    """
    Full pipeline: NER -> retrieval (using entities) -> grounded LLM verdict.
    Returns a dict with verdict, confidence, explanation, sources, entities, evidence.
    """
    # Step 1: NER -- extract medical entities
    entities = extract_entities(claim)
    search_query = entities_to_search_query(claim, entities)

    # Step 2: Retrieval -- search using entity-sharpened query
    evidence = retrieve_evidence(search_query, top_k=top_k)
    evidence_text = format_evidence_for_prompt(evidence)

    # Step 3: LLM synthesis grounded in entities + evidence
    prompt = build_prompt(claim, entities, evidence_text)

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )

    raw_output = response.choices[0].message.content
    cleaned = raw_output.strip().replace("```json", "").replace("```", "").strip()

    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        retry_response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        retry_cleaned = (
            retry_response.choices[0].message.content
            .strip().replace("```json", "").replace("```", "").strip()
        )
        try:
            result = json.loads(retry_cleaned)
        except json.JSONDecodeError:
            result = {
                "verdict": "Processing Error",
                "confidence": 0,
                "explanation": "Failed to generate a structured verdict. Please try again.",
                "sources": [],
            }

    result["entities"] = entities        # NEW -- expose extracted entities
    result["search_query_used"] = search_query  # NEW -- for debugging/demo
    result["raw_evidence"] = evidence
    return result


if __name__ == "__main__":
    test_claims = [
        "Garlic cures COVID-19",
        "Regular exercise is good for your heart",
        "5G towers spread coronavirus",
    ]

    for claim in test_claims:
        print(f"\n{'='*60}")
        print(f"CLAIM: {claim}")
        print('='*60)
        result = verify_claim(claim)
        print(f"Entities:    {[(e['text'], e['label']) for e in result['entities']]}")
        print(f"Search used: '{result['search_query_used']}'")
        print(f"Verdict:     {result['verdict']}")
        print(f"Confidence:  {result['confidence']}%")
        print(f"Explanation: {result['explanation']}")
        print(f"Sources:     {result['sources']}")