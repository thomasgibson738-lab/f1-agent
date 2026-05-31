# F1 Agent Project

Building a personal F1 agent with three capabilities:
1. Q&A over FIA technical and sporting regulations (RAG over PDFs)
2. Race results, lap times, and standings (FastF1 + Jolpica-F1 API)
3. Daily news digest from F1 RSS feeds

## Stack
- Python 3.11+
- Streamlit for the frontend
- Anthropic SDK with tool use as the agent loop
- LanceDB for regulation embeddings
- SQLite for caching API responses and RSS items
- pymupdf for PDF parsing (NOT pdfplumber)

## Project structure
- `src/` — application code
- `data/regs/` — FIA regulation PDFs
- `data/news/` — RSS cache
- `data/cache/` — FastF1 cache directory
- `notebooks/` — exploration only, not production code

## Conventions
- API key lives in .env, loaded via python-dotenv
- NEVER print, log, or echo ANTHROPIC_API_KEY or any other secret
- NEVER add .env to git — it's in .gitignore, keep it that way
- Always activate the .venv at `.venv/Scripts/activate` (Windows) before running Python
- Cache all Jolpica and FastF1 calls — Jolpica rate limit is 200 requests/hour
- Commit after each working feature with a descriptive message

## Data sources reference
- Jolpica-F1 (Ergast successor): https://api.jolpi.ca/ergast/f1/
- FastF1 docs: https://docs.fastf1.dev/
- OpenF1 (telemetry, 2023+): https://openf1.org/
- FIA regulations index: https://www.fia.com/regulations