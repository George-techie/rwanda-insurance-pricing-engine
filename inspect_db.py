"""Inspect the ASSAR rate database.

Usage:
    python inspect_db.py                 # pretty-print every table to the console
    python inspect_db.py --scheme fire   # print just one rate scheme
    python inspect_db.py --csv out/       # export every table to CSV files
    python inspect_db.py --xlsx rates.xlsx  # export to a single multi-sheet Excel file

Handy for eyeballing the transcribed rates against the source manual before use.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parent / "data" / "assar.db"
TABLES = ["rate", "transit_rate", "schedule", "product_rule"]


def load(con, table: str) -> pd.DataFrame:
    return pd.read_sql(f"SELECT * FROM {table}", con)


def print_all(con, scheme: str | None):
    if scheme:
        df = pd.read_sql("SELECT * FROM rate WHERE scheme=?", con, params=(scheme,))
        print(f"\n=== rate (scheme='{scheme}') — {len(df)} rows ===")
        if df.empty:
            schemes = pd.read_sql("SELECT DISTINCT scheme FROM rate ORDER BY scheme", con)
            print("  no rows. available schemes:", ", ".join(schemes["scheme"]))
        else:
            print(df.to_string(index=False))
        return

    for t in TABLES:
        df = load(con, t)
        print(f"\n{'='*70}\n{t}  —  {len(df)} rows\n{'='*70}")
        if t == "rate":
            # group by scheme for readability
            for sc, g in df.groupby("scheme"):
                print(f"\n  [{sc}]  ({len(g)} rows)")
                print(g.drop(columns=["scheme"]).to_string(index=False))
        else:
            with pd.option_context("display.max_rows", None, "display.width", 200):
                print(df.to_string(index=False))


def export_csv(con, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    for t in TABLES:
        path = out_dir / f"{t}.csv"
        load(con, t).to_csv(path, index=False)
        print(f"wrote {path}")


def export_xlsx(con, path: Path):
    with pd.ExcelWriter(path) as xl:
        for t in TABLES:
            load(con, t).to_excel(xl, sheet_name=t, index=False)
    print(f"wrote {path}")


def main():
    ap = argparse.ArgumentParser(description="Inspect the ASSAR rate database.")
    ap.add_argument("--db", default=str(DB_PATH))
    ap.add_argument("--scheme", help="print only this rate scheme (e.g. fire, pvt, money)")
    ap.add_argument("--csv", metavar="DIR", help="export all tables to CSV files in DIR")
    ap.add_argument("--xlsx", metavar="FILE", help="export all tables to one Excel workbook")
    args = ap.parse_args()

    con = sqlite3.connect(args.db)
    try:
        if args.csv:
            export_csv(con, Path(args.csv))
        elif args.xlsx:
            export_xlsx(con, Path(args.xlsx))
        else:
            print_all(con, args.scheme)
            counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}
            print("\n" + "-" * 40)
            print("TOTALS:", ", ".join(f"{t}={n}" for t, n in counts.items()))
    finally:
        con.close()


if __name__ == "__main__":
    main()
