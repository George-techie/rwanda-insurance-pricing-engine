# ASSAR Pricing Assistant

A pricing and information tool built over ASSAR's Approved General Business
Pricing Manual for the Rwandan Insurance Industry (Version 3). Through a
Streamlit chat it answers underwriting questions, produces deterministic premium
quotes with a step-by-step breakdown, and renders side-by-side rate comparison
tables. It combines SQL lookups for the manual's numbers with reranked hybrid
search over its prose, and it will not state a rate that is not grounded in the
manual.

## Why a hybrid of SQL and retrieval

The manual holds two kinds of content, and they are best handled in different
ways.

| Content | Stored in | Reason |
|---|---|---|
| Rate tables (fire grid, transit and marine commodity rates, liability, PA, engineering, bonds, PVT, schedules, minimums) | SQLite | The numbers must stay exact. Embedding a value such as 0.3144% would blur it. |
| Prose (definitions, conditions, warranties, exclusions, underwriting guidance) | Vector store (ChromaDB with local embeddings) | Semantic questions, where no figure is at stake. |

Premiums are computed by typed Python functions in `assar/pricing/` that read
exact rates from SQLite. The language model does not do the arithmetic. It
extracts the parameters, calls a pricing function, and phrases the result, which
keeps quotes deterministic. The pricing code is covered by 39 tests in `tests/`.

```
free-text query -> router -> pricing tools  -> SQLite rates -> deterministic premium
                        |--> table request   -> assar_info.db -> rendered comparison table
                        \--> hybrid search + rerank -> manual prose -> grounded answer
                                                  |
                                                  v
                                LLM composes a grounded answer
                                (no ungrounded figures allowed)
```

The Get a Quote tab bypasses the model and calls the calculators directly, so
pricing works with no API key. The Database tab lets you browse and run
read-only SQL against the rate tables.

## Two databases

The project keeps two SQLite files, both built from the same manual but shaped
for different uses.

- `data/assar.db`: four generic tables (`rate`, `transit_rate`, `schedule`,
  `product_rule`) that the pricing calculators read.
- `data/assar_info.db`: one table per table in the manual (45 data tables plus a
  `data_dictionary`), named and shaped so a plain question such as "what is the
  fire rate for a bank" can be answered from SQL. The `data_dictionary` records
  the unit of every column, so a percentage is never confused with a per-mille
  rate or a franc amount. The chat reads this database directly to render
  comparison tables (see below).

## Retrieval

Prose retrieval is a staged pipeline; the levers and the reasoning behind them
are documented in `docs/RETRIEVAL.md`.

- Embeddings: `BAAI/bge-base-en-v1.5` (768 dimensions), run locally through
  `sentence-transformers`.
- Hybrid first stage: dense vector search (ChromaDB) and BM25 keyword search over
  the same chunks, combined with Reciprocal Rank Fusion. Dense catches meaning,
  BM25 catches exact terms such as "reinsurance" or "ICC-A".
- Reranking: a cross-encoder (`ms-marco-MiniLM-L-6-v2`) re-scores the shortlist
  by reading the query and each passage together, so the most relevant passage
  ranks first.
- Optional multi-query expansion (off by default; uses the LLM).

Each stage is an environment toggle (`RAG_HYBRID`, `RAG_RERANK`,
`RAG_EXPANSION`). Quality is measured, not assumed:

```bash
python -m assar.rag.eval --compare   # recall@k / MRR@k: dense vs hybrid vs reranked
```

## Trustworthy answers

A small model will invent plausible-looking rates if allowed to, which is the one
failure an underwriting tool cannot have. The chat enforces grounding in code,
not by prompting: no rate, percentage or amount reaches the user unless that
exact number appears in a tool result or a retrieved manual excerpt. Anything
else is replaced with an honest request for the specific cover and sum insured.
Coverage and definition questions are answered extractively from the retrieved
passages, and a quote always shows its working (sum insured, rate, gross,
discounts, net, policy fee, final).

## Comparison tables

Asking for a table or comparison, for example "compare the goods-in-transit
options" or "table of fire rates for the different risks", matches the request to
one of the manual's tables in `assar_info.db`. The match uses the same embeddings
as retrieval and reads recent conversation turns, so a follow-up like "a table of
the options I have" inherits its subject from earlier in the chat. The chosen
table is rendered from SQL with the manual's verbatim labels and correct units.
Because the numbers come straight from the database, a rendered table cannot be
fabricated, and every cover is reachable with no per-scheme hard-coding.

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

