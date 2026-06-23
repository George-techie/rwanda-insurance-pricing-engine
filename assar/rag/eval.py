"""Measure retrieval quality so changes are data-driven, not vibes.

Each labelled question carries a `marker`: a distinctive phrase that appears in
the chunk that actually answers it (verified to exist in data/corpus.md). A
retrieved chunk counts as a hit if it contains the marker (case-insensitive).
Over the question set we report:

  Recall@k : fraction of questions with at least one hit in the top-k
  MRR@k    : mean reciprocal rank of the first hit (0 if none in top-k)

This is the "answer-bearing passage" proxy used throughout RAG evaluation: if
the chunk holding the answer never reaches the LLM, no prompt engineering can
save the answer. Improving these numbers is the whole point of the five levers.

Run the default (current env) config:
    python -m assar.rag.eval
Compare the levers head-to-head (dense -> +bm25 -> +rerank):
    python -m assar.rag.eval --compare
"""
from __future__ import annotations

import sys

from .retriever import Retriever

# Gold set: question -> marker present in the answer-bearing chunk.
GOLD: list[dict] = [
    {"q": "What is the Condition of Average in fire insurance?",
     "marker": "condition of average"},
    {"q": "How are large risks and reinsurance treaties handled?",
     "marker": "reinsurance treaty"},
    {"q": "Explain the co-insurance arrangement.",
     "marker": "co-insurance arrangement"},
    {"q": "What is the mandatory time excess for business interruption following fire?",
     "marker": "time excess is 14 days"},
    {"q": "What rate applies to high value goods like precious metals under burglary?",
     "marker": "high valued goods"},
    {"q": "What loading applies for transport outside Rwanda?",
     "marker": "transport outside rwanda"},
    {"q": "How are goods-in-transit rates derived from marine cargo ICC rates?",
     "marker": "discounted by 10% to git"},
    {"q": "What is the minimum policy fee?",
     "marker": "policy fees"},
    {"q": "How is PVT insurance priced?",
     "marker": "pricing of pvt risks"},
    {"q": "What is the scale of rates for short period insurance?",
     "marker": "scale of rates for short period"},
    {"q": "How is consequential loss insurance priced?",
     "marker": "pricing of consequential loss"},
    {"q": "What does fidelity guarantee insurance cover?",
     "marker": "fidelity guarantee"},
]


def _first_hit_rank(results: list[dict], marker: str) -> int | None:
    """1-based rank of the first chunk containing the marker, or None."""
    m = marker.lower()
    for i, r in enumerate(results, start=1):
        if m in r["text"].lower():
            return i
    return None


def evaluate(retriever: Retriever, k: int = 5, verbose: bool = False) -> dict:
    hits, rr = 0, 0.0
    rows = []
    for item in GOLD:
        res = retriever.search(item["q"], k=k)
        rank = _first_hit_rank(res, item["marker"])
        if rank is not None:
            hits += 1
            rr += 1.0 / rank
        rows.append((item["q"], rank))
        if verbose:
            tag = f"rank {rank}" if rank else "MISS"
            print(f"  [{tag:>7}] {item['q']}")
    n = len(GOLD)
    return {"recall": hits / n, "mrr": rr / n, "n": n, "rows": rows}


def _config(**kw) -> Retriever:
    """A retriever with expansion forced off (keeps eval offline/free unless asked)."""
    kw.setdefault("expansion", False)
    return Retriever(**kw)


def compare(k: int = 5):
    configs = [
        ("dense only", _config(hybrid=False, rerank=False)),
        ("+ bm25 (hybrid)", _config(hybrid=True, rerank=False)),
        ("+ rerank", _config(hybrid=True, rerank=True)),
    ]
    print(f"\nRetrieval eval over {len(GOLD)} questions  (k={k})\n")
    print(f"{'config':<22}{'Recall@k':>10}{'MRR@k':>10}   pipeline")
    print("-" * 78)
    for name, r in configs:
        m = evaluate(r, k=k)
        print(f"{name:<22}{m['recall']:>10.2f}{m['mrr']:>10.3f}   {r.describe()}")
    print()


def main():
    if "--compare" in sys.argv:
        compare()
        return
    r = Retriever()
    print(f"Config: {r.describe()}")
    m = evaluate(r, k=5, verbose=True)
    print(f"\nRecall@5 = {m['recall']:.2f}   MRR@5 = {m['mrr']:.3f}   (n={m['n']})")


if __name__ == "__main__":
    main()
