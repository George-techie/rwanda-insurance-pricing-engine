"""General table / comparison engine over assar_info.db.

The manual's 45 rate and reference tables are stored verbatim in assar_info.db,
described by a data_dictionary (column units + descriptions). This module turns a
natural-language request ("compare the goods-in-transit options", "fire rates for
the different risks") into the right table and renders it as a markdown table.

Design choices that matter:
- It is DETERMINISTIC: the numbers come straight from SQL, never the LLM, so a
  rendered table cannot be fabricated.
- It is GENERAL: every cover in the manual is reachable with no per-scheme
  hard-coding. New tables in assar_info.db are picked up automatically.
- Matching reuses the SAME bge embeddings as document retrieval, so "petrol
  moving to Kenya" maps to `goods_in_transit` semantically, and it can read the
  conversation (the caller passes recent turns as context).
"""
from __future__ import annotations

import functools
import re
import sqlite3
from pathlib import Path

INFO_DB = Path(__file__).resolve().parents[1] / "data" / "assar_info.db"
EXCLUDE = {"data_dictionary"}
MATCH_MIN = 0.30  # below this we ask the user to name the cover instead of guessing

# Tokens that should stay upper-case when we humanise names.
_ACRONYMS = {"pvt", "gpa", "pa", "cpm", "eear", "ear", "car", "bbb", "icc", "icca",
             "do", "tpd", "git", "si", "rwf"}

# Generic words that carry no table-discriminating signal in lexical matching.
_STOP = {"all", "and", "the", "of", "for", "pct", "rate", "rates", "table",
         "insurance", "premium", "premiums", "cover", "such", "other", "per",
         "with", "from", "value", "values", "type", "classification", "description"}


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(INFO_DB))
    c.row_factory = sqlite3.Row
    return c


def _humanise(name: str) -> str:
    name = re.sub(r"_(pct|rwf|months?|weeks?|days?)$", "", name)
    words = name.replace("_", " ").split()
    out = []
    for w in words:
        out.append(w.upper() if w.lower() in _ACRONYMS else w.capitalize())
    return " ".join(out)


def _clean_unit(unit: str | None) -> str:
    """Normalise the data_dictionary unit to a short tag, dropping PUA junk."""
    if not unit:
        return ""
    u = "".join(ch for ch in unit if not (0xF000 <= ord(ch) <= 0xF0FF)).strip()
    low = u.lower()
    if "%" in u or "percent" in low:
        return "%"
    if "mille" in low:
        return "per mille"
    if "rwf" in low or "franc" in low:
        return "RWF"
    if any(w in low for w in ("month", "week", "day", "ratio", "multiplier", "factor")):
        return u
    return ""


@functools.lru_cache(maxsize=1)
def _dictionary() -> dict[str, list[tuple[str, str, str]]]:
    """{table_name: [(column, unit_tag, description)]} from data_dictionary."""
    out: dict[str, list[tuple[str, str, str]]] = {}
    with _conn() as c:
        for r in c.execute("SELECT table_name, column_name, unit, description FROM data_dictionary"):
            out.setdefault(r["table_name"], []).append(
                (r["column_name"], _clean_unit(r["unit"]), r["description"] or "")
            )
    return out


