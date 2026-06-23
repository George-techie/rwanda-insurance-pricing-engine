# Retrieval pipeline — how it works and how to improve it

This document explains the retrieval stack for the ASSAR assistant: what each
component does, *why* it helps, where it lives in the code, and resources to
learn the theory. The goal is that you can reason about and tune retrieval, not
just run it.

The retrieval layer is **independent of the chat LLM**. A weak chat model
(llama-3.1-8b) does not make retrieval worse — retrieval quality is set by the
embedding model, the index, and the ranking, all of which run locally before the
LLM ever sees anything. (The one place the LLM *can* help retrieval is optional
query expansion; see lever 5.)

---

## The pipeline

```
                 ┌─────────────────────────────────────────────┐
   user query ──▶│ 5. query expansion (optional, LLM)           │
                 │    original + N paraphrases                   │
                 └───────────────────┬─────────────────────────-┘
                                     │  for each query
              ┌──────────────────────┴───────────────────────┐
              ▼                                               ▼
   ┌─────────────────────┐                       ┌────────────────────────┐
   │ 1. DENSE (semantic) │                       │ 2. SPARSE (keyword)    │
   │ bge embeddings,     │                       │ BM25 over same chunks  │
   │ cosine in ChromaDB  │                       │ (rank_bm25)            │
   └──────────┬──────────┘                       └───────────┬────────────┘
              │ top-N ids                                     │ top-N ids
              └────────────────────┬──────────────────────────┘
                                   ▼
                  ┌────────────────────────────────────┐
                  │ 3. HYBRID FUSION (RRF)              │
                  │ merge ranks, no score normalisation │
                  └────────────────┬───────────────────┘
                                   ▼ shortlist (~20)
                  ┌────────────────────────────────────┐
                  │ 4. RERANK (cross-encoder)          │
                  │ read (query, chunk) together,       │
                  │ re-score, sort                      │
                  └────────────────┬───────────────────┘
                                   ▼
                              top-k chunks ──▶ LLM
```

Code: [assar/rag/retriever.py](../assar/rag/retriever.py) (pipeline),
[assar/rag/ingest.py](../assar/rag/ingest.py) (chunking + embedding + index),
[assar/rag/eval.py](../assar/rag/eval.py) (measurement).

Every lever is a toggle (env var or constructor arg) so you can measure them one
at a time.

---

## The five levers

### 1. Dense retrieval — the embedding model
**What:** each chunk and the query are turned into a vector by a bi-encoder
(`BAAI/bge-base-en-v1.5`, 768 dimensions). We rank by cosine similarity in
ChromaDB. "Bi-encoder" = query and document are encoded *separately*, so all
chunk vectors are precomputed once at ingest and search is just a fast vector
comparison.

**Why it helps:** captures meaning, not words. "business interruption" finds the
"consequential loss" section even with no shared keywords.

**Its weakness:** a single vector is a lossy summary. It can miss exact tokens
(codes, rare terms like "PVT", "ICC-A") and it never sees the query and document
side by side.

**In this repo:** we upgraded the default from `bge-small` (384-d) to
`bge-base` (768-d) — bigger model, more expressive vectors, still CPU-friendly.
Set `EMBED_MODEL` and **re-ingest** to change it. Pick models using the MTEB
leaderboard (retrieval column).

**Learn:**
- Pinecone Learn — *Vector Embeddings for Developers* and *Sentence Transformers*: https://www.pinecone.io/learn/series/nlp/
- Sentence-Transformers docs — *Semantic Search*: https://sbert.net/examples/applications/semantic-search/README.html
- MTEB leaderboard (how to choose an embedding model): https://huggingface.co/spaces/mteb/leaderboard
- BGE / FlagEmbedding (the model family we use): https://github.com/FlagOpen/FlagEmbedding
- YouTube — James Briggs, search *"James Briggs sentence transformers semantic search"* (whole playlist on dense retrieval).

