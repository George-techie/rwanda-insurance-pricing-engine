# ASSAR Pricing Assistant

A hybrid RAG + SQL system over **ASSAR's Approved General Business Pricing Manual
for the Rwandan Insurance Industry (Version 3)**. It answers underwriting
questions and produces premium quotes through a Streamlit UI.

## Why hybrid (not pure RAG)

The manual has two kinds of content that need different handling:

| Content | Store | Why |
|---|---|---|
| Rate tables (Fire grid, GIT/marine commodity rates, liability, PA, engineering, bonds, PVT, schedules, minimums) | **SQLite** | Exact numbers; deterministic arithmetic. Embeddings would fuzz `0.3144%`. |
| Prose (definitions, conditions, warranties, exclusions, underwriting guidance) | **Vector store** (ChromaDB + local embeddings) | Semantic questions; no numbers at stake. |

Premiums are computed by **typed Python functions** (`assar/pricing/`) that read
exact rates from SQLite. The LLM never does the arithmetic — it extracts
parameters, calls a pricing tool, and phrases the result. That keeps quotes
deterministic and unit-tested (33 tests in `tests/`).

```
free-text query ─▶ router ─┬─▶ pricing tools  ─▶ SQLite rates ─▶ deterministic premium
                           └─▶ vector search  ─▶ manual prose  ─▶ grounded explanation
                                     │
                                     ▼
                              LLM synthesises a cited answer
```

The **Get a Quote** tab bypasses the LLM entirely and calls the calculators
directly, so the pricing demo works even with no API key. The **Database** tab
lets you browse and run read-only SQL against the rate tables directly.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate      # optional
pip install -r requirements.txt
cp .env.example .env        # then add GROQ_API_KEY (or set LLM_BACKEND=ollama)
```

## Build the data, then run

```bash
# 1. Build the rate database (SQLite) from the transcribed manual tables
python -m assar.build_db

# 1b. (Optional) Build the information-engine database — one SQL table per PDF
#     table (44 tables), tuned for a text-to-SQL agent answering general
#     number questions ("what's the fire rate for a bank?").
python -m assar.build_info_tables           # -> data/assar_info.db
python -m assar.build_info_tables --schema  # print the table/column catalog

# 2. Build the prose corpus from the PDF and ingest it into the vector store
#    (first run downloads the embedding model from Hugging Face)
python -m assar.ingest

# 3. Launch the UI
streamlit run app.py
```

> The PDF path is set in `assar/rag/build_corpus.py` (`PDF_PATH`). Point it at
> your copy of `ASSAR_s_Version_3.pdf` if it lives elsewhere.

## LLM backends

Set `LLM_BACKEND` in `.env`:

- `groq` *(default)* — fast, free tier, no local GPU. Set `GROQ_API_KEY`.
- `ollama` — local Qwen. `ollama pull qwen2.5:7b-instruct`, then `LLM_BACKEND=ollama`.
- `hf` — Hugging Face Inference Providers. Set `HF_TOKEN`.

Embeddings always run locally via `sentence-transformers` (default
`bge-small-en-v1.5`; switch to `BAAI/bge-m3` for Kinyarwanda/French).

## Inspecting the database

The database is a single SQLite file at `data/assar.db` (four tables: `rate`,
`transit_rate`, `schedule`, `product_rule`). Three ways to read it:

```bash
python inspect_db.py                  # pretty-print every table
python inspect_db.py --scheme fire    # just one rate scheme
python inspect_db.py --xlsx rates.xlsx   # export all tables to one Excel workbook
python inspect_db.py --csv out/       # export each table to CSV
```

Or open it in the **Database** tab of the Streamlit app (browse/filter/search any
table, or run read-only SQL), or in any SQLite GUI
([DB Browser for SQLite](https://sqlitebrowser.org/), VS Code SQLite Viewer).

## Tests

```bash
pytest -q        # 33 deterministic pricing tests
```

## Project layout

```
assar/
  db.py               SQLite schema + connection
  seed.py             all rate tables transcribed from the manual
  build_db.py         builds + seeds the database
  ingest.py           convenience: build corpus + ingest vector store
  pricing/
    base.py           shared primitives (lookups, discounts, short-period, minimums)
    fire.py           fire & allied perils, consequential loss, burglary
    transit.py        GIT / transporters liability / marine cargo
    products.py       liability, PA/GPA, bonds, PVT, engineering, machinery, CPM
    registry.py       calculator registry + LLM tool schemas
  rag/
    build_corpus.py   extract prose from the PDF -> data/corpus.md
    ingest.py         chunk + embed -> ChromaDB
    retriever.py      similarity search
  llm/
    client.py         pluggable Groq / Ollama / HF client
    router.py         tool-calling + retrieval + synthesis
app.py                Streamlit UI (Ask · Get a Quote · Database tabs)
inspect_db.py         CLI to print/export the rate tables
tests/test_pricing.py 33 tests
data/                 assar.db, corpus.md, chroma/   (generated)
```

## ⚠️ Before production use

The rate tables were transcribed from the PDF. **Spot-check them against the
source manual before binding cover** — a wrong cell is a real underwriting error.
Two known judgement calls are flagged in code and tests:

- **Voluntary-deductible band edges** overlap in the manual (`up to 250,000` /
  `250,000 up to 500,000`); the engine sends an exact-boundary value to the
  higher band. Confirm with ASSAR.
- **PVT rates are per mille**, every other class is percent. Handled throughout,
  but worth a deliberate check since it's the easiest 10× error to make.
