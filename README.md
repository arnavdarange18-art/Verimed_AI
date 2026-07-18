# VeriMed AI -- Setup Guide (Cursor)

## Step 1 -- Open in Cursor
1. Open Cursor
2. File -> Open Folder -> select this `verimed-ai` folder
3. Open the built-in terminal: `` Ctrl + ` `` (backtick)

## Step 2 -- Create virtual environment
```bash
python -m venv venv
```
Activate it:
```bash
# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```
You'll know it worked when you see `(venv)` at the start of your terminal line.

## Step 3 -- Install Phase 1-3 dependencies only (don't install everything yet)
```bash
pip install groq chromadb sentence-transformers python-dotenv streamlit
```

## Step 4 -- Get your free Groq API key
1. Go to https://console.groq.com/keys
2. Sign up (free, no credit card needed)
3. Click "Create API Key", copy it

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

## Step 5 -- Add your key
1. Rename `.env.example` to `.env`
2. Paste your key in: `GROQ_API_KEY=gsk_xxxxxxxxxxxx`

## Step 6 -- Run the test (THIS IS YOUR FIRST MILESTONE)
```bash
python test_groq.py
```
If you see a verdict + confidence + explanation printed, your foundation works.
Do not move to Phase 3 until this runs successfully.

## Step 7 -- Report back
Come back and tell me:
- Worked, here's the output -> we move to Phase 3 (RAG retrieval)
- Got an error: [paste error] -> I'll debug it with you

---

## What's next (don't build yet, just so you know the roadmap)
- Phase 3: Add ChromaDB + real evidence retrieval (replace hardcoded claim)
- Phase 4: Add BioBERT NER
- Phase 5: Build Streamlit UI wrapping everything we've built
- Phase 6: Add GNN (GAT trained on SciFact)
- Phase 7: Add OCR image input
