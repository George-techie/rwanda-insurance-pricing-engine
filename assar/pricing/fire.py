"""Fire & Allied Perils, Consequential Loss, Burglary/Theft, Plate Glass."""
from __future__ import annotations

from ..db import connect
from .base import (
    Quote, apply_minimum, get_rate, policy_fee, premium_from_rate, product_rule,
    short_period_fraction, voluntary_deductible_discount,
)


def quote_fire(
    risk_category: str,
    sum_insured: float,
    *,
    special_perils: bool = True,
    industrial: bool = False,
    fea_available: bool = False,
    voluntary_excess: float = 0.0,
    period_months: float | None = None,
    conn=None,
) -> Quote:
    """Price Fire & Allied Perils material damage.

    special_perils : True -> 'fire + all special perils' column, else standard fire.
    industrial     : adds 0.025% process loading + Rwf25,000 extensions loading,
                     neither of which enjoys the FEA discount.
    fea_available  : applies 15% FEA discount to the fire portion only.
    """
    own = conn is None
    conn = conn or connect()
    try:
        q = Quote(product="fire", sum_insured=sum_insured)
        base_rate, _ = get_rate("fire", risk_category, alt=special_perils, conn=conn)
        q.rate = base_rate
        col = "fire + all special perils" if special_perils else "standard fire"
        q.add(f"Base rate ({col}) for '{risk_category}': {base_rate}%")

        fire_portion = premium_from_rate(sum_insured, base_rate)
        process_portion = 0.0
        ext_load = 0.0

        if industrial:
            load = product_rule("fire", "industrial_load", 0.025, conn=conn)
            process_portion = premium_from_rate(sum_insured, load)
            ext_load = product_rule("fire", "industrial_ext_load", 25_000, conn=conn)
            q.add(f"Industrial process loading +{load}% = {process_portion:,.0f}")
            q.add(f"Industrial extensions flat loading = {ext_load:,.0f}")

        q.gross_premium = fire_portion + process_portion + ext_load

        # FEA discount: fire portion only (not process loading / perils / extensions)
        net = q.gross_premium
        if fea_available:
            fea = product_rule("fire", "fea_discount", 15.0, conn=conn)
            disc = fire_portion * fea / 100.0
            net -= disc
            q.add(f"FEA discount {fea}% on fire portion only = -{disc:,.0f}")

        # Voluntary deductible discount
        if voluntary_excess > 0:
            pct, saving = voluntary_deductible_discount(voluntary_excess, net, conn=conn)
            if pct:
                net -= saving
                q.add(f"Voluntary excess {voluntary_excess:,.0f} -> {pct}% discount "
                      f"(capped) = -{saving:,.0f}")
        q.net_premium = net

        # Short period
        frac = short_period_fraction(period_months, conn=conn)
        if frac < 1.0:
            q.add(f"Short-period factor ({period_months} months) = {frac:.4f}")
            q.net_premium *= frac

        fee = policy_fee(conn=conn)
        q.policy_fee = fee
        q.final_premium = q.net_premium + fee
        q.add(f"Policy fee = {fee:,.0f}")
        q.add(f"FINAL premium (net of taxes) = {q.final_premium:,.0f}")
        q.warn("All fire MD covers are subject to the Condition of Average.")
        return q
    finally:
        if own:
            conn.close()


def quote_consequential_loss(
    risk_category: str,
    gross_profit_si: float,
    *,
    indemnity_period_months: int = 12,
    cover: str = "gross_profit",   # gross_profit | auditors_fees | wages
    period_months: float | None = None,
    conn=None,
) -> Quote:
    """Business interruption following fire. Basis = applicable fire MD rate."""
    own = conn is None
    conn = conn or connect()
    try:
        q = Quote(product="consequential_loss", sum_insured=gross_profit_si)
        fire_rate, _ = get_rate("fire", risk_category, alt=False, conn=conn)
        key = {"gross_profit": "gross_profit_pct", "auditors_fees": "auditors_fees_pct",
               "wages": "wages_pct"}[cover]
        cover_pct = product_rule("consequential_loss", key, 100.0, conn=conn)
        basis_rate = fire_rate * cover_pct / 100.0
        q.add(f"Fire MD basis rate '{risk_category}': {fire_rate}%; "
              f"{cover} factor {cover_pct}% -> basis {basis_rate:.4f}%")

        row = conn.execute(
            "SELECT value,label FROM schedule WHERE name='ci_indemnity' AND upper >= ? "
            "ORDER BY upper ASC LIMIT 1", (indemnity_period_months,)
        ).fetchone()
        ip_mult = float(row["value"]) if row else 100.0
        eff_rate = basis_rate * ip_mult / 100.0
        q.rate = eff_rate
        q.add(f"Indemnity period {indemnity_period_months}m -> {ip_mult}% of basis "
              f"=> effective rate {eff_rate:.4f}%")

        q.gross_premium = premium_from_rate(gross_profit_si, eff_rate)
        q.net_premium = q.gross_premium
        frac = short_period_fraction(period_months, conn=conn)
        if frac < 1.0:
            q.net_premium *= frac
            q.add(f"Short-period factor = {frac:.4f}")
        fee = policy_fee(conn=conn)
        q.policy_fee = fee
        q.final_premium = q.net_premium + fee
        q.excess = "Mandatory time excess: 14 days"
        q.add(f"Policy fee = {fee:,.0f}; FINAL = {q.final_premium:,.0f}")
        return q
    finally:
        if own:
            conn.close()


def quote_burglary(
    sum_insured: float,
    *,
    high_value: bool = False,
    first_loss_ratio: float | None = None,   # first-loss SI / full value at risk
    stock_declaration: bool = False,
    period_months: float | None = None,
    conn=None,
) -> Quote:
    """Burglary & Theft. Full value 0.3% ordinary / 0.5% high value, first-loss multipliers."""
    own = conn is None
    conn = conn or connect()
    try:
        q = Quote(product="burglary", sum_insured=sum_insured)
        rate = 0.5 if high_value else 0.3
        q.add(f"Full-value rate ({'high value' if high_value else 'ordinary'}): {rate}%")
        q.gross_premium = premium_from_rate(sum_insured, rate)
        net = q.gross_premium

        if first_loss_ratio is not None:
            row = conn.execute(
                "SELECT value,upper FROM schedule WHERE name='first_loss' AND upper >= ? "
                "ORDER BY upper ASC LIMIT 1", (first_loss_ratio,)
            ).fetchone()
            mult = float(row["value"]) if row else 100.0
            net = net * mult / 100.0
            q.add(f"First-loss ratio {first_loss_ratio:.0%} -> {mult}% multiplier")

        if stock_declaration:
            disc = product_rule("burglary", "stock_declaration_discount", 10.0, conn=conn)
            net *= (1 - disc / 100.0)
            q.add(f"Stock declaration discount = -{disc}%")

        q.rate = rate
        q.net_premium = net
        frac = short_period_fraction(period_months, conn=conn)
        if frac < 1.0:
            q.net_premium *= frac
        fee = policy_fee(conn=conn)
        q.policy_fee = fee
        q.final_premium = q.net_premium + fee
        q.excess = "10% of each and every loss, min Rwf50,000"
        q.add(f"Policy fee = {fee:,.0f}; FINAL = {q.final_premium:,.0f}")
        return q
    finally:
        if own:
            conn.close()