### 2. Sparse retrieval — BM25
**What:** the classic keyword ranking (term frequency × inverse document
frequency, with length normalisation). Implemented with `rank_bm25` over the
exact same chunks, tokenised on first query.

**Why it helps:** it is unbeatable at *exact term* matching — acronyms, numbers,
section names. It complements dense retrieval's weakness directly.

**In this repo:** `_build_bm25()` and `_bm25_ids_for()` in the retriever.
Toggle with `RAG_HYBRID`.

**Learn:**
- *Okapi BM25* (Wikipedia is genuinely good here): https://en.wikipedia.org/wiki/Okapi_BM25
- Pinecone Learn — *Sparse-Dense (Hybrid) Search*: https://www.pinecone.io/learn/hybrid-search-intro/

### 3. Hybrid fusion — Reciprocal Rank Fusion (RRF)
**What:** dense and BM25 produce two ranked lists on different score scales
(cosine vs BM25 score). RRF combines them by **rank**, not score:
`score(doc) = Σ 1 / (k + rank_in_list)` with `k=60`. The document that both
methods rank highly wins.

**Why RRF and not "just add the scores":** cosine (0–1) and BM25 (unbounded) are
not comparable, and normalising them is fiddly and brittle. RRF sidesteps that
entirely — it only needs the *order*. It is the standard, robust default.

**In this repo:** `_rrf_fuse()`. Tune `RAG_RRF_K` (smaller = more weight to the
very top ranks).

**Learn:**
- Cormack et al. 2009, *Reciprocal Rank Fusion outperforms Condorcet and
  individual rank learning methods* (the 2-page paper that introduced RRF):
  https://plg.uwaterloo.ca/~gvcormack/cormacksigir09-rrf.pdf
- Elastic blog — *Hybrid search and RRF*: search *"Elastic reciprocal rank fusion"*.

### 4. Reranking — the cross-encoder
**What:** a *cross-encoder* (`cross-encoder/ms-marco-MiniLM-L-6-v2`) takes
`(query, chunk)` **together** in one forward pass and outputs a relevance score.
We run it only on the ~20-chunk shortlist from fusion, then keep the top-k.

**Why it helps the most:** the bi-encoder (lever 1) never sees query and document
together, so it can't reason about their interaction. The cross-encoder does —
it's far more accurate, but too slow to run over the whole corpus. So the
standard pattern is: cheap recall first (dense+BM25 over everything), expensive
precision second (cross-encoder over a small shortlist). This "retrieve then
rerank" is the single biggest precision win in most RAG systems.

**In this repo:** `_rerank()`. Raw outputs are logits; we squash them through a
sigmoid so the reported score is a 0–1 relevance. Toggle with `RAG_RERANK`;
falls back gracefully to fused order if the model can't load.

**Learn:**
- Sentence-Transformers — *Retrieve & Re-Rank*: https://sbert.net/examples/applications/retrieve_rerank/README.html
- Cohere — *What is a Reranker / Rerank docs*: https://docs.cohere.com/docs/reranking
- DeepLearning.AI short course — *Advanced Retrieval for AI with Chroma* (covers
  cross-encoder re-ranking and query expansion, ~1 hr, free):
  https://www.deeplearning.ai/short-courses/advanced-retrieval-for-ai/

### 5. Query expansion — multi-query (optional, uses the LLM)
**What:** the LLM rewrites the question into N paraphrases with different
wording/synonyms; we retrieve for each and RRF-fuse all results. This is the
"multi-query" variant. A close cousin is **HyDE** (generate a hypothetical
*answer* and embed *that*).

**Why it helps:** fixes vocabulary mismatch — when the user's words differ from
the manual's words. It trades LLM tokens for recall, so it's **off by default**
(`RAG_EXPANSION=0`).

**In this repo:** `_expand()` — defensive: any LLM failure falls back to the
original query alone, so retrieval never breaks.

**Learn:**
- HyDE paper — Gao et al. 2022, *Precise Zero-Shot Dense Retrieval without
  Relevance Labels*: https://arxiv.org/abs/2212.10496
