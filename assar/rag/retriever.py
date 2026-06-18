"""Retrieve relevant prose chunks from the ChromaDB vector store."""
from __future__ import annotations

import functools
import os
from pathlib import Path

from .ingest import CHROMA_DIR, COLLECTION, EMBED_MODEL

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


class Retriever:
    """Lazy-loaded retriever. Construction is cheap; the model and DB load on first query."""

    def __init__(self, persist_dir: Path = CHROMA_DIR, model_name: str = EMBED_MODEL):
        self.persist_dir = persist_dir
        self.model_name = model_name
        self._model = None
        self._coll = None

    @property
    def available(self) -> bool:
        return (self.persist_dir / "chroma.sqlite3").exists() or any(
            self.persist_dir.glob("*")
        ) if self.persist_dir.exists() else False

    def _ensure(self):
        if self._coll is None:
            import chromadb
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
            client = chromadb.PersistentClient(path=str(self.persist_dir))
            self._coll = client.get_collection(COLLECTION)

    def search(self, query: str, k: int = 4) -> list[dict]:
        """Return [{text, page, score}] for the top-k chunks."""
        self._ensure()
        emb = self._model.encode([query], normalize_embeddings=True).tolist()
        res = self._coll.query(query_embeddings=emb, n_results=k)
        out = []
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        for doc, meta, dist in zip(docs, metas, dists):
            out.append({"text": doc, "page": meta.get("page"),
                        "section": meta.get("section", ""), "score": 1 - dist})
        return out


@functools.lru_cache(maxsize=1)
def get_retriever() -> Retriever:
    return Retriever()
