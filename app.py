"""ASSAR pricing assistant — Streamlit UI.

Run (after building the DB and vector store):
    streamlit run app.py

Two modes:
  • Ask        — free-text question/quote routed through the LLM, with a
                 transparency panel (retrieved manual pages + exact rates used).
  • Get a Quote — structured, deterministic pricing. No LLM required; always works.
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from assar.pricing.base import list_categories
from assar.pricing import fire as fire_mod
from assar.pricing import products as prod_mod
from assar.pricing import transit as transit_mod
from assar.db import connect, DB_PATH

st.set_page_config(page_title="ASSAR Pricing Assistant", page_icon="📑", layout="wide")


@st.cache_resource(show_spinner="Warming up the language model (first load, ~20s)…")
def _warm_models():
    """Load the local embedding model once at startup so the first chat message
    isn't a silent wait. Cached for the life of the server process."""
    try:
        from assar.rag.retriever import get_retriever
        r = get_retriever()
        if r.available:
            r.search("warm up", k=1)
        return True
    except Exception:
        return False


_warm_models()


# --------------------------------------------------------------------------- #
# Sidebar — status
# --------------------------------------------------------------------------- #
def db_stats():
    try:
        conn = connect()
        n = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
             for t in ("rate", "transit_rate", "schedule", "product_rule")}
        conn.close()
        return n
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


with st.sidebar:
    st.header("Status")
    stats = db_stats()
    if "error" in stats:
        st.error("Database not built. Run `python -m assar.build_db`.")
    else:
        st.success(f"Rate DB loaded · {stats['rate']} rates")
        st.caption(f"transit {stats['transit_rate']} · schedules {stats['schedule']} "
                   f"· rules {stats['product_rule']}")

    try:
        import sqlite3 as _sq
        _ic = _sq.connect(f"file:{DB_PATH.parent / 'assar_info.db'}?mode=ro", uri=True)
        _n = _ic.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
        _ic.close()
        st.success(f"Info engine · {_n} tables")
    except Exception:
        st.caption("Info engine: run `python -m assar.build_info_tables`")

    backend = os.getenv("LLM_BACKEND", "groq")
    st.write(f"**LLM backend:** `{backend}`")
    key_present = bool(os.getenv("GROQ_API_KEY") or os.getenv("HF_TOKEN") or backend == "ollama")
    st.write("LLM key:", "✅ set" if key_present else "⚠️ missing")

    try:
        from assar.rag.retriever import get_retriever
        vs_ok = get_retriever().available
    except Exception:
        vs_ok = False
    st.write("Vector store:", "✅ built" if vs_ok else "⚠️ run `python -m assar.ingest`")

    st.divider()
    st.caption("⚠️ Rates transcribed from the manual. **Verify against the source "
               "before binding cover.**")


_BANNER = Path(__file__).resolve().parent / "assets" / "banner.png"
if _BANNER.exists():
    st.image(str(_BANNER), use_container_width=True)
else:
    st.title("ASSAR Pricing Assistant")
st.caption("Pricing and guidance over the Rwandan Insurance Industry Pricing "
           "Manual (v3): SQL for the rate tables, semantic search for the prose.")

tab_ask, tab_quote, tab_db = st.tabs(["Chat", "Get a Quote", "Database"])


# Shared renderer for an assistant turn's quote cards + cited sources.
def render_details(tool_calls, retrieved):
    for tc in tool_calls or []:
        r = tc["result"]
        if "error" in r:
            continue  # don't surface failed/spurious tool calls; the text answer stands
        c = st.columns(3)
        c[0].metric("Product", r.get("product", "-"))
        c[1].metric("Rate", f"{r.get('rate')} {r.get('rate_unit', '%')}")
        c[2].metric("Final premium", f"Rwf{r.get('final_premium', 0):,.0f}")
        with st.expander("Breakdown"):
            for line in r.get("breakdown", []):
                st.text(line)
            if r.get("excess"):
                st.caption(f"Excess: {r['excess']}")
            for w in r.get("warnings", []):
                st.caption(f"Note: {w}")
    if retrieved:
        with st.expander(f"Sources: {len(retrieved)} manual passage(s)"):
            for c in retrieved:
                sec = f" · {c.get('section', '')}" if c.get("section") else ""
                st.markdown(f"**Page {c['page']}**{sec} · similarity {c['score']:.2f}")
                st.caption(c["text"][:400] + ("…" if len(c["text"]) > 400 else ""))


