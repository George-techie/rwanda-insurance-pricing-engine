"""SQLite layer for the ASSAR pricing manual.

The structured rate tables live here (not in the vector store) so that lookups
return EXACT numbers and the pricing arithmetic stays deterministic. The prose
of the manual (definitions, warranties, exclusions, underwriting guidance) lives
in the vector store instead — see assar/rag/.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "assar.db"

SCHEMA = """
PRAGMA foreign_keys = ON;

-- Generic risk-category -> rate(s) table. `scheme` namespaces a rate family
-- (e.g. 'fire', 'public_liability', 'pa_gpa', 'bond', 'pvt', 'machinery').
DROP TABLE IF EXISTS rate;
CREATE TABLE rate (
    scheme        TEXT NOT NULL,
    category      TEXT NOT NULL,
    rate          REAL,            -- primary rate (% unless unit says otherwise)
    rate_alt      REAL,            -- secondary rate where a table has two columns
    unit          TEXT NOT NULL DEFAULT 'percent',  -- 'percent' | 'per_mille' | 'amount'
    note          TEXT,
    PRIMARY KEY (scheme, category)
);

-- Transit commodity rates (GIT / Transporters Liability / Marine Cargo) which
-- have a 2x2 grid of (road-accident vs all-risks) x (containerized vs not).
DROP TABLE IF EXISTS transit_rate;
CREATE TABLE transit_rate (
    scheme               TEXT NOT NULL,   -- 'git' | 'marine_cargo'
    code                 TEXT NOT NULL,   -- '1.a', '2.b', ...
    commodity            TEXT NOT NULL,
    ra_containerized     REAL,            -- road-accident-only, containerized
    ra_noncontainerized  REAL,
    ar_containerized     REAL,            -- all-risks, containerized
    ar_noncontainerized  REAL,
    excess               TEXT,
    PRIMARY KEY (scheme, code)
);

-- Discount/multiplier schedules keyed by an ordered band.
DROP TABLE IF EXISTS schedule;
CREATE TABLE schedule (
    name        TEXT NOT NULL,   -- 'voluntary_deductible', 'short_period', 'ci_indemnity', ...
    lower       REAL,            -- inclusive lower bound of the band (amount/days/months)
    upper       REAL,            -- exclusive upper bound (NULL = open ended)
    label       TEXT,
    value       REAL NOT NULL,   -- discount % or multiplier (see `kind`)
    kind        TEXT NOT NULL,   -- 'discount_pct' | 'multiplier_pct' | 'fraction'
    ord         INTEGER NOT NULL
);

-- Per-product constants: minimum premiums, mandatory excesses, policy fees.
DROP TABLE IF EXISTS product_rule;
CREATE TABLE product_rule (
    product     TEXT NOT NULL,
    key         TEXT NOT NULL,
    value       REAL,
    text        TEXT,
    PRIMARY KEY (product, key)
);

-- Tenancy: the platform serves several insurers over the one shared ASSAR
-- schedule. Each insurer may keep private rate overrides that overlay the base
-- `rate` table for their own pricing only.
DROP TABLE IF EXISTS rate_override;   -- drop child first (FK to insurer)
DROP TABLE IF EXISTS insurer;
CREATE TABLE insurer (
    id    INTEGER PRIMARY KEY,
    slug  TEXT NOT NULL UNIQUE,
    name  TEXT NOT NULL
);

-- An insurer-specific overlay on `rate`. A non-NULL value here wins over the
-- base rate for THAT insurer only; absence falls through to the shared base.
DROP TABLE IF EXISTS rate_override;
CREATE TABLE rate_override (
    insurer_id  INTEGER NOT NULL,
    scheme      TEXT NOT NULL,
    category    TEXT NOT NULL,
    rate        REAL,
    rate_alt    REAL,
    unit        TEXT,
    note        TEXT,
    PRIMARY KEY (insurer_id, scheme, category),
    FOREIGN KEY (insurer_id) REFERENCES insurer(id)
);
"""


def connect(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")  # enforce the insurer FK at runtime
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
