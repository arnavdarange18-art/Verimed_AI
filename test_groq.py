"""
PHASE 2: Prove the core loop works.
Run this FIRST, before building anything else, to confirm your Groq API key
and connection work. If this prints a verdict, your foundation is solid.

Run with: python test_groq.py
"""

import os
from dotenv import load_dotenv
from groq import Groq

load_dotenv()  # reads GROQ_API_KEY from .env file

client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# Hardcoded test claim -- no retrieval, no NER, no graph yet.
# This is ONLY testing: can we send a claim and get a structured verdict back?
TEST_CLAIM = "Garlic cures COVID-19"

PROMPT = f"""You are a medical fact-checking assistant. Analyze this health claim
and respond ONLY with valid JSON, no other text, no markdown formatting.

Claim: "{TEST_CLAIM}"

Respond in exactly this JSON format:
{{
  "verdict": "True" | "False" | "Misleading" | "Unverified",
  "confidence": <number 0-100>,
  "explanation": "<2-3 sentence plain-language explanation>"
}}
"""

def test_connection():
    print(f"Testing claim: '{TEST_CLAIM}'")
    print("Sending to Groq API...\n")

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",  # fast, free-tier, good reasoning
        messages=[
            {"role": "user", "content": PROMPT}
        ],
        temperature=0.2,  # low temperature = more consistent/factual output
    )

    raw_output = response.choices[0].message.content
    print("RAW OUTPUT:")
    print(raw_output)
    print("\n" + "=" * 50)

    # Try parsing as JSON to make sure the model followed instructions
    import json
    try:
        # Strip markdown code fences if the model added them anyway
        cleaned = raw_output.strip().replace("```json", "").replace("```", "").strip()
        parsed = json.loads(cleaned)
        print("\n✅ SUCCESS -- parsed JSON:")
        print(f"  Verdict:     {parsed['verdict']}")
        print(f"  Confidence:  {parsed['confidence']}")
        print(f"  Explanation: {parsed['explanation']}")
        print("\nYour core pipeline foundation works. Move to Phase 3 (RAG retrieval).")
    except json.JSONDecodeError as e:
        print(f"\n⚠️  Model responded but didn't return clean JSON: {e}")
        print("This is common -- Phase 3+ will add stricter JSON parsing/retry logic.")


if __name__ == "__main__":
    test_connection()