# --------------------------------------------------------------------------- #
# Ask tab — free text through the router
# --------------------------------------------------------------------------- #
with tab_ask:
    # What we cover — themed product tiles
    cover = [("🔥", "Fire & Perils"), ("🏢", "Property"), ("🚚", "Goods in Transit"),
             ("🚢", "Marine"), ("✈️", "Aviation"), ("⚖️", "Liability"),
             ("🏗️", "Engineering"), ("⚙️", "Machinery"), ("📜", "Bonds"),
             ("🚑", "Personal Accident"), ("🛡️", "PVT"), ("💻", "Computer/EEAR")]
    tile_cols = st.columns(6)
    for i, (emo, label) in enumerate(cover):
        with tile_cols[i % 6]:
            st.markdown(
                f"<div style='text-align:center;padding:8px 4px;border:1px solid #e6e6e6;"
                f"border-radius:10px;margin-bottom:8px;background:#fafcff'>"
                f"<div style='font-size:26px'>{emo}</div>"
                f"<div style='font-size:12px;color:#334'>{label}</div></div>",
                unsafe_allow_html=True,
            )
    st.caption("Ask about pricing or cover in plain language. It remembers the "
               "conversation, so follow-ups like \"and for a bank?\" work.")

    if "chat" not in st.session_state:
        st.session_state.chat = []

    # Replay the whole conversation (newest at the bottom).
    for m in st.session_state.chat:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])
            if m["role"] == "assistant":
                render_details(m.get("tool_calls", []), m.get("retrieved", []))

    # If the latest turn is a user message awaiting a reply, answer it here —
    # below the history and above the input box.
    if st.session_state.chat and st.session_state.chat[-1]["role"] == "user":
        from assar.llm.router import answer_query
        history = [(m["role"], m["content"]) for m in st.session_state.chat[:-1]
                   if m["role"] in ("user", "assistant")]
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                res = answer_query(st.session_state.chat[-1]["content"], history=history)
            st.markdown(res.answer or "_(no answer)_")
            render_details(res.tool_calls, res.retrieved)
        st.session_state.chat.append({
            "role": "assistant", "content": res.answer or "",
            "tool_calls": res.tool_calls, "retrieved": res.retrieved,
        })

    if st.session_state.chat and st.button("Clear conversation"):
        st.session_state.chat = []
        st.rerun()

    # Input stays pinned at the bottom; on submit, record the turn and rerun so
    # it appears in the history above, with the input still below.
    prompt = st.chat_input("Ask about insurance pricing…")
    if prompt:
        st.session_state.chat.append({"role": "user", "content": prompt})
        st.rerun()


# --------------------------------------------------------------------------- #
# Get a Quote tab — deterministic, no LLM
# --------------------------------------------------------------------------- #
def show_quote(q):
    cols = st.columns(3)
    cols[0].metric("Gross premium", f"Rwf{q.gross_premium:,.0f}")
    cols[1].metric("Net premium", f"Rwf{q.net_premium:,.0f}")
    cols[2].metric("FINAL premium", f"Rwf{q.final_premium:,.0f}")
    st.markdown("**Breakdown**")
    for line in q.lines:
        st.text(line)
    if q.excess:
        st.info(f"Excess / deductible: {q.excess}")
    for w in q.warnings:
        st.warning(w)


