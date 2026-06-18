"""Goods in Transit, Transporters Liability, Marine Cargo."""
from __future__ import annotations

from ..db import connect
from .base import Quote, policy_fee, premium_from_rate

# Multi-trip multipliers (months -> % of annual premium)
MULTI_TRIP = [(3, 30), (6, 60), (9, 90), (12, 100)]


def _closest_commodity(scheme, commodity, conn):
    """Snap an approximate commodity to a valid key within the scheme."""
    import difflib

    names = [r[0] for r in conn.execute(
        "SELECT commodity FROM transit_rate WHERE scheme=?", (scheme,))]
    q = commodity.strip().lower()
    close = difflib.get_close_matches(q, names, n=1, cutoff=0.6)
    if close:
        return close[0]
    contains = [n for n in names if q in n or n in q]
    if contains:
        return max(contains, key=lambda n: difflib.SequenceMatcher(None, q, n).ratio())
    return None


def _transit_rate(scheme, commodity, cover, containerized, conn):
    col = {
        ("road_accident", True): "ra_containerized",
        ("road_accident", False): "ra_noncontainerized",
        ("all_risks", True): "ar_containerized",
        ("all_risks", False): "ar_noncontainerized",
    }[(cover, containerized)]

    def fetch(c):
        return conn.execute(
            f"SELECT {col} AS r, excess FROM transit_rate WHERE scheme=? AND commodity=?",
            (scheme, c),
        ).fetchone()

    row = fetch(commodity)
    if row is None:
        snapped = _closest_commodity(scheme, commodity, conn)
        if snapped is not None:
            row = fetch(snapped)
    if row is None:
        raise ValueError(f"No {scheme} commodity '{commodity}'")
    if row["r"] is None:
        raise ValueError(f"'{commodity}' not available as {cover}/"
                         f"{'containerized' if containerized else 'non-containerized'}")
    return float(row["r"]), row["excess"]


def quote_git(
    commodity: str,
    consignment_value: float,
    *,
    cover: str = "all_risks",        # all_risks | road_accident
    containerized: bool = True,
    transporters_liability: bool = False,   # +30% if transport outside Rwanda
    outside_rwanda: bool = False,
    trips_period_months: int | None = None, # None = single/annual rate
    conn=None,
) -> Quote:
    """Goods in Transit / Transporters Liability."""
    own = conn is None
    conn = conn or connect()
    try:
        product = "transporters_liability" if transporters_liability else "git"
        q = Quote(product=product, sum_insured=consignment_value)
        rate, excess = _transit_rate("git", commodity, cover, containerized, conn)
        q.add(f"GIT base rate '{commodity}' ({cover}, "
              f"{'containerized' if containerized else 'non-containerized'}): {rate}%")

        if transporters_liability and outside_rwanda:
            rate *= 1.30
            q.add("Transport outside Rwanda -> +30% loading")

        q.rate = rate
        q.gross_premium = premium_from_rate(consignment_value, rate)
        q.net_premium = q.gross_premium

        if trips_period_months is not None:
            mult = next((m for cap, m in MULTI_TRIP if trips_period_months <= cap), 100)
            q.net_premium = q.gross_premium * mult / 100.0
            q.add(f"Multi-trip ({trips_period_months}m) -> {mult}% of annual premium")

        fee = policy_fee(conn=conn)
        q.policy_fee = fee
        q.final_premium = q.net_premium + fee
        q.excess = excess
        q.add(f"Policy fee = {fee:,.0f}; FINAL = {q.final_premium:,.0f}")
        return q
    finally:
        if own:
            conn.close()


# Marine cargo mode discounts off ICC-A
MODE_DISCOUNT = {"combined": 0, "road": 10, "air": 30, "sea": 20}
CLAUSE_DISCOUNT = {"A": 0, "B": 25, "C": 35}


def quote_marine_cargo(
    commodity: str,
    consignment_value: float,
    *,
    containerized: bool = True,
    mode: str = "combined",          # combined | road | air | sea
    clause: str = "A",               # A | B | C
    conn=None,
) -> Quote:
    """Marine Cargo. Base = ICC-A; apply mode discount then clause discount."""
    own = conn is None
    conn = conn or connect()
    try:
        q = Quote(product="marine_cargo", sum_insured=consignment_value)
        rate, excess = _transit_rate("marine_cargo", commodity, "all_risks", containerized, conn)
        q.add(f"ICC-A base rate '{commodity}': {rate}%")

        md = MODE_DISCOUNT.get(mode, 0)
        if md:
            rate *= (1 - md / 100.0)
            q.add(f"Mode '{mode}' -> -{md}% => {rate:.4f}%")
        cd = CLAUSE_DISCOUNT.get(clause, 0)
        if cd:
            rate *= (1 - cd / 100.0)
            q.add(f"Institute Cargo Clause {clause} -> -{cd}% => {rate:.4f}%")

        q.rate = rate
        q.gross_premium = premium_from_rate(consignment_value, rate)
        q.net_premium = q.gross_premium
        fee = policy_fee(conn=conn)
        q.policy_fee = fee
        q.final_premium = q.net_premium + fee
        q.excess = excess
        q.add(f"Policy fee = {fee:,.0f}; FINAL = {q.final_premium:,.0f}")
        return q
    finally:
        if own:
            conn.close()
