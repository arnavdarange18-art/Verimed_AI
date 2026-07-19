"""
One-time cleanup: GitHub's push protection flagged what look like real AWS
credentials embedded inside data/health_facts_seed.json. These almost
certainly came from scraped article text inside the PubHealth or
MedFact-Bench source datasets (a claim or evidence snippet that happened to
quote/reference an AWS key somewhere) -- not anything either of you typed.

This script finds every fact entry containing an AWS-Access-Key-ID-shaped
string (or a generic 40-character secret-shaped string) in any of its text
fields, removes those entries, and writes a cleaned file back out.

Run:
    python clean_seed_secrets.py

Then re-run `python ingest.py` afterward to rebuild ChromaDB from the
cleaned file before committing.
"""

import json
import re
import shutil

DATA_PATH = "data/health_facts_seed.json"
BACKUP_PATH = "data/health_facts_seed.backup.json"

# AWS Access Key ID: starts with AKIA (or ASIA for temp creds), 16 more
# uppercase-alphanumeric chars after that.
AKID_PATTERN = re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")

# Generic AWS-style secret key: 40-char base64-ish string. This is broader
# and can false-positive on unrelated long tokens/hashes, so we treat it as
# a secondary check -- entries are removed if AKID matches OR if a 40-char
# secret-shaped string sits near the word "secret"/"aws" for extra safety.
SECRET_PATTERN = re.compile(r"(?<![A-Za-z0-9/+=])[A-Za-z0-9/+=]{40}(?![A-Za-z0-9/+=])")


def looks_like_aws_secret(text: str) -> bool:
    if AKID_PATTERN.search(text):
        return True
    match = SECRET_PATTERN.search(text)
    if match:
        context = text.lower()
        if "aws" in context or "secret" in context or "access key" in context:
            return True
    return False


def main():
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        facts = json.load(f)

    print(f"Loaded {len(facts)} facts.")

    cleaned = []
    removed = []
    for fact in facts:
        blob = " ".join(str(fact.get(k, "")) for k in ("claim", "explanation", "source_name", "source_url"))
        if looks_like_aws_secret(blob):
            removed.append(fact)
        else:
            cleaned.append(fact)

    print(f"Removed {len(removed)} facts containing AWS-credential-shaped strings.")
    for i, fact in enumerate(removed):
        print(f"\n--- Removed entry {i} ---")
        print("Claim:", fact.get("claim", "")[:200])
        print("Explanation:", fact.get("explanation", "")[:200])

    if not removed:
        print("\nNo matches found with this script's patterns.")
        print("The secret GitHub flagged may use a shape this regex doesn't catch.")
        print("Check the byte offsets GitHub gave you directly, e.g.:")
        print("  python -c \"print(open('data/health_facts_seed.json', encoding='utf-8').read()[41100:41300])\"")
        return

    # Keep a backup of the original before overwriting, just in case
    shutil.copy(DATA_PATH, BACKUP_PATH)
    print(f"\nBackup of original saved to {BACKUP_PATH}")

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Wrote {len(cleaned)} cleaned facts to {DATA_PATH}")
    print("Next: re-run `python ingest.py` to rebuild ChromaDB, then re-commit.")


if __name__ == "__main__":
    main()