with tab_quote:
    product = st.selectbox(
        "Product",
        ["Fire & Allied Perils", "Public/Employers/Product/Professional Liability",
         "Goods in Transit", "Marine Cargo", "Personal / Group Personal Accident",
         "Bond / Guarantee", "PVT (Political Violence & Terrorism)",
         "Engineering CAR/EAR", "Machinery Breakdown", "Contractors Plant & Machinery",
         "Burglary & Theft"],
    )

    if product == "Fire & Allied Perils":
        cats = list_categories("fire")
        c = st.selectbox("Risk category", cats, index=cats.index("hotels") if "hotels" in cats else 0)
        si = st.number_input("Sum insured (Rwf)", min_value=0.0, value=100_000_000.0, step=1_000_000.0)
        col1, col2, col3 = st.columns(3)
        sp = col1.checkbox("All special perils", value=True)
        ind = col2.checkbox("Industrial", value=False)
        fea = col3.checkbox("FEA available", value=False)
        vexc = st.number_input("Voluntary excess (Rwf, 0 = none)", min_value=0.0, value=0.0, step=50_000.0)
        months = st.slider("Period (months)", 1, 12, 12)
        if st.button("Calculate", type="primary"):
            show_quote(fire_mod.quote_fire(c, si, special_perils=sp, industrial=ind,
                                           fea_available=fea, voluntary_excess=vexc,
                                           period_months=months))

    elif product == "Public/Employers/Product/Professional Liability":
        kind = st.selectbox("Type", ["public", "employers", "product", "professional"])
        scheme = {"public": "public_liability", "employers": "employers_liability",
                  "product": "product_liability", "professional": "professional_indemnity"}[kind]
        occ = st.selectbox("Occupation / class", list_categories(scheme))
        loi = st.number_input("Limit of indemnity (Rwf)", min_value=0.0, value=50_000_000.0, step=1_000_000.0)
        months = st.slider("Period (months)", 1, 12, 12)
        if st.button("Calculate", type="primary"):
            show_quote(prod_mod.quote_liability(kind, occ, loi, period_months=months))

    elif product == "Goods in Transit":
        conn = connect()
        commodities = [r["commodity"] for r in conn.execute(
            "SELECT DISTINCT commodity FROM transit_rate WHERE scheme='git' ORDER BY commodity")]
        conn.close()
        com = st.selectbox("Commodity", commodities)
        val = st.number_input("Consignment value (Rwf)", min_value=0.0, value=10_000_000.0, step=1_000_000.0)
        cover = st.selectbox("Cover", ["all_risks", "road_accident"])
        cont = st.checkbox("Containerized", value=True)
        tl = st.checkbox("Transporters Liability", value=False)
        out = st.checkbox("Transport outside Rwanda (+30%)", value=False)
        if st.button("Calculate", type="primary"):
            show_quote(transit_mod.quote_git(com, val, cover=cover, containerized=cont,
                                             transporters_liability=tl, outside_rwanda=out))

    elif product == "Marine Cargo":
        conn = connect()
        commodities = [r["commodity"] for r in conn.execute(
            "SELECT DISTINCT commodity FROM transit_rate WHERE scheme='marine_cargo' ORDER BY commodity")]
        conn.close()
        com = st.selectbox("Commodity", commodities)
        val = st.number_input("Consignment value (Rwf)", min_value=0.0, value=10_000_000.0, step=1_000_000.0)
        cont = st.checkbox("Containerized", value=True)
        mode = st.selectbox("Transit mode", ["combined", "road", "air", "sea"])
        clause = st.selectbox("Institute Cargo Clause", ["A", "B", "C"])
        if st.button("Calculate", type="primary"):
            show_quote(transit_mod.quote_marine_cargo(com, val, containerized=cont, mode=mode, clause=clause))

    elif product == "Personal / Group Personal Accident":
        rc = st.selectbox("Risk class", list_categories("pa_gpa"))
        db = st.number_input("Death benefit / capital sum (Rwf)", min_value=0.0, value=10_000_000.0, step=1_000_000.0)
        group = st.checkbox("Group (GPA)", value=False)
        student = st.checkbox("Student", value=False)
        benefits = st.multiselect("Benefits", ["death", "tpd", "ttd", "medical", "funeral"],
                                  default=["death", "tpd"])
        if st.button("Calculate", type="primary"):
            show_quote(prod_mod.quote_pa_gpa(rc, db, group=group, student=student,
                                             benefits=tuple(benefits)))

    elif product == "Bond / Guarantee":
        bt = st.selectbox("Bond type", list_categories("bond"))
        bv = st.number_input("Bond value (Rwf)", min_value=0.0, value=50_000_000.0, step=1_000_000.0)
        cc = st.checkbox("100% cash collateral (rate -> 3%)", value=False)
        if st.button("Calculate", type="primary"):
            show_quote(prod_mod.quote_bond(bt, bv, cash_collateral_100=cc))

    elif product == "PVT (Political Violence & Terrorism)":
        st.caption("Note: PVT rates are quoted **per mille**, not percent.")
        rt = st.selectbox("Risk type", list_categories("pvt"))
        si = st.number_input("Sum insured (Rwf)", min_value=0.0, value=1_000_000_000.0, step=10_000_000.0)
        disc = st.slider("Security features discount (%) — max 10", 0, 10, 0)
        if st.button("Calculate", type="primary"):
            show_quote(prod_mod.quote_pvt(rt, si, security_features_discount=disc))

    elif product == "Engineering CAR/EAR":
        kind = st.selectbox("Type", ["car", "ear"])
        pt = st.selectbox("Project type", list_categories("ear_car"))
        cv = st.number_input("Contract value (Rwf)", min_value=0.0, value=100_000_000.0, step=5_000_000.0)
        dur = st.slider("Duration (months)", 1, 60, 12)
        tpl = st.number_input("TPL limit (Rwf, 0 = none)", min_value=0.0, value=0.0, step=1_000_000.0)
        if st.button("Calculate", type="primary"):
            show_quote(prod_mod.quote_car_ear(kind, pt, cv, duration_months=dur, tpl_limit=tpl))

    elif product == "Machinery Breakdown":
        mt = st.selectbox("Machine type", list_categories("machinery"))
        si = st.number_input("Sum insured (Rwf)", min_value=0.0, value=10_000_000.0, step=1_000_000.0)
        if st.button("Calculate", type="primary"):
            show_quote(prod_mod.quote_machinery(mt, si))

    elif product == "Contractors Plant & Machinery":
        grp = st.selectbox("Plant group", ["1", "2", "3"],
                           format_func=lambda g: {"1": "1 — Cranes", "2": "2 — Mobile plant",
                                                  "3": "3 — Non-mobile"}[g])
        haz = st.selectbox("Hazard class", ["A", "B", "C"])
        si = st.number_input("Sum insured (Rwf)", min_value=0.0, value=20_000_000.0, step=1_000_000.0)
        if st.button("Calculate", type="primary"):
            show_quote(prod_mod.quote_cpm(grp, haz, si))

    elif product == "Burglary & Theft":
        si = st.number_input("Sum insured (Rwf)", min_value=0.0, value=20_000_000.0, step=1_000_000.0)
        hv = st.checkbox("High-value stock", value=False)
        fl = st.number_input("First-loss ratio (0 = full value)", min_value=0.0, max_value=1.0, value=0.0, step=0.05)
        sd = st.checkbox("Stock declaration basis (-10%)", value=False)
        if st.button("Calculate", type="primary"):
            show_quote(fire_mod.quote_burglary(si, high_value=hv,
                                               first_loss_ratio=fl or None,
                                               stock_declaration=sd))


