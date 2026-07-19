"""
Builds a large data/health_facts_seed.json from real, published, citable
fact-verification datasets via the Hugging Face `datasets` library --
instead of hand-written facts.

Install once:
    pip install datasets

Run:
    python build_seed_dataset.py

WHAT THIS PULLS IN (all real, citable, used in published research):
  1. PubHealth (health_fact)   -- ~11,800 public health claims, 4-way
     verdict (true/false/unproven/mixture) + a written explanation for each.
     Paper: Kotonya & Toni, "Explainable Automated Fact-Checking for Public
     Health Claims", EMNLP 2020.
  2. MedFact-Bench (ncbi)      -- ~14,270 claims. This one dataset already
     combines SciFact, HealthVer, MedAESQA, PubMedQA-Fact, and BioASQ-Fact
     into a single unified claim/evidence/label format, published by NIH/NCBI
     researchers.

Combined (after de-duplication): roughly 20,000-25,000 real, sourced facts.

WHY NOT MORE:
Datasets of "lakhs" of genuinely verified health facts don't really exist
publicly. FEVER (185k claims) exists but is GENERAL fact-checking over
Wikipedia trivia, not health-specific -- mixing it in would dilute your
knowledge base with irrelevant claims about films, geography, etc. Public,
health-specific, citably-sourced fact-checking data tops out in the tens of
thousands across all known datasets combined. This script gets you into
that ceiling territory honestly, rather than fabricating volume.

IMPORTANT -- THIS WASN'T TESTED END-TO-END:
I don't have network access to huggingface.co from where I wrote this, so
I could not run it myself. Dataset schemas occasionally drift between
versions. If a load fails or you get 0 facts from a source, the script
will print the actual error and, where possible, the real column names it
found -- paste that back and I'll fix the mapping.
"""

import json
from datasets import load_dataset

OUTPUT_PATH = "data/health_facts_seed.json"


def safe_label_name(feature, label_idx):
    """
    Resolve an integer label back to its string name using the dataset's
    own ClassLabel definition, instead of hardcoding an index->name mapping
    -- hardcoded mappings are exactly the kind of thing that silently
    breaks when a dataset's internal label order changes between versions.
    """
    try:
        return feature.int2str(label_idx)
    except Exception:
        return str(label_idx)


def normalize_verdict(raw_label: str) -> str:
    """Map each dataset's own label vocabulary onto VeriMed's 4-way verdict."""
    raw_label = (raw_label or "").strip().lower()
    mapping = {
        "true": "True",
        "false": "False",
        "mixture": "Misleading",
        "misleading": "Misleading",
        "unproven": "Unverified",
        "support": "True",
        "supports": "True",
        "contradict": "False",
        "contradicts": "False",
        "refute": "False",
        "refutes": "False",
        "nei": "Unverified",
        "not_enough_info": "Unverified",
        "not enough information": "Unverified",
    }
    return mapping.get(raw_label, "Unverified")


