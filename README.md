# Sales Requirements Agent (LLM + Catalog/History Matching)

This project ingests:
- `data/lab_products.txt` (product catalog NLP doc)
- `data/product_history.xlsx` (historic purchases)

And exposes an API that:
1) Accepts a sales rep's uploaded note (structured or unstructured)
2) Extracts explicit + implicit requirements
3) Matches against catalog + historic data
4) Returns a structured JSON requirement object

## Quickstart

```bash
python -m venv venv
# Windows: venv\Scripts\activate
# Mac/Linux: source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env   # fill API keys if using real LLM

uvicorn app.main:app --reload
```

API docs: http://127.0.0.1:8000/docs

## Endpoints
- `POST /analyze/text` -> send raw text + optional structured fields
- `POST /analyze/file` -> upload txt/pdf/docx (text extraction for pdf/docx is best done upstream; this demo expects text-like files)

## LLM providers
Configured in `config.yaml`:
- `openai` (default) -> uses `OPENAI_API_KEY`
- `gemini` -> uses `GEMINI_API_KEY`
- `mock` -> no API calls, deterministic output (for local testing)



## Merged Workflow ✅
1) Open `/` (Sales Requirements UI)
2) Submit → `/output`
3) Click **Go to Quote Generation** → `/quote` (prefilled)
4) Generate quote + adjust qty (+/−/delete)
5) Click **View Insights**