# 1b. Optional: build the information-engine database, one SQL table per table
#     in the manual; the chat matches a request to a table and renders it
#     read-only (the model does not write SQL).
python -m assar.build_info_tables           # -> data/assar_info.db
python -m assar.build_info_tables --schema  # print the table/column catalog

# 2. Build the prose corpus from the PDF and ingest it into the vector store
#    (the first run downloads the embedding model from Hugging Face)
python -m assar.ingest

# 3. Launch the UI
streamlit run app.py
```

The PDF path is set in `assar/rag/build_corpus.py` (`PDF_PATH`); point it at your
copy of `ASSAR_s_Version_3.pdf` if it lives elsewhere.

## LLM backends

Set `LLM_BACKEND` in `.env`:

- `groq` (default): hosted, no local GPU needed. Set `GROQ_API_KEY`.
- `ollama`: local Qwen. Run `ollama pull qwen2.5:7b-instruct`, then set
  `LLM_BACKEND=ollama`.
- `hf`: Hugging Face Inference Providers. Set `HF_TOKEN`.

Embeddings run locally through `sentence-transformers` (default
`BAAI/bge-base-en-v1.5`; use `BAAI/bge-m3` for Kinyarwanda or French). Changing
`EMBED_MODEL` changes the vector dimension, so re-run `python -m assar.ingest`
after a change. The retrieval toggles (`RAG_HYBRID`, `RAG_RERANK`,
`RAG_EXPANSION`, and so on) are listed in `.env.example`.

## Inspecting the database

`data/assar.db` is a single SQLite file with four tables (`rate`,
`transit_rate`, `schedule`, `product_rule`). There are a few ways to read it:

```bash
python inspect_db.py                     # pretty-print every table
python inspect_db.py --scheme fire       # just one rate scheme
python inspect_db.py --xlsx rates.xlsx   # export all tables to one Excel workbook
python inspect_db.py --csv out/          # export each table to CSV
```

You can also open it in the Database tab of the Streamlit app, or in any SQLite
GUI such as [DB Browser for SQLite](https://sqlitebrowser.org/) or the VS Code
SQLite viewer. For the information-engine database, point the same tools at
`data/assar_info.db`.

## Tests

```bash
pytest -q        # 39 deterministic pricing tests
```

## Project layout

```
assar/
  db.py                 SQLite schema + connection
  seed.py               all rate tables transcribed from the manual
  build_db.py           builds + seeds the pricing database
  build_info_tables.py  builds data/assar_info.db (one table per manual table)
  ingest.py             convenience: build corpus + ingest vector store
  pricing/
    base.py             shared primitives (lookups, discounts, short-period, minimums)
    fire.py             fire & allied perils, consequential loss, burglary
    transit.py          GIT / transporters liability / marine cargo
    products.py         liability, PA/GPA, bonds, PVT, engineering, machinery, CPM
    registry.py         calculator registry + LLM tool schemas
  info_engine.py        catalog over assar_info.db: match a request to a table + render it
  rag/
    build_corpus.py     extract prose from the PDF -> data/corpus.md
    ingest.py           section-aware chunking + embed -> ChromaDB
    retriever.py        hybrid search (dense + BM25, RRF) + cross-encoder rerank
    eval.py             recall@k / MRR@k harness for comparing retrieval configs
  llm/
    client.py           pluggable Groq / Ollama / HF client
    router.py           routing, retrieval, tool-calling, grounding guards
app.py                  Streamlit UI (Chat, Get a Quote, Database tabs)
demo_agent.py           small multi-agent CLI over data/assar_info.db
inspect_db.py           CLI to print/export the rate tables
make_report.py          generates data/PROJECT_REPORT.pdf (no dependencies)
docs/                   RETRIEVAL.md, CALCULATORS.md (and PDFs)
tests/test_pricing.py   39 tests
data/                   assar.db, assar_info.db, corpus.md, chroma/  (generated)
```

## Before relying on the rates

The rate tables were transcribed from the PDF, so check them against the source
manual before binding cover; a wrong cell is a real underwriting error. Two
judgement calls are flagged in the code and tests:

- The voluntary-deductible bands overlap at their edges in the manual
  (`up to 250,000` and `250,000 up to 500,000`); the engine assigns an
  exact-boundary value to the higher band. Confirm this with ASSAR.
- PVT rates are quoted per mille while every other class is percent. This is
  handled throughout, but it is the easiest factor-of-ten mistake to make, so it
  is worth a deliberate check.
