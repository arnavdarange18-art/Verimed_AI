"""
PHASE 3a: Ingest seed health facts into ChromaDB.

Run this ONCE to build your local vector database:
    python ingest.py

This creates a ./chroma_db folder on disk with your embedded facts.
You only need to re-run this if you change health_facts_seed.json.
"""

import json
import chromadb
from chromadb.utils import embedding_functions

DATA_PATH = "data/health_facts_seed.json"
DB_PATH = "./chroma_db"
COLLECTION_NAME = "health_facts"


def ingest():
    print("Loading seed data...")
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        facts = json.load(f)
    print(f"Loaded {len(facts)} facts.")

    # Persistent client -- data survives between runs, stored on disk
    client = chromadb.PersistentClient(path=DB_PATH)

    # Free, local embedding model -- no API key/cost, runs on CPU
    embedder = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )

    # Reset collection if it already exists, so re-running this script is safe
    try:
        client.delete_collection(COLLECTION_NAME)
        print("Cleared existing collection.")
    except Exception:
        pass  # collection didn't exist yet, that's fine

    collection = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedder,
    )

    # ChromaDB needs: ids, documents (the text to embed/search), metadatas (extra data)
    ids = [f"fact_{i}" for i in range(len(facts))]
    documents = [fact["claim"] for fact in facts]  # we embed the CLAIM text
    metadatas = [
        {
            "verdict": fact["verdict"],
            "explanation": fact["explanation"],
            "source_name": fact["source_name"],
            "source_url": fact["source_url"],
        }
        for fact in facts
    ]

    # Insert in batches -- ChromaDB (and the embedding step under the hood)
    # has a max batch size, so a single collection.add() call fails once
    # the seed dataset grows into the thousands. 500 is comfortably under
    # any known limit while still being efficient.
    BATCH_SIZE = 500
    total = len(facts)
    for start in range(0, total, BATCH_SIZE):
        end = min(start + BATCH_SIZE, total)
        collection.add(
            ids=ids[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
        )
        print(f"  Ingested {end}/{total}...")

    print(f"\n✅ Ingested {total} facts into ChromaDB at '{DB_PATH}'")
    print(f"Collection '{COLLECTION_NAME}' is ready for retrieval.")


if __name__ == "__main__":
    ingest()
