"""Build the prose corpus for the vector store from the source PDF.

The numeric rate tables already live in SQLite, so the vector store only needs
the *prose* — definitions, conditions, warranties, exclusions and underwriting
guidance. We extract page text and keep page numbers as anchors so retrieved
chunks can be cited back to the manual.

Run:  python -m assar.rag.build_corpus
"""
from __future__ import annotations

from pathlib import Path

PDF_PATH = Path("/mnt/user-data/uploads/ASSAR_s_Version_3.pdf")
CORPUS_PATH = Path(__file__).resolve().parents[2] / "data" / "corpus.md"

# Lines that are almost certainly pure rate-table rows add noise to semantic
# search (the numbers are authoritative in SQL). We keep a line unless it is
# dominated by numbers / rate punctuation.
import re

_NUMERIC_LINE = re.compile(r"^[\s\d.,%/()\-]+$")

# Repeated page header/footer boilerplate to drop (appears on most pages).
_BOILERPLATE = [
    re.compile(r"^P\s*age\s*\d+\s*\|\s*\d+$", re.I),
    re.compile(r"^RWANDAN INSURANCE MARKET PRICING MANUAL$", re.I),
    re.compile(r"^VERSION\s*3$", re.I),
    re.compile(r"^ISSUE DATE:.*$", re.I),
]


def _is_boilerplate(line: str) -> bool:
    s = line.strip()
    return any(p.match(s) for p in _BOILERPLATE)


def _looks_like_table_row(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if _NUMERIC_LINE.match(s):
        return True
    # mostly numeric tokens?
    tokens = s.split()
    if len(tokens) >= 4:
        numeric = sum(1 for t in tokens if re.fullmatch(r"[\d.,%/()\-]+", t))
        if numeric / len(tokens) > 0.6:
            return True
    return False


def build_corpus(pdf_path: Path = PDF_PATH, out_path: Path = CORPUS_PATH) -> Path:
    import pdfplumber

    out_path.parent.mkdir(parents=True, exist_ok=True)
    parts: list[str] = [
        "# ASSAR General Business Pricing Manual (Version 3) — Prose Corpus\n",
        "_Auto-extracted prose for semantic retrieval. Numeric rate tables are "
        "served from SQLite, not from here._\n",
    ]
    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            raw = page.extract_text() or ""
            kept = [
                ln for ln in raw.splitlines()
                if not _looks_like_table_row(ln) and not _is_boilerplate(ln)
            ]
            text = "\n".join(kept).strip()
            if len(text) < 40:           # skip near-empty / pure-table pages
                continue
            parts.append(f"\n\n## Page {i}\n\n{text}")
    out_path.write_text("\n".join(parts), encoding="utf-8")
    return out_path


if __name__ == "__main__":
    p = build_corpus()
    n = len(p.read_text(encoding="utf-8"))
    print(f"Wrote {p}  ({n:,} chars)")