# --------------------------------------------------------------------------- #
# Database tab — browse and query the rate database directly
# --------------------------------------------------------------------------- #
INFO_DB_PATH = DB_PATH.parent / "assar_info.db"


def read_only_conn(db_path=DB_PATH):
    """A genuinely read-only SQLite connection (URI mode=ro)."""
    import sqlite3
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


def list_db_tables(db_path) -> list[str]:
    con = read_only_conn(db_path)
    try:
        return [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    finally:
        con.close()


_FORBIDDEN = ("insert", "update", "delete", "drop", "alter", "create",
              "attach", "detach", "pragma", "replace", "vacuum")


def run_select(sql: str, db_path=DB_PATH) -> pd.DataFrame:
    s = sql.strip().rstrip(";")
    low = s.lower()
    if not low.startswith("select") and not low.startswith("with"):
        raise ValueError("Only SELECT / WITH queries are allowed.")
    if ";" in s:
        raise ValueError("One statement at a time (no ';').")
    if any(w in low.split() for w in _FORBIDDEN):
        raise ValueError("Read-only: write/DDL keywords are blocked.")
    con = read_only_conn(db_path)
    try:
        return pd.read_sql(s, con)
    finally:
        con.close()


_PRICING_SQL_EXAMPLES = {
    "Fire rates (all special perils > 0.4%)":
        "SELECT category, rate AS standard_fire, rate_alt AS all_perils\n"
        "FROM rate WHERE scheme='fire' AND rate_alt > 0.4\nORDER BY rate_alt DESC",
    "All PVT rates (per mille)":
        "SELECT category, rate, unit FROM rate WHERE scheme='pvt' ORDER BY rate",
    "Minimum premiums by product":
        "SELECT product, value AS min_premium FROM product_rule\n"
        "WHERE key='min_premium' ORDER BY value DESC",
    "Count rates per scheme":
        "SELECT scheme, COUNT(*) AS n FROM rate GROUP BY scheme ORDER BY n DESC",
}

_INFO_SQL_EXAMPLES = {
    "Fire rate for a bank":
        "SELECT * FROM fire_allied_perils WHERE risk_category LIKE '%Bank%'",
    "PVT rates (per mille)":
        "SELECT description_of_risk, rate_per_mille FROM pvt_political_violence_terrorism",
    "Top 10 largest property risks":
        "SELECT property, insured_value_rwf FROM large_risks_property\n"
        "ORDER BY insured_value_rwf DESC LIMIT 10",
    "Units of every numeric column (data dictionary)":
        "SELECT table_name, column_name, unit FROM data_dictionary\n"
        "WHERE unit LIKE '%percent%' OR unit LIKE '%mille%' OR unit LIKE '%RWF%'",
    "All bonds & guarantees":
        "SELECT * FROM bonds_guarantees",
}


with tab_db:
    db_choice = st.radio(
        "Database",
        ["Pricing engine · assar.db (4 tables)",
         "Information engine · assar_info.db (46 tables)"],
        horizontal=True,
    )
    is_info = db_choice.startswith("Information")
    db_path = INFO_DB_PATH if is_info else DB_PATH

    if is_info:
        st.caption("One SQL table per table in the manual — natural for asking "
                   "general questions about the numbers. Units are documented in "
                   "the `data_dictionary` table.")
    else:
        st.caption("The four generic tables the deterministic pricing engine reads from.")

    try:
        tables = list_db_tables(db_path)
    except Exception as exc:  # noqa: BLE001
        st.error(f"Could not open {db_path.name}: {exc}. "
                 f"Build it with `python -m assar.build_info_tables`.")
        tables = []

    mode = st.radio("Mode", ["Browse tables", "Run SQL"], horizontal=True)

    if mode == "Browse tables" and tables:
        con = read_only_conn(db_path)
        table = st.selectbox(f"Table ({len(tables)} available)", tables)
        df = pd.read_sql(f"SELECT * FROM {table}", con)
        con.close()

        if not is_info and table == "rate":
            schemes = sorted(df["scheme"].unique())
            pick = st.multiselect("Filter scheme(s)", schemes, default=[])
            if pick:
                df = df[df["scheme"].isin(pick)]

        kw = st.text_input("Search (matches any text column)", "")
        if kw:
            mask = pd.Series(False, index=df.index)
            for col in df.select_dtypes(include="object").columns:
                mask |= df[col].astype(str).str.contains(kw, case=False, na=False)
            df = df[mask]

        st.caption(f"{len(df)} rows")
        st.dataframe(df, use_container_width=True, hide_index=True)
        st.download_button("Download CSV", df.to_csv(index=False).encode(),
                           file_name=f"{table}.csv", mime="text/csv")

    elif mode == "Run SQL":
        st.caption("Read-only. `SELECT`/`WITH` only; writes and DDL are blocked.")
        sql_examples = _INFO_SQL_EXAMPLES if is_info else _PRICING_SQL_EXAMPLES
        ex = st.selectbox("Example queries", ["—"] + list(sql_examples))
        fallback = ("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                    if is_info else "SELECT * FROM rate LIMIT 20")
        default_sql = sql_examples.get(ex, fallback)
        sql = st.text_area("SQL", value=default_sql, height=130)
        if st.button("Run query", type="primary"):
            try:
                res = run_select(sql, db_path)
                st.success(f"{len(res)} rows")
                st.dataframe(res, use_container_width=True, hide_index=True)
                st.download_button("Download CSV", res.to_csv(index=False).encode(),
                                   file_name="query_result.csv", mime="text/csv")
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))

        if is_info:
            with st.expander("Tables in the information engine"):
                st.write(", ".join(tables))
        else:
            with st.expander("Schema reference"):
                st.code(
                    "rate(scheme, category, rate, rate_alt, unit, note)\n"
                    "transit_rate(scheme, code, commodity, ra_*, ar_*, excess)\n"
                    "schedule(name, lower, upper, label, value, kind, ord)\n"
                    "product_rule(product, key, value, text)",
                    language="text",
                )
