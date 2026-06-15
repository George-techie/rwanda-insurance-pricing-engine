"""Minimal multi-agent demo over the ASSAR information engine.

A small, runnable slice of the planned multi-agent system. It shows the roles
working together and PRINTS each step so you can watch the routing:

    Manager   -> classifies the question: NUMBER (query the DB) or CONCEPT (RAG)
    Quant     -> NUMBER: turns the question into a read-only SQL SELECT and runs it
    Retriever -> CONCEPT: semantic search over the manual prose (ChromaDB)
    Verifier  -> annotates units from the data_dictionary, confirms read-only,
                 flags the per-mille trap, and (with an LLM) writes the answer

Runs with NO API key (heuristic manager + keyword search). If an LLM backend is
configured (GROQ_API_KEY etc.), the Manager/Quant/answer steps use it instead.

    python demo_agent.py                     # interactive REPL
    python demo_agent.py "fire rate for a bank?"
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

INFO_DB = Path(__file__).resolve().parent / "data" / "assar_info.db"

_WRITE = re.compile(r"\b(insert|update|delete|drop|alter|create|replace|attach|"
                    r"detach|pragma|vacuum|reindex)\b", re.I)
_STOP = {"the", "for", "what", "whats", "is", "a", "an", "of", "to", "in", "on",
         "rate", "rates", "cost", "price", "how", "much", "and", "or", "are",
         "value", "premium", "me", "give", "show", "tell"}


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #
def ro_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{INFO_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def schema_brief(conn) -> str:
    """Compact schema (table -> columns with units) from the data_dictionary."""
    rows = conn.execute(
        "SELECT table_name, column_name, unit FROM data_dictionary "
        "ORDER BY table_name, rowid").fetchall()
    by_table: dict[str, list[str]] = {}
    for r in rows:
        u = "" if r["unit"] in ("—", "") else f" [{r['unit']}]"
        by_table.setdefault(r["table_name"], []).append(r["column_name"] + u)
    return "\n".join(f"{t}({', '.join(cols)})" for t, cols in by_table.items())


def text_columns(conn, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})") if r[2] == "TEXT"]


def all_tables(conn) -> list[str]:
    return [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT IN ('data_dictionary') ORDER BY name")]


# --------------------------------------------------------------------------- #
# Agents
# --------------------------------------------------------------------------- #
def manager(question: str, llm) -> str:
    """Classify the question -> 'number' or 'concept'."""
    if llm and llm.ready:
        msg = llm.chat([
            {"role": "system", "content":
             "Classify the user's insurance question. Reply with ONLY one word: "
             "NUMBER if it asks for a rate/premium/amount/figure that lives in a "
             "table, or CONCEPT if it asks what something means / is excluded / "
             "covered / how a cover works."},
            {"role": "user", "content": question},
        ], temperature=0)
        route = "concept" if "CONCEPT" in (msg.content or "").upper() else "number"
        print(f"  [manager] (llm) -> {route.upper()}")
        return route
    # Heuristic fallback: number cues win over concept cues.
    q = question.lower()
    number_cues = ("rate", "premium", "cost", "price", "how much", "value", "rwf",
                   "%", "amount", "fee", "deductible", "excess", "multiplier",
                   "discount", "rates")
    concept_cues = ("explain", "exclud", "cover", "mean", "warrant", "definition",
                    "condition", "clause", "difference", "what does", "why")
    if any(c in q for c in number_cues):
        route = "number"
    elif any(c in q for c in concept_cues):
        route = "concept"
    else:
        route = "number"
    print(f"  [manager] (heuristic) -> {route.upper()}")
    return route


def _safe_select(sql: str) -> str | None:
    sql = sql.strip().rstrip(";").strip()
    if not re.match(r"(?is)^\s*select\b", sql):
        return None
    if _WRITE.search(sql) or ";" in sql:
        return None
    return sql


def quant(question: str, conn, llm) -> tuple[str, list[sqlite3.Row]]:
    """NUMBER path: produce a read-only SELECT and execute it."""
    if llm and llm.ready:
        sql_msg = llm.chat([
            {"role": "system", "content":
             "You write ONE read-only SQLite SELECT against this schema. Output "
             "ONLY the SQL, no prose, no code fence. Use LIKE '%...%' for text "
             "matches. Keep it to a single statement.\n\nSCHEMA:\n"
             + schema_brief(conn)},
            {"role": "user", "content": question},
        ], temperature=0)
        sql = _safe_select(re.sub(r"```\w*|```", "", sql_msg.content or "").strip())
        if sql:
            print(f"  [quant]   (llm sql) {sql}")
            try:
                return sql, conn.execute(sql).fetchall()[:10]
            except sqlite3.Error as e:
                print(f"  [quant]   sql error: {e} -> falling back to keyword search")
    # Heuristic keyword search across text columns of every table
    kws = [w for w in re.findall(r"[a-zA-Z]{3,}", question.lower()) if w not in _STOP]
    best_table, best_rows, best_score = "", [], 0
    for t in all_tables(conn):
        cols = text_columns(conn, t)
        if not cols or not kws:
            continue
        where = " OR ".join(f"{c} LIKE ?" for kw in kws for c in cols)
        params = [f"%{kw}%" for kw in kws for c in cols]
        try:
            rows = conn.execute(f"SELECT * FROM {t} WHERE {where} LIMIT 10", params).fetchall()
        except sqlite3.Error:
            rows = []
        # Boost tables whose NAME matches a keyword (e.g. 'pvt' -> pvt_* table),
        # weighting earlier keywords more ('fire rate for a bank' -> fire table,
        # not bankers_blanket_bond).
        name_bonus = sum((len(kws) - i) * 10 for i, kw in enumerate(kws)
                         if kw in t.lower())
        score = len(rows) + name_bonus
        if rows and score > best_score:
            best_table, best_rows, best_score = t, rows, score
    sql = f"SELECT * FROM {best_table} WHERE <label> LIKE keywords" if best_table else "(no match)"
    print(f"  [quant]   (keyword search) table={best_table or 'none'} kws={kws}")
    return sql, best_rows


def verifier(conn, sql: str, rows: list[sqlite3.Row]) -> dict:
    """Attach units, confirm read-only, flag the per-mille trap."""
    notes = {"read_only": True, "units": {}, "warnings": []}
    m = re.search(r"(?is)\bfrom\s+([a-z_][a-z0-9_]*)", sql or "")
    table = m.group(1) if m else None
    cols = rows[0].keys() if rows else []
    if table:
        for c in cols:
            u = conn.execute(
                "SELECT unit FROM data_dictionary WHERE table_name=? AND column_name=?",
                (table, c)).fetchone()
            if u and u[0] not in ("—", ""):
                notes["units"][c] = u[0]
                if "mille" in u[0]:
                    notes["warnings"].append(
                        f"{c} is PER MILLE (per 1,000), not percent — do not read as %.")
    print(f"  [verifier] read-only=yes  units={ {k: v for k, v in notes['units'].items()} }")
    for w in notes["warnings"]:
        print(f"  [verifier] !! {w}")
    return notes


def retriever_path(question: str):
    from assar.rag.retriever import get_retriever
    r = get_retriever()
    if not r.available:
        print("  [retriever] vector store not built (run: python -m assar.ingest)")
        return []
    hits = r.search(question, k=3)
    for h in hits:
        print(f"  [retriever] p{h['page']} score={h['score']:.2f}")
    return hits


def synthesize(question, route, sql, rows, notes, chunks, llm) -> str:
    if route == "number":
        body = "\n".join("  " + json.dumps({k: r[k] for k in r.keys()}, default=str)
                         for r in rows) or "  (no matching rows)"
        unit_line = "; ".join(f"{k}={v}" for k, v in (notes or {}).get("units", {}).items())
        context = f"SQL: {sql}\nRows:\n{body}\nUnits: {unit_line}"
    else:
        context = "\n\n".join(f"[p.{c['page']}] {c['text']}" for c in chunks) or "(no prose)"
    if llm and llm.ready:
        msg = llm.chat([
            {"role": "system", "content":
             "Answer the insurance question from the provided data ONLY. Show the "
             "exact figure(s) WITH their unit. Cite the manual page for prose. Note "
             "per-mille rates are not percent. Be concise. End by reminding the user "
             "to verify against the source manual before binding cover."},
            {"role": "user", "content": f"Question: {question}\n\nData:\n{context}"},
        ])
        return msg.content or ""
    # No-LLM rendering
    return f"(no LLM - raw result)\n{context}"


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def answer(question: str):
    print(f"\nyou> {question}")
    try:
        from assar.llm.client import get_client
        llm = get_client()
    except Exception:
        llm = None
    if llm and not llm.ready:
        print("  [note] no LLM key set -> running heuristic mode "
              "(set GROQ_API_KEY in .env for the smart path)")

    conn = ro_connect()
    route = manager(question, llm)
    sql, rows, notes, chunks = "", [], {}, []
    if route == "number":
        sql, rows = quant(question, conn, llm)
        notes = verifier(conn, sql, rows)
    else:
        chunks = retriever_path(question)
    out = synthesize(question, route, sql, rows, notes, chunks, llm)
    conn.close()
    print("\n" + "-" * 70 + "\n" + out + "\n" + "-" * 70)


def main():
    if not INFO_DB.exists():
        sys.exit(f"Missing {INFO_DB} — run: python -m assar.build_info_tables")
    if len(sys.argv) > 1:
        answer(" ".join(sys.argv[1:]))
        return
    print("ASSAR multi-agent demo. Type a question (blank to quit).")
    while True:
        try:
            q = input("\nask> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            break
        answer(q)


if __name__ == "__main__":
    main()
