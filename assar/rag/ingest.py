"""Chunk the prose corpus and build the ChromaDB vector store.

Embeddings are computed locally with sentence-transformers (no API needed).
Default model is bge-base-en-v1.5 (768-d, stronger than -small at ~3x size,
still CPU-friendly). Override with EMBED_MODEL:
  - BAAI/bge-small-en-v1.5   384-d, fastest, lowest quality (the old default)
  - BAAI/bge-base-en-v1.5    768-d, the new default (better recall)
  - BAAI/bge-large-en-v1.5   1024-d, best English quality, heavier
  - BAAI/bge-m3              multilingual (Kinyarwanda/French), hybrid-capable

Tune chunking with CHUNK_TARGET (chars) and CHUNK_OVERLAP (chars).

IMPORTANT: changing the embedding model changes the vector dimension, so you
MUST re-ingest (this script DROPs and recreates the collection):
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
EMBED_MODEL = os.getenv("EMBED_MODEL", "BAAI/bge-base-en-v1.5")
CHUNK_TARGET = int(os.getenv("CHUNK_TARGET", "1600"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))


def _upper_ratio(s: str) -> float:
    letters = [c for c in s if c.isalpha()]
    return sum(c.isupper() for c in letters) / len(letters) if letters else 0.0


def _is_heading(s: str, *, max_words: int = 9, max_len: int = 60) -> bool:
    """A section title line: short, (almost) all-caps, no digits.

    Matches the manual's headers ('PRICING OF CONSEQUENTIAL LOSS', 'NOTA BENA',
    'FULL VALUE BASIS', 'ERECTION ALL RISKS (EAR)') without catching prose.
    """
    s = s.strip()
    if len(s) > max_len or any(ch.isdigit() for ch in s):
        return False
    words = s.split()
    if not (2 <= len(words) <= max_words):
        return False
    return _upper_ratio(s) >= 0.8 and len([c for c in s if c.isalpha()]) >= 3


def _clean(s: str) -> str:
    """Strip PDF private-use bullet glyphs (e.g. U+F0D8) that survive extraction."""
    return "".join(c for c in s if not (0xf000 <= ord(c) <= 0xf0ff))


# Front-matter sections (cover/table-of-contents) that add noise, not pricing prose.
_NOISE_TITLE = ("S/NO", "DESCRIPTION OF ITEM", "TABLE OF CONTENT")


def _pageful_lines(text: str) -> list[tuple[int, str]]:
    """[(page, line)] for all body lines, dropping the pre-page-1 preamble."""
    out, page = [], 0
    for ln in text.splitlines():
        m = re.match(r"##\s+Page\s+(\d+)\s*$", ln.strip())
        if m:
            page = int(m.group(1))
            continue
        if page >= 1:
            out.append((page, _clean(ln)))
    return out


def _sections(text: str) -> list[dict]:
    """Group lines into {title, lines:[(page,line)]} by heading runs.

    A heading may wrap to a second all-caps line (e.g. 'PRICING OF CONTRACTORS
    PLANT AND' + 'MACHINERY (CPM) INSURANCE'); we fold one continuation line in.
    """
    lines = _pageful_lines(text)
    sections: list[dict] = []
    cur = {"title": "General", "lines": []}
    i, n = 0, len(lines)
    while i < n:
        page, ln = lines[i]
        if _is_heading(ln):
            if cur["lines"]:
                sections.append(cur)
            title = ln.strip()
            i += 1
            # fold a single all-caps continuation line into the title
            if i < n and _is_heading(lines[i][1], max_words=6, max_len=50):
                title += " " + lines[i][1].strip()
                i += 1
            cur = {"title": title, "lines": []}
            continue
        cur["lines"].append((page, ln))
        i += 1
    if cur["lines"]:
        sections.append(cur)
    return sections


def _split_section(title: str, lines: list[tuple[int, str]],
                   target_chars: int, overlap: int) -> list[dict]:
    """Sub-split one section into title-prefixed chunks with page anchors."""
    offsets, parts, pos = [], [], 0
    for page, ln in lines:
        piece = (ln.rstrip() + "\n") if ln.strip() else "\n"
        offsets.append((pos, page))
        parts.append(piece)
        pos += len(piece)
    body = "".join(parts).strip()
    if len(body) < 20:
        return []

    def page_at(off: int) -> int:
        p = lines[0][0]
        for o, pg in offsets:
            if o <= off:
                p = pg
            else:
                break
        return p

    out: list[dict] = []
    if len(body) <= target_chars:
        return [{"text": f"{title}\n{body}", "page": page_at(0), "section": title}]
    start, n = 0, len(body)
    while start < n:
        end = min(start + target_chars, n)
        piece = body[start:end]
        if end < n:
            cut = max(piece.rfind(". "), piece.rfind("\n"))
            if cut > target_chars * 0.5:
                end = start + cut + 1
                piece = body[start:end]
        ptxt = piece.strip()
        if len(ptxt) >= 20:
            out.append({"text": f"{title}\n{ptxt}", "page": page_at(start), "section": title})
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return out


def chunk_corpus(text: str, target_chars: int = CHUNK_TARGET, overlap: int = CHUNK_OVERLAP) -> list[dict]:
    """Structure-aware chunking: split by the manual's section headings, keep
    each section's body together (even across page breaks), sub-split long
    sections on sentence boundaries, and prefix every chunk with its section
    title. Each chunk carries its page anchor (for citations) and section name.
    """
    chunks: list[dict] = []
    for sec in _sections(text):
        if any(marker in sec["title"].upper() for marker in _NOISE_TITLE):
            continue  # skip cover / table-of-contents front matter
        chunks.extend(_split_section(sec["title"], sec["lines"], target_chars, overlap))
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
    print(f"Chunked corpus into {len(chunks)} pieces "
          f"(target={CHUNK_TARGET}, overlap={CHUNK_OVERLAP}); "
          f"embedding with {EMBED_MODEL} ...")

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
        metadatas=[{"page": c["page"], "section": c.get("section", "")} for c in chunks],
        embeddings=embeddings,
    )
    print(f"Ingested {len(chunks)} chunks into '{COLLECTION}' at {persist_dir}")
    return len(chunks)


if __name__ == "__main__":
    ingest()