@functools.lru_cache(maxsize=1)
def list_tables() -> list[str]:
    with _conn() as c:
        names = [r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    return [n for n in names if n not in EXCLUDE]


def table_title(table: str) -> str:
    return _humanise(table)


def _columns(table: str) -> list[str]:
    with _conn() as c:
        return [r[1] for r in c.execute(f"PRAGMA table_info('{table}')")]


def _rows(table: str) -> list[sqlite3.Row]:
    with _conn() as c:
        return list(c.execute(f"SELECT * FROM '{table}'"))


def _descriptor(table: str) -> str:
    """A short text profile of a table for semantic matching: its title, column
    meanings, and a sample of the row labels (occupancies / commodities / etc.)."""
    title = table_title(table)
    cols = _dictionary().get(table, [])
    col_text = "; ".join(f"{_humanise(c)} {d}".strip() for c, _u, d in cols)
    label_col = None
    for c, unit, _d in cols:
        if not unit:  # first text column = the descriptive label
            label_col = c
            break
    samples = ""
    if label_col:
        try:
            with _conn() as cx:
                vals = [str(r[0]) for r in cx.execute(
                    f"SELECT DISTINCT \"{label_col}\" FROM '{table}' LIMIT 15")]
            samples = " ; ".join(vals)
        except sqlite3.Error:
            samples = ""
    return f"{title}. {col_text}. Examples: {samples}"


@functools.lru_cache(maxsize=1)
def _descriptors() -> dict[str, str]:
    return {t: _descriptor(t) for t in list_tables()}


def _toks(text: str) -> set[str]:
    out = set()
    for t in re.split(r"[^a-z0-9]+", text.lower()):
        t = re.sub(r"(pct|rwf)$", "", t)
        if len(t) > 2 and t not in _STOP:
            out.add(t)
    return out


@functools.lru_cache(maxsize=1)
def _table_tokens() -> dict[str, set[str]]:
    """Discriminating lexical tokens per table: from its name + column names."""
    out: dict[str, set[str]] = {}
    for t in list_tables():
        toks = _toks(t)
        for c, _u, _d in _dictionary().get(t, []):
            toks |= _toks(c)
        out[t] = toks
    return out


class _Catalog:
    def __init__(self):
        self._emb: dict[str, list[float]] | None = None

    def _ensure(self):
        if self._emb is not None:
            return
        from .rag.retriever import get_retriever

        desc = _descriptors()
        names = list(desc)
        vecs = get_retriever().encode([desc[n] for n in names])
        self._emb = dict(zip(names, vecs))

    def match(self, query: str) -> tuple[str | None, float]:
        """Best-matching table = semantic cosine + a lexical bonus for how many of
        the table's title/column tokens appear in the query. The lexical term is
        what makes 'transit ... road accident ... containerized' land squarely on
        goods_in_transit rather than a semantically-nearby table."""
        self._ensure()
        from .rag.retriever import get_retriever

        qv = get_retriever().encode([query])[0]
        qtok = _toks(query)
        toks = _table_tokens()
        best, best_score = None, -1.0
        for name, vec in self._emb.items():
            cos = sum(a * b for a, b in zip(qv, vec))
            overlap = len(toks[name] & qtok)
            score = cos + 0.05 * min(overlap, 6)
            if score > best_score:
                best, best_score = name, score
        return (best, best_score) if best_score >= MATCH_MIN else (None, best_score)


_CATALOG = _Catalog()


def match_table(query: str) -> str | None:
    return _CATALOG.match(query)[0]


def _fmt(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        f = float(value)
        if f == int(f) and abs(f) >= 1000:
            return f"{int(f):,}"
        return f"{round(f, 6):g}"
    return str(value)


def render_markdown(table: str, max_rows: int | None = None) -> str | None:
    """Render an info-engine table as a markdown table with unit-aware headers."""
    if table not in list_tables():
        return None
    cols = _columns(table)
    units = {c: u for c, u, _d in _dictionary().get(table, [])}
    rows = _rows(table)
    if not rows:
        return None

    # Drop a pure 'code' index column from the display; keep everything else.
    show = [c for c in cols if c != "code"]
    headers = []
    for c in show:
        u = units.get(c, "")
        headers.append(f"{_humanise(c)} ({u})" if u else _humanise(c))

    title = table_title(table)
    n = len(rows)
    out = [f"**{title}: rate table**  \n_{n} row(s), read directly from the manual "
           f"schedule (assar_info.db). Rates are of the sum insured unless noted._", ""]
    out.append("| " + " | ".join(headers) + " |")
    out.append("|" + "|".join("---" for _ in show) + "|")
    shown = rows if max_rows is None else rows[:max_rows]
    for r in shown:
        out.append("| " + " | ".join(_fmt(r[c]) for c in show) + " |")
    if max_rows is not None and n > max_rows:
        out.append(f"\n_Showing {max_rows} of {n} rows; ask for a specific item to narrow it._")
    out += ["", "Tell me the specific item and the sum insured (or consignment value) "
            "and I'll compute the exact premium."]
    return "\n".join(out)


def answer_table(query: str) -> str | None:
    """One-shot: match the query to a table and render it, or None if no good match."""
    table = match_table(query)
    return render_markdown(table) if table else None


def catalog_titles(limit: int = 12) -> list[str]:
    return [table_title(t) for t in list_tables()[:limit]]