def load_pubhealth():
    print("Loading PubHealth (bigbio/pubhealth, pubhealth_source, parquet branch)...")
    facts = []

    # bigbio/pubhealth's main branch still carries an old-style "loading
    # script" (pubhealth.py), which newer `datasets` versions refuse to run
    # under any circumstances -- so load_dataset("bigbio/pubhealth", ...)
    # keeps finding that script no matter what config we pass.
    #
    # HuggingFace auto-converts script-based datasets to Parquet on a
    # SEPARATE branch: refs/convert/parquet. Pointing the generic "parquet"
    # loader directly at files on that branch sidesteps the script entirely.
    base = "https://huggingface.co/datasets/bigbio/pubhealth/resolve/refs%2Fconvert%2Fparquet/pubhealth_source/"
    data_files = {
        "train": base + "train/0000.parquet",
        "validation": base + "validation/0000.parquet",
        "test": base + "test/0000.parquet",
    }

    try:
        ds = load_dataset("parquet", data_files=data_files)
    except Exception as e:
        print(f"  Could not load PubHealth via direct parquet URLs: {e}")
        print("  Skipping PubHealth -- MedFact-Bench facts will still be used.")
        return facts

    claim_keys = ["claim", "text", "claim_text"]
    label_keys = ["label", "verdict", "veracity"]
    explanation_keys = ["explanation", "justification"]
    source_keys = ["sources", "source_url", "main_text_url"]

    printed_debug = False
    for split in ds:
        label_feature = None
        try:
            label_feature = ds[split].features.get("label")
        except Exception:
            pass

        for row in ds[split]:
            claim = ""
            for k in claim_keys:
                if row.get(k):
                    claim = str(row[k]).strip()
                    break

            if not claim:
                if not printed_debug:
                    print(f"  Couldn't find a claim field. Available columns: {list(row.keys())}")
                    printed_debug = True
                continue

            raw_label = None
            for k in label_keys:
                if k in row and row[k] is not None:
                    raw_label = row[k]
                    break

            if isinstance(raw_label, int) and label_feature is not None:
                verdict = normalize_verdict(safe_label_name(label_feature, raw_label))
            else:
                verdict = normalize_verdict(str(raw_label) if raw_label is not None else "")

            explanation = ""
            for k in explanation_keys:
                if row.get(k):
                    explanation = str(row[k]).strip()
                    break

            source_url = ""
            for k in source_keys:
                val = row.get(k)
                if val:
                    source_url = val[0] if isinstance(val, list) and val else (val if isinstance(val, str) else "")
                    break

            facts.append({
                "claim": claim,
                "verdict": verdict,
                "explanation": explanation[:1000] if explanation else "See original source for detailed explanation.",
                "source_name": "PubHealth Dataset (Kotonya & Toni, EMNLP 2020)",
                "source_url": source_url,
            })
    print(f"  -> {len(facts)} facts")
    return facts


def load_medfact_bench():
    print("Loading MedFact-Bench (SciFact + HealthVer + MedAESQA + PubMedQA-Fact + BioASQ-Fact)...")
    facts = []
    try:
        ds = load_dataset("ncbi/MedFact-Bench")
    except Exception as e:
        print(f"  Could not load MedFact-Bench: {e}")
        return facts

    for split in ds:
        for row in ds[split]:
            claim = (row.get("claim") or "").strip()
            raw_label = row.get("label") or ""
            source_dataset = row.get("dataset") or "MedFact-Bench"
            evidence_text = (row.get("source") or "").strip()
            if not claim:
                continue
            verdict = normalize_verdict(raw_label)
            explanation = (
                f"Evidence from {source_dataset}: {evidence_text[:500]}"
                if evidence_text else f"Verdict sourced from the {source_dataset} benchmark."
            )
            facts.append({
                "claim": claim,
                "verdict": verdict,
                "explanation": explanation,
                "source_name": f"MedFact-Bench / {source_dataset}",
                "source_url": "https://huggingface.co/datasets/ncbi/MedFact-Bench",
            })
    print(f"  -> {len(facts)} facts")
    return facts


def main():
    all_facts = []
    all_facts.extend(load_pubhealth())
    all_facts.extend(load_medfact_bench())

    if not all_facts:
        print("\nNo facts were loaded from either source -- check the errors above.")
        print("Your existing data/health_facts_seed.json was NOT modified.")
        return

    # De-duplicate identical claims (the datasets overlap in places)
    seen = set()
    deduped = []
    for f in all_facts:
        key = f["claim"].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(f)

    print(f"\nTotal facts before dedup: {len(all_facts)}")
    print(f"Total facts after dedup:  {len(deduped)}")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(deduped, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Wrote {len(deduped)} facts to {OUTPUT_PATH}")
    print("Next step: re-run `python ingest.py` to rebuild your ChromaDB with this larger dataset.")


if __name__ == "__main__":
    main()
