# VeriMed AI

**Health misinformation doesn't just get shared — it spreads through networks like a virus.**
VeriMed AI doesn't just fact-check claims after they go viral; it detects, explains, and predicts their spread before they cause real harm.

---

## The Problem

During COVID-19, the WHO officially declared the crisis an **"infodemic"** — false claims about cures, vaccines, and treatments directly influenced public behavior, delayed real treatment, and in some cases caused fatal self-medication.

Existing fact-checking tools fall short in three ways:
1. **They only classify, not explain** — a bare True/False label with no traceable reasoning.
2. **They only react, not predict** — claims get checked after they've already gone viral.
3. **They ignore how misinformation actually arrives** — as forwarded screenshots and regional-language messages, not clean typed English.

VeriMed AI is a layered system that detects, explains, *and* predicts — closing all three gaps.

---

## What It Actually Does

### 🔍 Claim Verification (`verify_v2.py`, `ner_utils.py`, `retrieval.py`)
- Extracts medical entities (diseases, treatments, symptoms) from a claim using a **BioBERT-style NER model** (`d4data/biomedical-ner-all`).
- Retrieves the most relevant evidence from a **ChromaDB vector store seeded with 16,500+ real, published fact-checked claims** — combined from the **PubHealth** and **MedFact-Bench** (SciFact + HealthVer + more) datasets, not hand-written guesses.
- An LLM (Groq, Llama 3.3) reasons over that retrieved evidence to produce a grounded verdict — **True / False / Misleading / Unverified** — with a confidence score, a plain-language explanation, and cited sources.

### 🌐 Multimodal & Multilingual Input (`ocr_utils.py`, `translate_utils.py`)
- Paste text, or **upload a screenshot** (e.g. a WhatsApp forward) — read automatically via **EasyOCR** (English only for now).
- Claims can be submitted in **English, Hindi, Marathi, or Spanish**; non-English text is translated before verification and the explanation is translated back for display.
- Results can be **read aloud** via browser text-to-speech, with an automatic Hindi-voice fallback on devices with no Marathi voice installed.

### 📈 Spread-Risk Scoring (`gnn/`, `spread_predictor.py`)
- A **real trained Graph Attention Network (GNN)** estimates how far and fast a claim is likely to spread.
- If the trained model can't load or inference fails for any reason, the system **falls back to an explainable heuristic scorer** (`spread_predictor.py`) that combines: similarity to known misinformation in the knowledge base, sensational-language analysis of the claim text, and NetworkX graph-centrality of its medical entities.
- **This fallback is always disclosed in the API response** (`used_trained_gnn: true/false`) — never silently presented as the trained model's output.

### ⚖️ Method Comparison (`comparison.py`)
A transparent, side-by-side comparison of three detection approaches, all scored on the same 0–100 scale:
| Method | What it uses | Limitation |
|---|---|---|
| **BERT (NER) Only** | Entity density + sensational-language patterns, no evidence | Naive baseline — no source-checking at all |
| **RAG + LLM** | Real evidence retrieved from the knowledge base, reasoned over by an LLM | Accurate on truth, but doesn't assess urgency |
| **GNN-Enhanced (Full Pipeline)** | RAG verdict + trained GNN spread-risk on top | The only method that answers both "is this false" *and* "how urgently does this need attention" |

This comparison reuses the already-computed verification and spread-risk results — no extra API calls, no extra cost.

### 🩺 Health Passport (`health_passport.py`, `pdf_export.py`, `auth.py`)
- User accounts with secure login (`flask-login`).
- Stores a personal emergency medical profile (allergies, conditions, medications, emergency contact).
- Generates a **scannable QR code** and a **printable PDF** for instant, read-only emergency sharing — no app or login required for whoever scans it.

### 📊 Dashboard & History (`db.py`)
- SQLite-backed history of every claim checked, with live dashboard stats and a trending-claims view.

---

## Architecture

```
User Input (text / screenshot / voice, any supported language)
        │
        ▼
OCR (if image) + Translation (if non-English)
        │
        ▼
BioBERT-style NER → extract medical entities
        │
        ▼
RAG Retrieval → ChromaDB search over 16,500+ real fact-checked claims
        │
        ▼
Groq LLM → grounded verdict + explanation + cited sources
        │
        ▼
Spread-Risk: trained GNN (fallback: explainable heuristic scorer)
        │
        ▼
Output → Verdict + Explanation + Sources + Spread-Risk Score
          (+ optional 3-way method comparison)
```

---

## Tech Stack

| Layer | Tool |
|---|---|
| Backend | Flask, flask-login |
| LLM | Groq API (Llama 3.3) |
| Embeddings | sentence-transformers (`all-MiniLM-L6-v2`) |
| Vector store | ChromaDB |
| NER | `transformers` — `d4data/biomedical-ner-all` (BioBERT-based) |
| Spread-risk GNN | PyTorch Geometric (Graph Attention Network) |
| Fallback scoring | NetworkX (graph centrality) |
| OCR | EasyOCR |
| Translation | deep-translator |
| PDF / QR | `qrcode[pil]`, PDF export via `pdf_export.py` |
| Database | SQLite |
| Frontend | Flask templates + Tailwind, vanilla JS |

---

## Setup

### 1. Clone and create a virtual environment
```bash
git clone https://github.com/arnavdarange18-art/Verimed_AI.git
cd Verimed_AI
python -m venv venv

# Windows
venv\Scripts\activate
# Mac/Linux
source venv/bin/activate
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Add your Groq API key
Create a `.env` file in the project root:
```
GROQ_API_KEY=your_groq_key_here
```
Get a free key at [console.groq.com/keys](https://console.groq.com/keys).

### 4. Build the knowledge base
```bash
python ingest.py
```
This embeds `data/health_facts_seed.json` (16,500+ real facts) into a local ChromaDB store (`./chroma_db`). Only needs to be run once, or after regenerating the seed data with `build_seed_dataset.py`.

### 5. Run the app
```bash
python app.py
```
Visit `http://127.0.0.1:5000`.

**First run notes:** the BioBERT NER model and EasyOCR's detection models download automatically on first use (a few hundred MB total, one-time).

---

## Known Limitations (by design, disclosed honestly)

- **OCR is English-only.** Screenshots in other languages return a clear message asking for typed text instead of silently mis-reading them.
- **Marathi text-to-speech falls back to a Hindi voice** on devices with no Marathi voice installed (same Devanagari script, closer than an English voice attempting Marathi).
- **Spread-risk fallback is explicit.** When the trained GNN can't run, the heuristic scorer is used instead and the response says so — it's never presented as trained-model output.
- **Health Passport is a hackathon-scope demo.** Single-user auth via `flask-login`, no encryption at rest. A production version would need proper encryption and access controls.
- **QR codes for emergency sharing only work on networks that can reach the running server** — for a local demo, use a tunneling tool (e.g. ngrok) or deploy the app publicly so phones on any network can scan them.

---

## Project Roadmap Origin

This project followed a phased build plan:
- **Phase 1–2:** Core Groq LLM connection
- **Phase 3:** RAG retrieval with ChromaDB
- **Phase 4:** BioBERT-based NER
- **Phase 5:** Flask UI wrapping the pipeline
- **Phase 6:** Spread-risk modeling — implemented as a real trained GNN with a disclosed, explainable heuristic fallback (the original plan's "GAT trained on SciFact" was revised after finding SciFact contains no spread/virality data to train that specific task on)
- **Phase 7:** OCR image input

---

## Team

Built collaboratively — see [contributors](https://github.com/arnavdarange18-art/Verimed_AI/graphs/contributors).
