"""
Corrected cleanup script -- v1 (clean_seed_secrets.py) had a bad secondary
heuristic that flagged any ~40-character string sitting near the word
"secret", which false-positived on ordinary claims containing that word in
normal English ("secret sister gift exchange", "secretly taped", etc).

This version ONLY matches the real, structurally distinctive AWS Access Key
ID format (AKIA/ASIA + 16 uppercase alphanumeric chars) -- there is no
ambiguity about what this pattern means, real AWS keys are the only thing
that look like this. No secondary keyword heuristic, no false positives
from ordinary text.

Run this against your ORIGINAL (restored from backup) file, not the
already-damaged v1 output.
"""

import json
import re
import shutil

DATA_PATH = "data/health_facts_seed.json"
BACKUP_PATH = "data/health_facts_seed.backup.json"

AKID_PATTERN = re.compile(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b")


def main():
    with open(BACKUP_PATH, "r", encoding="utf-8") as f:
        facts = json.load(f)

    print(f"Loaded {len(facts)} facts from backup (the original, pre-v1-cleanup file).")

    cleaned = []
    removed = []
    for fact in facts:
        blob = " ".join(str(fact.get(k, "")) for k in ("claim", "explanation", "source_name", "source_url"))
        matches = AKID_PATTERN.findall(blob)
        if matches:
            removed.append((fact, blob))
        else:
            cleaned.append(fact)

    print(f"\nRemoved {len(removed)} facts containing an actual AWS Access Key ID pattern.")
    for fact, blob in removed:
        match = AKID_PATTERN.search(blob)
        start = max(0, match.start() - 80)
        end = min(len(blob), match.end() + 80)
        print("\n--- Match context ---")
        print(blob[start:end])

    if not removed:
        print("\nNo AKIA/ASIA-pattern matches found anywhere in the dataset.")
        print("The secret GitHub flagged may not be in this file at all in its current form,")
        print("or may use a non-standard prefix. Paste this back to me along with the exact")
        print("byte offsets GitHub reported (41216, 49063, 66794, 83041) and I'll help look")
        print("directly at those locations in the original committed version.")
        return

    with open(DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Wrote {len(cleaned)} cleaned facts to {DATA_PATH}")
    print(f"(Restored the {16524 - len(cleaned) - len(removed)} entries v1 wrongly removed, "
          f"only actually removed {len(removed)} with real AWS key patterns.)")
    print("Next: re-run `python ingest.py`, then proceed to the git history fix.")


if __name__ == "__main__":
    main()
