"""Shared pricing primitives used by every product calculator.

Design: the LLM never does arithmetic. It extracts parameters and calls these
deterministic functions; the functions read EXACT rates from SQLite and compose
the premium. Every public function is unit-tested in tests/test_pricing.py.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..db import connect


# --------------------------------------------------------------------------- #
# Quote result container
# --------------------------------------------------------------------------- #
@dataclass
class Quote:
    product: str
    sum_insured: float | None = None
    rate: float | None = None            # effective rate actually applied
    rate_unit: str = "percent"
    gross_premium: float = 0.0
    net_premium: float = 0.0             # after discounts, before fees/min floor
    final_premium: float = 0.0           # what the client pays (net of taxes/fees)
    policy_fee: float = 0.0
    lines: list[str] = field(default_factory=list)   # human-readable breakdown
    excess: str | None = None
    warnings: list[str] = field(default_factory=list)

    def add(self, msg: str) -> None:
        self.lines.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def as_dict(self) -> dict:
        return {
            "product": self.product,
            "sum_insured": self.sum_insured,
            "rate": self.rate,
            "rate_unit": self.rate_unit,
            "gross_premium": round(self.gross_premium, 2),
            "net_premium": round(self.net_premium, 2),
            "final_premium": round(self.final_premium, 2),
            "policy_fee": self.policy_fee,
            "excess": self.excess,
            "breakdown": self.lines,
            "warnings": self.warnings,
        }


class RateNotFound(Exception):
    pass


# --------------------------------------------------------------------------- #
# Low-level lookups
# --------------------------------------------------------------------------- #
def get_rate(scheme: str, category: str, *, alt: bool = False, conn=None) -> tuple[float, str]:
    """Return (rate, unit) for a scheme/category. `alt` selects the second column."""
    own = conn is None
    conn = conn or connect()
    try:
        col = "rate_alt" if alt else "rate"
        row = conn.execute(
            f"SELECT {col} AS r, unit FROM rate WHERE scheme=? AND category=?",
            (scheme, category),
        ).fetchone()
        if row is None or row["r"] is None:
            raise RateNotFound(f"No rate for scheme='{scheme}', category='{category}'"
                               f"{' (alt column)' if alt else ''}")
        return float(row["r"]), row["unit"]
    finally:
        if own:
            conn.close()


def list_categories(scheme: str, conn=None) -> list[str]:
    own = conn is None
    conn = conn or connect()
    try:
        rows = conn.execute(
            "SELECT category FROM rate WHERE scheme=? ORDER BY category", (scheme,)
        ).fetchall()
        return [r["category"] for r in rows]
    finally:
        if own:
            conn.close()


def product_rule(product: str, key: str, default=None, conn=None):
    own = conn is None
    conn = conn or connect()
    try:
        row = conn.execute(
            "SELECT value FROM product_rule WHERE product=? AND key=?", (product, key)
        ).fetchone()
        return row["value"] if row else default
    finally:
        if own:
            conn.close()


def policy_fee(conn=None) -> float:
    return product_rule("global", "policy_fee", 5_000.0, conn=conn)


# --------------------------------------------------------------------------- #
# Discounts and multipliers
# --------------------------------------------------------------------------- #
def voluntary_deductible_discount(excess_amount: float, gross_premium: float, conn=None) -> tuple[float, float]:
    """Return (discount_pct, capped_discount_amount).

    Discount % comes from the schedule band; the saving is capped at 33.33% of
    the excess amount (manual rule).
    """
    own = conn is None
    conn = conn or connect()
    try:
        row = conn.execute(
            "SELECT value FROM schedule WHERE name='voluntary_deductible' "
            "AND (lower IS NULL OR ? >= lower) AND (upper IS NULL OR ? < upper) "
            "ORDER BY ord DESC LIMIT 1",
            (excess_amount, excess_amount),
        ).fetchone()
        if row is None:
            return 0.0, 0.0
        pct = float(row["value"])
        saving = gross_premium * pct / 100.0
        cap = excess_amount * 33.33 / 100.0
        return pct, min(saving, cap)
    finally:
        if own:
            conn.close()


def short_period_fraction(period_months: float | None, period_days: int | None = None,
                          schedule: str = "short_period_months", conn=None) -> float:
    """Fraction of annual premium for a short-period cover. Returns 1.0 for full year."""
    if period_months is None and period_days is None:
        return 1.0
    own = conn is None
    conn = conn or connect()
    try:
        if period_days is not None and period_days < 28:
            row = conn.execute(
                "SELECT value FROM schedule WHERE name='short_period_days' AND upper >= ? "
                "ORDER BY upper ASC LIMIT 1", (period_days,)
            ).fetchone()
            if row:
                return float(row["value"])
        if period_months is None:
            return 1.0
        if period_months >= 12:
            return 1.0
        row = conn.execute(
            "SELECT value FROM schedule WHERE name=? AND upper >= ? "
            "ORDER BY upper ASC LIMIT 1", (schedule, period_months)
        ).fetchone()
        return float(row["value"]) if row else 1.0
    finally:
        if own:
            conn.close()


def apply_minimum(premium: float, minimum: float | None, quote: Quote | None = None) -> float:
    """Floor the premium at a product minimum (net of taxes/fees)."""
    if minimum is not None and premium < minimum:
        if quote is not None:
            quote.add(f"Premium {premium:,.0f} below minimum {minimum:,.0f} -> charge minimum")
        return float(minimum)
    return premium


def premium_from_rate(sum_insured: float, rate: float, unit: str = "percent") -> float:
    """Premium = SI * rate. Percent divides by 100, per_mille divides by 1000."""
    if unit == "per_mille":
        return sum_insured * rate / 1000.0
    if unit == "amount":
        return rate
    return sum_insured * rate / 100.0
