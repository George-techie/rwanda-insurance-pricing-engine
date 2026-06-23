"""Retrieve relevant prose chunks from the ASSAR manual.

This retriever stacks the classic RAG quality levers, each independently
toggleable so you can measure them one at a time (see assar/rag/eval.py):

  1. Dense retrieval   - semantic vector search over bge embeddings (ChromaDB).
  2. Sparse retrieval  - BM25 keyword search (rank_bm25) over the same chunks.
  3. Hybrid fusion     - combine dense + sparse ranks with Reciprocal Rank
                         Fusion (RRF). Catches exact terms (e.g. "reinsurance",
                         "PVT") that pure embeddings miss, plus the semantics.
  4. Reranking         - a cross-encoder re-scores the fused shortlist by reading
                         (query, chunk) together. Far more precise than the
                         bi-encoder used for first-stage recall.
  5. Query expansion   - the LLM rewrites the question into a few paraphrases;
                         we retrieve for each and fuse. Helps vocabulary
                         mismatch. Costs LLM tokens, so it is OFF by default.

Pipeline: (expand?) -> [dense + bm25] per query -> RRF fuse -> (rerank?) -> top-k.

Config via env (all have sensible defaults):
  RAG_HYBRID=1        dense+BM25 fusion (default on)
  RAG_RERANK=1        cross-encoder rerank (default on)
  RAG_EXPANSION=0     LLM multi-query expansion (default off, uses tokens)
  RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
  RAG_CANDIDATES=20   shortlist size pulled from each first-stage retriever
  RAG_RRF_K=60        RRF damping constant
  RAG_EXPANSION_N=3   number of LLM paraphrases
"""
from __future__ import annotations

import functools
import os
import re
from pathlib import Path

from .ingest import CHROMA_DIR, COLLECTION, EMBED_MODEL

DATA_DIR = Path(__file__).resolve().parents[2] / "data"

RERANK_MODEL = os.getenv("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")


def _flag(name: str, default: bool) -> bool:
    return os.getenv(name, "1" if default else "0").strip().lower() in ("1", "true", "yes", "on")


_WORD = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def _rrf_fuse(ranked_lists: list[list[str]], k: int = 60) -> dict[str, float]:
    """Reciprocal Rank Fusion. Each input is an ordered list of chunk ids
    (best first). Returns {id: fused_score}. Rank-based, so it needs no score
    normalisation between dense (cosine) and sparse (BM25) — that is exactly why
    RRF is the standard, robust way to combine heterogeneous rankers."""
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, cid in enumerate(ranked):
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
    return scores


