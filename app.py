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


st.title("📑 ASSAR Pricing Assistant")
st.caption("Hybrid retrieval over the Rwandan Insurance Industry Pricing Manual (v3): "
           "SQL for rate tables, vector search for the prose.")

tab_ask, tab_quote, tab_db = st.tabs(["💬 Ask", "🧮 Get a Quote", "🗄️ Database"])


# --------------------------------------------------------------------------- #
# Ask tab — free text through the router
# --------------------------------------------------------------------------- #
with tab_ask:
    st.markdown("Ask a pricing question or request a quote in plain language.")
    examples = [
        "Quote fire cover for a tannery, sum insured 200,000,000, industrial, with FEA, standard fire only",
        "What is the difference between a policy excess and a franchise?",
        "PVT cover for a hotel, sum insured 1,000,000,000",
        "Public liability for a manufacturer, limit of indemnity 50,000,000",
    ]
    ex = st.selectbox("Examples", ["—"] + examples, index=0)
    query = st.text_area("Your question", value="" if ex == "—" else ex, height=80)

    if st.button("Ask", type="primary"):
        if not query.strip():
            st.warning("Type a question first.")
        else:
            from assar.llm.router import answer_query
            with st.spinner("Thinking…"):
                res = answer_query(query)

            st.markdown("### Answer")
            st.markdown(res.answer or "_(no answer)_")
            if res.error:
                st.info(f"Note: {res.error}")

            if res.tool_calls:
                st.markdown("### 🧮 Rates & figures used")
                for tc in res.tool_calls:
                    r = tc["result"]
                    if "error" in r:
                        st.error(f"{tc['name']}: {r['error']}")
                        continue
                    cols = st.columns(3)
                    cols[0].metric("Product", r["product"])
                    cols[1].metric("Rate", f"{r['rate']} {r.get('rate_unit','%')}")
                    cols[2].metric("Final premium", f"Rwf{r['final_premium']:,.0f}")
                    with st.expander("Breakdown"):
                        for line in r.get("breakdown", []):
                            st.text(line)
                        if r.get("excess"):
                            st.caption(f"Excess: {r['excess']}")
                        for w in r.get("warnings", []):
                            st.caption(f"⚠️ {w}")

            with st.expander(f"📄 Retrieved manual passages ({len(res.retrieved)})"):
                if not res.retrieved:
                    st.caption("No prose retrieved (vector store may not be built).")
                for c in res.retrieved:
                    st.markdown(f"**Page {c['page']}** · similarity {c['score']:.2f}")
                    st.caption(c["text"][:500] + ("…" if len(c["text"]) > 500 else ""))


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
def read_only_conn():
    """A genuinely read-only SQLite connection (URI mode=ro)."""
    import sqlite3
    return sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)


_TABLES = ["rate", "transit_rate", "schedule", "product_rule"]
_FORBIDDEN = ("insert", "update", "delete", "drop", "alter", "create",
              "attach", "detach", "pragma", "replace", "vacuum")


def run_select(sql: str) -> pd.DataFrame:
    s = sql.strip().rstrip(";")
    low = s.lower()
    if not low.startswith("select") and not low.startswith("with"):
        raise ValueError("Only SELECT / WITH queries are allowed.")
    if ";" in s:
        raise ValueError("One statement at a time (no ';').")
    if any(w in low.split() for w in _FORBIDDEN):
        raise ValueError("Read-only: write/DDL keywords are blocked.")
    con = read_only_conn()
    try:
        return pd.read_sql(s, con)
    finally:
        con.close()


with tab_db:
    st.markdown("Query the rate database directly — the same SQLite the pricing "
                "engine reads from.")
    mode = st.radio("Mode", ["Browse tables", "Run SQL"], horizontal=True)

    if mode == "Browse tables":
        con = read_only_conn()
        table = st.selectbox("Table", _TABLES)
        df = pd.read_sql(f"SELECT * FROM {table}", con)
        con.close()

        if table == "rate":
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
        st.download_button("⬇️ Download CSV", df.to_csv(index=False).encode(),
                           file_name=f"{table}.csv", mime="text/csv")

    else:  # Run SQL
        st.caption("Read-only. `SELECT`/`WITH` only — writes and DDL are blocked.")
        sql_examples = {
            "Fire rates (all special perils > 0.4%)":
                "SELECT category, rate AS standard_fire, rate_alt AS all_perils\n"
                "FROM rate WHERE scheme='fire' AND rate_alt > 0.4\nORDER BY rate_alt DESC",
            "All PVT rates (per mille)":
                "SELECT category, rate, unit FROM rate WHERE scheme='pvt' ORDER BY rate",
            "Minimum premiums by product":
                "SELECT product, value AS min_premium FROM product_rule\n"
                "WHERE key='min_premium' ORDER BY value DESC",
            "GIT all-risks rates":
                "SELECT commodity, ar_containerized, ar_noncontainerized, excess\n"
                "FROM transit_rate WHERE scheme='git'",
            "Count rates per scheme":
                "SELECT scheme, COUNT(*) AS n FROM rate GROUP BY scheme ORDER BY n DESC",
        }
        ex = st.selectbox("Example queries", ["—"] + list(sql_examples))
        default_sql = sql_examples.get(ex, "SELECT * FROM rate LIMIT 20")
        sql = st.text_area("SQL", value=default_sql, height=130)
        if st.button("Run query", type="primary"):
            try:
                res = run_select(sql)
                st.success(f"{len(res)} rows")
                st.dataframe(res, use_container_width=True, hide_index=True)
                st.download_button("⬇️ Download CSV", res.to_csv(index=False).encode(),
                                   file_name="query_result.csv", mime="text/csv")
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))

        with st.expander("Schema reference"):
            st.code(
                "rate(scheme, category, rate, rate_alt, unit, note)\n"
                "    unit: 'percent' everywhere except scheme='pvt' (per_mille)\n"
                "          and flat-amount rows (school_liability, marine_hull_occupant)\n"
                "    rate_alt: second column where a table has two (e.g. fire:\n"
                "              rate=standard fire, rate_alt=all special perils)\n\n"
                "transit_rate(scheme, code, commodity, ra_containerized,\n"
                "    ra_noncontainerized, ar_containerized, ar_noncontainerized, excess)\n"
                "    scheme: 'git' | 'marine_cargo'\n\n"
                "schedule(name, lower, upper, label, value, kind, ord)\n"
                "    banded discounts/multipliers (voluntary_deductible, short_period_*,\n"
                "    ci_indemnity, first_loss, ...)\n\n"
                "product_rule(product, key, value, text)\n"
                "    minimum premiums, excesses, fees, loadings",
                language="text",
            )
