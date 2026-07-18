"""
PHASE 3c: The core verification pipeline.

This combines:
  1. Retrieval (retrieval.py) -- find relevant evidence
  2. LLM synthesis (Groq) -- generate grounded verdict

This is the function your Streamlit UI will call in Phase 5.

Test it directly with: python verify.py
"""

import os
import json
from dotenv import load_dotenv
from groq import Groq

from retrieval import retrieve_evidence, format_evidence_for_prompt

load_dotenv()
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))


def build_prompt(claim: str, evidence_text: str) -> str:
    return f"""You are a medical fact-checking assistant. Analyze the health claim
below using ONLY the retrieved evidence provided. If the evidence doesn't clearly
relate to the claim, say the claim is "Unverified" -- do not guess or use outside
knowledge not present in the evidence.

Claim to check: "{claim}"

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
    Full pipeline: retrieve evidence -> generate grounded verdict.
    Returns a dict with verdict, confidence, explanation, sources, and raw evidence.
    """
    # Step 1: Retrieval
    evidence = retrieve_evidence(claim, top_k=top_k)
    evidence_text = format_evidence_for_prompt(evidence)

    # Step 2: LLM synthesis grounded in that evidence
    prompt = build_prompt(claim, evidence_text)

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
        # Fallback if the model doesn't return clean JSON -- retry once with temp=0.1
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

    result["raw_evidence"] = evidence  # keep for UI display / debugging
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
        print(f"Verdict:     {result['verdict']}")
        print(f"Confidence:  {result['confidence']}%")
        print(f"Explanation: {result['explanation']}")
        print(f"Sources:     {result['sources']}")