- DeepLearning.AI *Advanced Retrieval for AI with Chroma* (same course as above;
  it teaches query expansion by both paraphrase and generated answer).
- LangChain docs — *MultiQueryRetriever* (concept reference): https://python.langchain.com/docs/how_to/MultiQueryRetriever/

---

## Chunking (lever 0 — it sets the ceiling)

Retrieval can only return chunks that chunking created. If the answer is split
across two chunks, or buried in a 4,000-char wall, no reranker can fix it.

Our strategy ([ingest.py](../assar/rag/ingest.py)) is **structure-aware**:
- split on the manual's ALL-CAPS section headings (`_is_heading`),
- keep each section together even across page breaks,
- sub-split long sections on sentence boundaries with overlap,
- prefix every chunk with its section title (so the title's words are
  searchable and the LLM sees the context),
- carry a `page` anchor for citations and drop table-of-contents front matter.

Tune `CHUNK_TARGET` (chars per chunk) and `CHUNK_OVERLAP`, then **re-ingest** and
re-run the eval. Smaller chunks = sharper matches but more fragmentation; larger
chunks = more context but noisier vectors.

**Learn:**
- Pinecone Learn — *Chunking Strategies*: https://www.pinecone.io/learn/chunking-strategies/
- DeepLearning.AI — *Building and Evaluating Advanced RAG* (sentence-window &
  auto-merging retrieval, plus evaluation): https://www.deeplearning.ai/short-courses/building-evaluating-advanced-rag/

---

## Measuring — don't trust vibes

`assar/rag/eval.py` holds a gold set of questions, each tagged with a `marker`
phrase that exists in the chunk that actually answers it (verified against
`data/corpus.md`). A chunk "hits" if it contains the marker. We report:
- **Recall@k** — did *any* top-k chunk contain the answer? (Did we retrieve it
  at all? This is the ceiling on answer quality.)
- **MRR@k** — how high did the first correct chunk rank? (Precision/ordering —
  what reranking improves.)

```
python -m assar.rag.eval            # current env config, per-question detail
python -m assar.rag.eval --compare  # dense -> +bm25 -> +rerank, side by side
```

### Current results (k=5, 12 questions)

| config            | Recall@5 | MRR@5 |
|-------------------|---------:|------:|
| dense only (bge-base) | 1.00 | 0.938 |
| + BM25 (hybrid)       | 1.00 | 0.944 |
| + rerank              | 1.00 | **1.000** |

Reading this honestly: on this small, fairly easy gold set, **recall is already
saturated** (bge-base alone finds every answer in the top 5). The visible win is
in **MRR** — reranking pushes the correct chunk to **rank 1 every time**, which
matters because the LLM weights the first chunk most. The fusion + rerank stack
earns its keep on harder, more adversarial questions and protects against
regressions when you change the model or chunking. **Next step for you:** grow
the gold set with harder, paraphrased, and out-of-vocabulary questions until you
can see dense-only *fail* — that's where you'll watch the levers pull their
weight.

---

## How to tune (a loop, not a guess)

1. Add hard questions to `GOLD` in `eval.py` (with verified markers).
2. Run `python -m assar.rag.eval --compare` to get a baseline.
3. Change **one** thing (embedding model, chunk size, candidates, RRF k…).
4. Re-ingest if you changed the model/chunking; re-run the eval.
5. Keep the change only if the numbers improve. Commit with the before/after.

---

## What is NOT built yet (honest backlog)

- **A bigger, harder eval set** — the current 12 are a smoke test, not a benchmark.
- **HyDE** (hypothetical-document expansion) — only multi-query expansion exists.
- **Fine-tuned / domain embeddings** — we use off-the-shelf bge.
- **Metadata filtering** (e.g. restrict to a product's pages before ranking).
- **Answer-level evaluation** (faithfulness/groundedness, e.g. RAGAS) — we only
  measure retrieval, not the final generated answer.
