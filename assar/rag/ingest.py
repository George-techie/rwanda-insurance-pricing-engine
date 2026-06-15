"""Chunk the prose corpus and build the ChromaDB vector store.

Embeddings are computed locally with sentence-transformers (no API needed).
Default model is bge-small-en-v1.5 (fast, CPU-friendly). For Kinyarwanda/French
content switch EMBED_MODEL to BAAI/bge-m3 (multilingual, hybrid dense+sparse).

Run once on your machine (downloads the embedding model on first use):
    python -m assar.ingest
"""
from __future__ import annotations

import os
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
CORPUS_PATH = DATA_DIR / "corpus.md"
CHROMA_DIR = DATA_DIR / "chroma"
COLLECTION = "assar_manual"
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-small-en-v1.5")


def chunk_corpus(text: str, target_chars: int = 1100, overlap: int = 150) -> list[dict]:
    """Split the corpus into overlapping chunks, tagged with their page anchor."""
    # Split on the "## Page N" markers the corpus builder inserted.
    sections = re.split(r"\n##\s+Page\s+(\d+)\s*\n", text)
    chunks: list[dict] = []
    # sections = [preamble, pageno, body, pageno, body, ...]
    it = iter(sections[1:])
    for page_no, body in zip(it, it):
        body = body.strip()
        if len(body) < 40:
            continue
        # Short page -> a single chunk (avoids the degenerate tiny-advance loop).
        if len(body) <= target_chars:
            chunks.append({"text": body, "page": int(page_no)})
            continue
        n = len(body)
        start = 0
        while start < n:
            end = min(start + target_chars, n)
            piece = body[start:end]
            # Prefer to end on a sentence/newline boundary unless we're at the end.
            if end < n:
                cut = max(piece.rfind(". "), piece.rfind("\n"))
                if cut > target_chars * 0.5:
                    end = start + cut + 1
                    piece = body[start:end]
            piece = piece.strip()
            if len(piece) > 40:
                chunks.append({"text": piece, "page": int(page_no)})
            if end >= n:
                break
            # Advance in BODY coordinates (not len(piece), which strip() distorts),
            # guaranteeing forward progress of ~ (target_chars - overlap).
            start = max(end - overlap, start + 1)
    return chunks


def ingest(corpus_path: Path = CORPUS_PATH, persist_dir: Path = CHROMA_DIR) -> int:
    import chromadb
    from sentence_transformers import SentenceTransformer

    if not corpus_path.exists():
        raise FileNotFoundError(
            f"{corpus_path} missing — run `python -m assar.rag.build_corpus` first."
        )

    text = corpus_path.read_text(encoding="utf-8")
    chunks = chunk_corpus(text)
    print(f"Chunked corpus into {len(chunks)} pieces; embedding with {EMBED_MODEL} ...")

    model = SentenceTransformer(EMBED_MODEL)
    embeddings = model.encode(
        [c["text"] for c in chunks], normalize_embeddings=True, show_progress_bar=True
    ).tolist()

    persist_dir.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(persist_dir))
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    coll = client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
    coll.add(
        ids=[f"chunk-{i}" for i in range(len(chunks))],
        documents=[c["text"] for c in chunks],
        metadatas=[{"page": c["page"]} for c in chunks],
        embeddings=embeddings,
    )
    print(f"Ingested {len(chunks)} chunks into '{COLLECTION}' at {persist_dir}")
    return len(chunks)


if __name__ == "__main__":
    ingest()
