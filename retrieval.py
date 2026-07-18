"""
PHASE 3b: Retrieval module.

Given a user's claim, finds the top-k most semantically similar verified
facts from the ChromaDB knowledge base. This is the "R" in RAG.

Import and use retrieve_evidence() from your app -- don't run this file directly.
"""

import chromadb
from chromadb.utils import embedding_functions

DB_PATH = "./chroma_db"
COLLECTION_NAME = "health_facts"

# Load once, reuse across calls (avoid reloading the embedding model every query)
_client = chromadb.PersistentClient(path=DB_PATH)
_embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)
_collection = _client.get_collection(
    name=COLLECTION_NAME,
    embedding_function=_embedder,
)


def retrieve_evidence(claim_text: str, top_k: int = 3) -> list[dict]:
    """
    Search the knowledge base for facts most similar to the input claim.

    Returns a list of dicts like:
    [
        {
            "matched_claim": "...",
            "verdict": "False",
            "explanation": "...",
            "source_name": "WHO",
            "source_url": "...",
            "similarity_distance": 0.12   # lower = more similar
        },
        ...
    ]
    """
    results = _collection.query(
        query_texts=[claim_text],
        n_results=top_k,
    )

    evidence = []
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    for doc, meta, dist in zip(documents, metadatas, distances):
        evidence.append({
            "matched_claim": doc,
            "verdict": meta["verdict"],
            "explanation": meta["explanation"],
            "source_name": meta["source_name"],
            "source_url": meta["source_url"],
            "similarity_distance": dist,
        })

    return evidence


def format_evidence_for_prompt(evidence: list[dict]) -> str:
    """Turn retrieved evidence into a clean text block to insert into the LLM prompt."""
    if not evidence:
        return "No relevant evidence found in knowledge base."

    lines = []
    for i, e in enumerate(evidence, start=1):
        lines.append(
            f"{i}. Similar known claim: \"{e['matched_claim']}\"\n"
            f"   Verdict: {e['verdict']}\n"
            f"   Explanation: {e['explanation']}\n"
            f"   Source: {e['source_name']} ({e['source_url']})"
        )
    return "\n\n".join(lines)


if __name__ == "__main__":
    # Quick manual test -- run: python retrieval.py
    test_claim = "Does eating garlic protect you from coronavirus?"
    print(f"Testing retrieval for: '{test_claim}'\n")

    results = retrieve_evidence(test_claim, top_k=3)
    print(format_evidence_for_prompt(results))
