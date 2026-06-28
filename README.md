# Rwandan Insurance AI Assistant

The conversational AI layer for Rwandan general (non-life) insurance, built over
ASSAR's Approved General Business Pricing Manual (Version 3). Through a Streamlit
chat it answers underwriting questions, produces premium quotes with a
step-by-step breakdown, and renders side-by-side rate comparison tables. It will
not state a rate that is not grounded in a tool result or the manual.

It is designed to sit on top of the **CoverSoko underwriting engine**: property
pricing is computed by CoverSoko's API (the source of truth), with the local
ASSAR calculators kept as an offline fallback. The retrieval-augmented answers
over the manual's prose are the part unique to this layer.

## Where the numbers and the prose come from

| Content | Source | Notes |
|---|---|---|
| Property / fire premiums | **CoverSoko API** (PostgreSQL), via the `quote_property` tool | the source of truth when configured |
| Property / fire fallback | local ASSAR calculator (SQLite) | used only when the engine is unreachable |
| Other lines (liability, PA, transit, marine, bonds, PVT, engineering, machinery) | local typed calculators (SQLite) | deterministic, unit-tested |
| Comparison tables | local info engine (`assar_info.db`, the 45 ASSAR tables) | rendered read-only |
| Prose (definitions, conditions, warranties, exclusions, guidance) | vector store (ChromaDB, local embeddings) | the RAG layer, unique to this assistant |

The language model never writes SQL and never does arithmetic. It extracts
parameters and calls typed tools; the server (CoverSoko, or the local
calculators) runs the query and computes the premium.

```
user question
   -> router
       |-- property / fire quote -> CoverSoko API (Postgres) -> premium      [primary]
       |                            (local ASSAR calculator if engine is down) [fallback]
       |-- other quote           -> local typed calculators (SQLite)
       |-- table / comparison    -> info engine (SQLite, ASSAR tables)
       \-- concept / definition  -> hybrid retrieval + rerank -> manual prose
                                 -> LLM composes a grounded answer (no ungrounded figures)
```

## What it does

- **Multi-turn chat** that remembers the conversation.
- **Grounded answers**: no rate, percentage or amount is shown unless it comes
  from a tool result or a retrieved passage; otherwise it asks for specifics
  instead of guessing. Enforced in code, not by prompting.
- **Quotes with full working**: every quote shows a step-by-step breakdown
  (sum insured, rate, gross, discounts, net, fee, final).
- **Comparison tables**: a plain-language request is matched to the right manual
  table and rendered read-only.
- **Multi-insurer tenancy**: per-insurer rate overrides overlay a shared base;
  the acting insurer comes from authenticated context, never from user input.
- **Audit trail**: every turn records its ordered decisions (retrieval, routing,
  tool calls, grounding guard) for failure isolation; persisted to
  `data/traces.jsonl`.

## Pricing: CoverSoko primary, local fallback

When `COVERSOKO_API_URL` is set, property/fire pricing goes through CoverSoko's
`POST /api/quote` (the `quote_property` tool), and the overlapping local
`quote_fire` is hidden from the model. If the engine is unreachable, the
assistant falls back to the local ASSAR calculator and labels the result as a
fallback. When `COVERSOKO_API_URL` is unset, everything is priced locally.

The tenant (CoverSoko `ownerId`) is read from config (`COVERSOKO_OWNER_ID`),
never chosen by the model. See `docs/COVERSOKO_INTEGRATION.md` for the field
mapping and run steps.

## Retrieval pipeline

Concept questions are answered by a staged pipeline (see `docs/RETRIEVAL.md`):
`BAAI/bge-base-en-v1.5` embeddings, dense + BM25 hybrid fused with Reciprocal
Rank Fusion, then a cross-encoder reranker, with optional multi-query expansion.
Each stage is an env toggle; quality is measured with
`python -m assar.rag.eval --compare` (recall@k / MRR@k).

## Setup and run

```bash
python -m venv .venv && source .venv/bin/activate      # optional
pip install -r requirements.txt
cp .env.example .env        # add GROQ_API_KEY (or set LLM_BACKEND=ollama)
```

Build the data, then run:

```bash
python -m assar.build_db            # local pricing database (SQLite)
python -m assar.build_info_tables   # info-engine database (45 ASSAR tables)
python -m assar.ingest              # build the vector store (downloads the embedding model once)
streamlit run app.py                # chat on http://localhost:8501
```

### Connect it to the CoverSoko engine

1. Start the engine (in the `coversoko-underwriter` repo): `docker compose up --build`
   (API on http://localhost:3500).
2. Add to this app's `.env`: `COVERSOKO_API_URL=http://localhost:3500`
   (optionally `COVERSOKO_OWNER_ID=<insurer-uuid>` for that insurer's overrides).
3. `python -m assar.integrations.coversoko` to confirm reachability, then run the app.
   Property quotes now price through CoverSoko; everything else is unchanged.

## LLM backends

Set `LLM_BACKEND` in `.env`: `groq` (default, hosted), `ollama` (local Qwen), or
`hf`. Embeddings always run locally through `sentence-transformers`
(`BAAI/bge-base-en-v1.5`; changing it requires a re-ingest). Retrieval and
CoverSoko toggles are documented in `.env.example`.

## Tests

```bash
pytest -q        # 53 tests (deterministic pricing + CoverSoko contract, HTTP mocked)
```

## Project layout

```
assar/
  db.py / seed.py / build_db.py     local pricing DB (rate, transit, schedule, rules, tenancy)
  build_info_tables.py              info-engine DB (one table per ASSAR table)
  tenancy.py                        per-insurer overrides + scoped access (contextvar)
  trace.py                          per-turn audit trail + JSONL logger
  pricing/                          typed calculators + tool registry (local fallback)
  integrations/coversoko.py         CoverSoko API client (the primary pricing path)
  rag/                              chunking, hybrid retrieval + rerank, eval harness
  llm/                              pluggable client + router (routing, tools, guards, trace)
  info_engine.py                    semantic table matching -> rendered comparison tables
app.py                              Streamlit UI (Chat, Get a Quote, Database)
docs/                               RETRIEVAL.md, COVERSOKO_INTEGRATION.md, CALCULATORS.md
tests/                              53 tests
data/                               assar.db, assar_info.db, corpus.md, chroma/  (generated)
```

## Before relying on the rates

When connected to CoverSoko, premiums come from the engine. The local
calculators and the info tables were transcribed from the manual and may differ
slightly from the engine; verify against the source before binding cover. PVT is
quoted per mille while every other class is percent, the easiest factor-of-ten
mistake to make.