class Retriever:
    """Lazy-loaded hybrid retriever. Construction is cheap; the models, the DB
    and the BM25 index load on first query."""

    def __init__(
        self,
        persist_dir: Path = CHROMA_DIR,
        model_name: str = EMBED_MODEL,
        *,
        hybrid: bool | None = None,
        rerank: bool | None = None,
        expansion: bool | None = None,
        candidates: int | None = None,
        rrf_k: int | None = None,
        expansion_n: int | None = None,
        rerank_model: str = RERANK_MODEL,
    ):
        self.persist_dir = persist_dir
        self.model_name = model_name
        self.hybrid = _flag("RAG_HYBRID", True) if hybrid is None else hybrid
        self.rerank = _flag("RAG_RERANK", True) if rerank is None else rerank
        self.expansion = _flag("RAG_EXPANSION", False) if expansion is None else expansion
        self.candidates = int(os.getenv("RAG_CANDIDATES", "20")) if candidates is None else candidates
        self.rrf_k = int(os.getenv("RAG_RRF_K", "60")) if rrf_k is None else rrf_k
        self.expansion_n = int(os.getenv("RAG_EXPANSION_N", "3")) if expansion_n is None else expansion_n
        self.rerank_model = rerank_model

        self._model = None
        self._coll = None
        self._docs: dict[str, dict] = {}   # id -> {text, page, section}
        self._bm25 = None
        self._bm25_ids: list[str] = []
        self._cross = None
        self._cross_failed = False

    @property
    def available(self) -> bool:
        if not self.persist_dir.exists():
            return False
        return (self.persist_dir / "chroma.sqlite3").exists() or any(self.persist_dir.glob("*"))

    # --------------------------------------------------------------------- #
    # Lazy loading
    # --------------------------------------------------------------------- #
    def _ensure(self):
        if self._coll is not None:
            return
        import chromadb
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self.model_name)
        client = chromadb.PersistentClient(path=str(self.persist_dir))
        self._coll = client.get_collection(COLLECTION)

        # Pull every chunk once: needed for BM25 and for materialising results.
        got = self._coll.get(include=["documents", "metadatas"])
        for cid, doc, meta in zip(got["ids"], got["documents"], got["metadatas"]):
            self._docs[cid] = {
                "text": doc,
                "page": (meta or {}).get("page"),
                "section": (meta or {}).get("section", ""),
            }
        if self.hybrid:
            self._build_bm25()

    def _build_bm25(self):
        from rank_bm25 import BM25Okapi

        self._bm25_ids = list(self._docs.keys())
        corpus = [_tokenize(self._docs[cid]["text"]) for cid in self._bm25_ids]
        self._bm25 = BM25Okapi(corpus)

    def _ensure_cross(self):
        if self._cross is not None or self._cross_failed:
            return
        try:
            from sentence_transformers import CrossEncoder

            self._cross = CrossEncoder(self.rerank_model)
        except Exception as e:  # missing model / offline -> degrade gracefully
            self._cross_failed = True
            print(f"[retriever] reranker unavailable ({e}); continuing without rerank")

    # --------------------------------------------------------------------- #
    # First-stage retrievers (return ordered lists of chunk ids)
    # --------------------------------------------------------------------- #
    def _dense_ids(self, query: str, n: int) -> list[str]:
        emb = self._model.encode([query], normalize_embeddings=True).tolist()
        res = self._coll.query(query_embeddings=emb, n_results=min(n, len(self._docs)))
        return list(res.get("ids", [[]])[0])

    def _bm25_ids_for(self, query: str, n: int) -> list[str]:
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(_tokenize(query))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [self._bm25_ids[i] for i in order[:n]]

    def _expand(self, query: str) -> list[str]:
        """Use the LLM to produce paraphrases of the query. Returns [] on any
        failure so retrieval always proceeds with at least the original query."""
        try:
            from ..llm.client import get_client

            client = get_client()
            if not client.ready:
                return []
            prompt = (
                "Rewrite the user's insurance question into "
                f"{self.expansion_n} alternative search queries that use different "
                "wording and synonyms but keep the same meaning. One per line, no "
                "numbering, no extra text.\n\nQuestion: " + query
            )
            msg = client.chat(
                [{"role": "user", "content": prompt}], tools=None, temperature=0.3
            )
            lines = [l.strip(" -*\t") for l in (msg.content or "").splitlines()]
            return [l for l in lines if l][: self.expansion_n]
        except Exception:
            return []

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #
    def search(self, query: str, k: int = 4) -> list[dict]:
        """Return [{text, page, section, score}] for the top-k chunks."""
        self._ensure()
        if not self._docs:
            return []

        queries = [query]
        if self.expansion:
            queries += self._expand(query)

        # First-stage recall: dense (+ BM25 if hybrid) for every query variant.
        ranked_lists: list[list[str]] = []
        for q in queries:
            ranked_lists.append(self._dense_ids(q, self.candidates))
            if self.hybrid:
                ranked_lists.append(self._bm25_ids_for(q, self.candidates))

        fused = _rrf_fuse(ranked_lists, k=self.rrf_k)
        shortlist = sorted(fused, key=lambda cid: fused[cid], reverse=True)

        if self.rerank and shortlist:
            ranked = self._rerank(query, shortlist)
        else:
            ranked = [(cid, fused[cid]) for cid in shortlist]

        out = []
        for cid, score in ranked[:k]:
            d = self._docs[cid]
            out.append({"text": d["text"], "page": d["page"],
                        "section": d["section"], "score": float(score)})
        return out

    def _rerank(self, query: str, shortlist: list[str]) -> list[tuple[str, float]]:
        """Cross-encoder rerank of the fused shortlist. Falls back to fused order
        if the reranker can't load. Raw cross-encoder outputs are logits; we map
        them through a sigmoid so the returned score is a 0..1 relevance, in line
        with the dense path (and readable in the UI)."""
        import math

        self._ensure_cross()
        if self._cross is None:
            return [(cid, 0.0) for cid in shortlist]
        cand = shortlist[: max(self.candidates, 1)]
        pairs = [(query, self._docs[cid]["text"]) for cid in cand]
        scores = self._cross.predict(pairs)
        ranked = sorted(zip(cand, scores), key=lambda t: float(t[1]), reverse=True)
        return [(cid, 1.0 / (1.0 + math.exp(-float(s)))) for cid, s in ranked]

    def describe(self) -> str:
        bits = [f"dense({self.model_name.split('/')[-1]})"]
        if self.hybrid:
            bits.append("bm25")
        if self.rerank:
            bits.append(f"rerank({self.rerank_model.split('/')[-1]})")
        if self.expansion:
            bits.append(f"expand x{self.expansion_n}")
        return " + ".join(bits)


@functools.lru_cache(maxsize=1)
def get_retriever() -> Retriever:
    return Retriever()
