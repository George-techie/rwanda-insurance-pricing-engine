"""Liability suite, Personal/Group Personal Accident, Bonds, Fidelity, PVT, Engineering."""
from __future__ import annotations

from ..db import connect
from .base import (
    Quote, apply_minimum, get_rate, policy_fee, premium_from_rate, product_rule,
    short_period_fraction,
)

# --------------------------------------------------------------------------- #
# Liability suite (rate on selected limit of indemnity)
# --------------------------------------------------------------------------- #
_LIABILITY = {
    "public": ("public_liability", "public_liability"),
    "employers": ("employers_liability", "employers_liability"),
    "product": ("product_liability", "product_liability"),
    "professional": ("professional_indemnity", "professional_indemnity"),
}


def quote_liability(
    kind: str,                  # public | employers | product | professional
    occupation: str,
    limit_of_indemnity: float,
    *,
    period_months: float | None = None,
    conn=None,
) -> Quote:
    own = conn is None
    conn = conn or connect()
    try:
        scheme, product = _LIABILITY[kind]
        q = Quote(product=product, sum_insured=limit_of_indemnity)
        rate, _ = get_rate(scheme, occupation, conn=conn)
        q.rate = rate
        q.add(f"{kind.title()} liability rate '{occupation}': {rate}% on LOI {limit_of_indemnity:,.0f}")
        q.gross_premium = premium_from_rate(limit_of_indemnity, rate)
        q.net_premium = q.gross_premium

        frac = short_period_fraction(period_months, conn=conn)
        if frac < 1.0:
            q.net_premium *= frac
            q.add(f"Short-period factor = {frac:.4f}")

        # Minimum premium (PI agents get a lower floor)
        if product == "professional_indemnity" and occupation == "insurance_agents":
            minimum = product_rule(product, "min_premium_agents", 25_000, conn=conn)
        else:
            minimum = product_rule(product, "min_premium", 100_000, conn=conn)
        q.final_premium = apply_minimum(q.net_premium, minimum, q)
        if product == "professional_indemnity":
            q.excess = "5% of each and every loss, min Rwf200,000"
        q.add(f"FINAL premium (net of taxes/fees) = {q.final_premium:,.0f}")
        return q
    finally:
        if own:
            conn.close()


# --------------------------------------------------------------------------- #
# Personal Accident / Group Personal Accident
# --------------------------------------------------------------------------- #
def quote_pa_gpa(
    risk_class: str,
    death_benefit: float,
    *,
    group: bool = False,
    benefits: tuple[str, ...] = ("death", "tpd"),  # death, tpd, ttd, medical, funeral
    student: bool = False,
    period_months: float | None = None,
    conn=None,
) -> Quote:
    """PA/GPA. death=TPD=base rate; TTD=15%; medical & funeral = 10x death rate."""
    own = conn is None
    conn = conn or connect()
    try:
        product = "gpa" if group else "pa"
        q = Quote(product=product, sum_insured=death_benefit)
        base, _ = get_rate("pa_gpa", risk_class, conn=conn)
        q.add(f"PA/GPA base rate '{risk_class}': {base}%")

        total = 0.0
        for b in benefits:
            if b in ("death", "tpd"):
                p = premium_from_rate(death_benefit, base)
                q.add(f"  {b}: {death_benefit:,.0f} x {round(base, 6):g}% = {p:,.0f}")
            elif b == "ttd":
                p = premium_from_rate(death_benefit, base * 0.15)
                q.add(f"  ttd: {death_benefit:,.0f} x {round(base * 0.15, 6):g}% "
                      f"(15% of base) = {p:,.0f}")
            elif b in ("medical", "funeral"):
                p = premium_from_rate(death_benefit, base * 10)
                q.add(f"  {b}: {death_benefit:,.0f} x {round(base * 10, 6):g}% "
                      f"(10x death) = {p:,.0f}")
            else:
                continue
            total += p
        q.add(f"Total of selected benefits = {total:,.0f}")

        q.rate = base
        q.gross_premium = total
        q.net_premium = total
        frac = short_period_fraction(period_months, schedule="short_period_school", conn=conn)
        if frac < 1.0:
            q.net_premium *= frac
            q.add(f"Short-period factor = {frac:.4f}")

        if student:
            minimum = product_rule(product, "min_premium_student",
                                   15_000 if not group else 30_000, conn=conn)
        else:
            minimum = product_rule(product, "min_premium", 25_000 if not group else 50_000, conn=conn)
        q.final_premium = apply_minimum(q.net_premium, minimum, q)
        q.add(f"FINAL premium (net of taxes/fees) = {q.final_premium:,.0f}")
        return q
    finally:
        if own:
            conn.close()


# --------------------------------------------------------------------------- #
# Bonds / Guarantees (no short period; full rate always)
# --------------------------------------------------------------------------- #
def quote_bond(
    bond_type: str,
    bond_value: float,
    *,
    cash_collateral_100: bool = False,
    conn=None,
) -> Quote:
    own = conn is None
    conn = conn or connect()
    try:
        q = Quote(product="bond", sum_insured=bond_value)
        rate, _ = get_rate("bond", bond_type, conn=conn)
        if cash_collateral_100:
            cc = product_rule("bond", "cash_collateral_rate", 3.0, conn=conn)
            q.add(f"Standard rate {rate}% reduced to {cc}% (100% cash collateral)")
            rate = cc
        else:
            q.add(f"Bond rate '{bond_type}': {rate}%")
        q.rate = rate
        q.gross_premium = premium_from_rate(bond_value, rate)
        q.net_premium = q.gross_premium

        if bond_type == "bid_bond":
            minimum = product_rule("bond", "min_premium_bid", 10_000, conn=conn)
        else:
            minimum = product_rule("bond", "min_premium_other", 30_000, conn=conn)
        q.final_premium = apply_minimum(q.net_premium, minimum, q)
        q.warn("Bonds carry full rate for any period; no short-period or pro-rata.")
        q.add(f"FINAL premium (net of taxes/fees) = {q.final_premium:,.0f}")
        return q
    finally:
        if own:
            conn.close()


# --------------------------------------------------------------------------- #
# PVT — Political Violence & Terrorism (PER MILLE rates!)
# --------------------------------------------------------------------------- #
def quote_pvt(
    risk_type: str,
    sum_insured: float,
    *,
    security_features_discount: float = 0.0,   # up to 10% for CCTV/scan
    conn=None,
) -> Quote:
    own = conn is None
    conn = conn or connect()
    try:
        q = Quote(product="pvt", sum_insured=sum_insured, rate_unit="per_mille")
        rate, unit = get_rate("pvt", risk_type, conn=conn)   # unit == 'per_mille'
        q.rate = rate
        q.add(f"PVT rate '{risk_type}': {rate} per mille  (NB: per mille, not percent)")
        q.gross_premium = premium_from_rate(sum_insured, rate, unit=unit)

        net = q.gross_premium
        if security_features_discount:
            d = min(security_features_discount, 10.0)
            net *= (1 - d / 100.0)
            q.add(f"Security features discount = -{d}% (max 10%)")
        q.net_premium = net
        q.final_premium = net

        # Mandatory deductible: 5% e.e.l, min 0.5% of SI, floor Rwf50,000
        ded = max(sum_insured * 0.5 / 100.0, 50_000)
        q.excess = f"5% each loss, min 0.5% of SI ({ded:,.0f})"
        q.warn("Do not retain more than 5% of gross capacity/share capital without reinsurance.")
        q.add(f"FINAL premium (net of taxes/fees) = {q.final_premium:,.0f}")
        return q
    finally:
        if own:
            conn.close()


# --------------------------------------------------------------------------- #
# Engineering — CAR / EAR with duration loading and TPL handling
# --------------------------------------------------------------------------- #
def quote_car_ear(
    kind: str,                       # 'car' | 'ear'
    project_type: str,
    contract_value: float,
    *,
    duration_months: int = 12,
    tpl_limit: float = 0.0,
    conn=None,
) -> Quote:
    own = conn is None
    conn = conn or connect()
    try:
        q = Quote(product=kind, sum_insured=contract_value)
        rate, _ = get_rate("ear_car", project_type, conn=conn)
        q.add(f"{kind.upper()} base rate '{project_type}': {rate}%")

        # Duration loading: +25% for each extra 6 months beyond first 12
        if duration_months > 12:
            extra = duration_months - 12
            blocks = -(-extra // 6)  # ceil division
            load = blocks * 25.0
            rate *= (1 + load / 100.0)
            q.add(f"Duration {duration_months}m -> +{load}% ({blocks}x6mo blocks) => {rate:.4f}%")

        q.rate = rate
        works_premium = premium_from_rate(contract_value, rate)
        q.gross_premium = works_premium
        q.add(f"Contract works premium = {works_premium:,.0f}")

        # TPL: included if <=15% of project value, else rated separately at 0.2%
        cap_pct = product_rule(kind, "tpl_pct_cap", 15.0, conn=conn)
        if tpl_limit > 0:
            if tpl_limit <= contract_value * cap_pct / 100.0:
                q.add(f"TPL limit {tpl_limit:,.0f} within {cap_pct}% of value -> included in works")
            else:
                from .. import seed
                tpl_rate = seed.EAR_CAR_TPL_SEPARATE
                tpl_premium = premium_from_rate(tpl_limit, tpl_rate)
                q.gross_premium += tpl_premium
                q.add(f"TPL limit exceeds {cap_pct}% -> rated separately at {tpl_rate}% "
                      f"= {tpl_premium:,.0f}")

        q.net_premium = q.gross_premium
        fee = policy_fee(conn=conn)
        q.policy_fee = fee
        q.final_premium = q.net_premium + fee
        q.excess = ("Acts of God: 10% min 0.25% SI; other: 10% min 0.125% SI; "
                    "TPL: 5% min Rwf500,000")
        q.add(f"Policy fee = {fee:,.0f}; FINAL = {q.final_premium:,.0f}")
        return q
    finally:
        if own:
            conn.close()


def quote_machinery(
    machine_type: str,
    sum_insured: float,
    *,
    period_months: float | None = None,
    conn=None,
) -> Quote:
    own = conn is None
    conn = conn or connect()
    try:
        q = Quote(product="machinery", sum_insured=sum_insured)
        rate, _ = get_rate("machinery", machine_type, conn=conn)
        q.rate = rate
        q.add(f"Machinery breakdown rate '{machine_type}': {rate}%")
        q.gross_premium = premium_from_rate(sum_insured, rate)
        q.net_premium = q.gross_premium
        fee = policy_fee(conn=conn)
        q.policy_fee = fee
        q.final_premium = q.net_premium + fee
        threshold = product_rule("machinery", "large_si_threshold", 5_000_000, conn=conn)
        if sum_insured > threshold:
            q.excess = "10% each loss, min Rwf500,000 (SI above 5,000,000)"
        else:
            q.excess = "5% each loss, min Rwf250,000 (SI 5,000,000 or less)"
        q.add(f"Policy fee = {fee:,.0f}; FINAL = {q.final_premium:,.0f}")
        return q
    finally:
        if own:
            conn.close()


def quote_cpm(
    plant_group: str,                # '1' cranes | '2' mobile | '3' non-mobile
    hazard_class: str,               # 'A' | 'B' | 'C'
    sum_insured: float,
    *,
    period_months: float | None = None,
    conn=None,
) -> Quote:
    own = conn is None
    conn = conn or connect()
    try:
        q = Quote(product="cpm", sum_insured=sum_insured)
        rate, _ = get_rate("cpm", f"{hazard_class}/{plant_group}", conn=conn)
        q.rate = rate
        q.add(f"CPM rate (class {hazard_class}, group {plant_group}): {rate}%")
        q.gross_premium = premium_from_rate(sum_insured, rate)
        q.net_premium = q.gross_premium
        frac = short_period_fraction(period_months, schedule="short_period_cpm", conn=conn)
        if frac < 1.0:
            q.net_premium *= frac
            q.add(f"CPM short-period factor = {frac:.4f}")
        fee = policy_fee(conn=conn)
        q.policy_fee = fee
        q.final_premium = q.net_premium + fee
        q.excess = "10% of claim, min Rwf500,000"
        q.add(f"Policy fee = {fee:,.0f}; FINAL = {q.final_premium:,.0f}")
        return q
    finally:
        if own:
            conn.close()


def _excess_note(product, conn, default_pct, default_min):
    ep = product_rule(product, "excess_pct", default_pct, conn=conn)
    em = product_rule(product, "excess_min", default_min, conn=conn)
    return ep, em


# --------------------------------------------------------------------------- #
# Fidelity Guarantee
# --------------------------------------------------------------------------- #
def quote_fidelity(
    risk: str,
    sum_insured: float,
    *,
    blanket: bool = False,
    employees: int = 0,
    period_months: float | None = None,
    conn=None,
) -> Quote:
    own = conn is None
    conn = conn or connect()
    try:
        q = Quote(product="fidelity", sum_insured=sum_insured)
        rate, _ = get_rate("fidelity", risk, conn=conn)
        q.rate = rate
        if blanket:
            per_capita = product_rule("fidelity", "blanket_per_capita", 30_000, conn=conn)
            q.gross_premium = per_capita * max(int(employees), 0)
            q.add(f"Blanket cover: Rwf{per_capita:,.0f} per capita x {int(employees)} "
                  f"= {q.gross_premium:,.0f}")
        else:
            q.add(f"Fidelity rate '{risk}': {rate}% on {sum_insured:,.0f}")
            q.gross_premium = premium_from_rate(sum_insured, rate)
        q.net_premium = q.gross_premium * short_period_fraction(period_months, conn=conn)
        minimum = product_rule("fidelity", "min_premium", 200_000, conn=conn)
        q.final_premium = apply_minimum(q.net_premium, minimum, q)
        ep, em = _excess_note("fidelity", conn, 10.0, 250_000)
        q.excess = f"Rwf{em:,.0f} or {ep}% of adjusted claim, whichever is higher"
        q.add(f"FINAL premium (net of taxes/fees) = {q.final_premium:,.0f}")
        return q
    finally:
        if own:
            conn.close()


# --------------------------------------------------------------------------- #
# Bankers Blanket Bond  /  Directors & Officers Liability
# --------------------------------------------------------------------------- #
def quote_bbb(limit_of_indemnity: float, *, conn=None) -> Quote:
    own = conn is None
    conn = conn or connect()
    try:
        q = Quote(product="bbb", sum_insured=limit_of_indemnity)
        rate, _ = get_rate("bbb", "financial_services", conn=conn)
        q.rate = rate
        q.add(f"Bankers Blanket Bond rate (financial services): {rate}% of selected limit")
        q.gross_premium = premium_from_rate(limit_of_indemnity, rate)
        q.net_premium = q.final_premium = q.gross_premium
        ep, em = _excess_note("bbb", conn, 10.0, 250_000)
        q.excess = f"Rwf{em:,.0f} or {ep}% of adjusted claim, whichever is higher"
        q.add(f"FINAL premium (net of taxes/fees) = {q.final_premium:,.0f}")
        return q
    finally:
        if own:
            conn.close()


def quote_do_liability(
    limit_of_indemnity: float,
    *,
    risk: str = "financial_services",   # financial_services | other_offices
    conn=None,
) -> Quote:
    own = conn is None
    conn = conn or connect()
    try:
        q = Quote(product="do_liability", sum_insured=limit_of_indemnity)
        rate, _ = get_rate("do_liability", risk, conn=conn)
        q.rate = rate
        q.add(f"Directors & Officers rate '{risk}': {rate}% of selected limit")
        q.gross_premium = premium_from_rate(limit_of_indemnity, rate)
        q.net_premium = q.final_premium = q.gross_premium
        ep, em = _excess_note("do_liability", conn, 10.0, 250_000)
        q.excess = f"Rwf{em:,.0f} or {ep}% of adjusted claim, whichever is higher"
        q.add(f"FINAL premium (net of taxes/fees) = {q.final_premium:,.0f}")
        return q
    finally:
        if own:
            conn.close()


# --------------------------------------------------------------------------- #
# School Liability — flat premium per student (annual, incl. fees & VAT)
# --------------------------------------------------------------------------- #
def quote_school_liability(
    school_category: str,
    num_students: int,
    *,
    period_months: float | None = None,
    conn=None,
) -> Quote:
    own = conn is None
    conn = conn or connect()
    try:
        q = Quote(product="school_liability", rate_unit="amount")
        per_student, _ = get_rate("school_liability", school_category, conn=conn)
        n = max(int(num_students), 0)
        q.rate = per_student
        gross = per_student * n
        q.add(f"School liability '{school_category}': Rwf{per_student:,.0f}/student "
              f"x {n} students = {gross:,.0f}")
        q.gross_premium = gross
        q.net_premium = gross * short_period_fraction(
            period_months, schedule="short_period_school", conn=conn)
        q.final_premium = q.net_premium
        q.add("Premiums are annual and inclusive of policy fees and VAT.")
        q.add(f"FINAL premium = {q.final_premium:,.0f}")
        return q
    finally:
        if own:
            conn.close()


# --------------------------------------------------------------------------- #
# Aviation
# --------------------------------------------------------------------------- #
def quote_aviation(
    risk_class: str,
    sum_insured: float,
    *,
    seats: int = 1,
    conn=None,
) -> Quote:
    own = conn is None
    conn = conn or connect()
    try:
        q = Quote(product="aviation", sum_insured=sum_insured)
        rate, _ = get_rate("aviation", risk_class, conn=conn)
        q.rate = rate
        prem = premium_from_rate(sum_insured, rate)
        if "pax" in risk_class:
            prem *= max(int(seats), 1)
            q.add(f"PAX liability: {rate}% of per-seat limit x {int(seats)} seats")
        else:
            q.add(f"Aviation '{risk_class}': {rate}% on {sum_insured:,.0f}")
        q.gross_premium = q.net_premium = prem
        fee = policy_fee(conn=conn)
        q.policy_fee = fee
        q.final_premium = q.net_premium + fee
        q.add(f"Policy fee = {fee:,.0f}; FINAL = {q.final_premium:,.0f}")
        return q
    finally:
        if own:
            conn.close()


# --------------------------------------------------------------------------- #
# Marine Hull  /  Boilers  /  Computer (EEAR)  /  Plate Glass
# --------------------------------------------------------------------------- #
def quote_marine_hull(vessel_value: float, *, cover: str = "hull", conn=None) -> Quote:
    own = conn is None
    conn = conn or connect()
    try:
        cat = "third_party_liability" if cover in ("tpl", "liability", "third_party") \
            else "hull_all_risks"
        q = Quote(product="marine_hull", sum_insured=vessel_value)
        rate, _ = get_rate("marine_hull", cat, conn=conn)
        q.rate = rate
        q.add(f"Marine hull '{cat}': {rate}% on {vessel_value:,.0f}")
        q.gross_premium = q.net_premium = premium_from_rate(vessel_value, rate)
        fee = policy_fee(conn=conn)
        q.policy_fee = fee
        q.final_premium = q.net_premium + fee
        q.add(f"Policy fee = {fee:,.0f}; FINAL = {q.final_premium:,.0f}")
        return q
    finally:
        if own:
            conn.close()


def quote_boiler(sum_insured: float, *, cover: str = "material_damage", conn=None) -> Quote:
    own = conn is None
    conn = conn or connect()
    try:
        cat = "third_party_liability" if cover in ("tpl", "liability", "third_party") \
            else "material_damage"
        q = Quote(product="boiler", sum_insured=sum_insured)
        rate, _ = get_rate("boiler", cat, conn=conn)
        q.rate = rate
        q.add(f"Boiler & pressure vessel '{cat}': {rate}% on {sum_insured:,.0f}")
        q.gross_premium = q.net_premium = premium_from_rate(sum_insured, rate)
        fee = policy_fee(conn=conn)
        q.policy_fee = fee
        q.final_premium = q.net_premium + fee
        ep, em = _excess_note("boiler", conn, 10.0, 625_000)
        q.excess = f"{ep}% of claim, min Rwf{em:,.0f}"
        q.add(f"Policy fee = {fee:,.0f}; FINAL = {q.final_premium:,.0f}")
        return q
    finally:
        if own:
            conn.close()


_EEAR_CAT = {
    "premises": "equipment_at_premises", "portable": "portable_away_premises",
    "unspecified": "unspecified_tender", "increased_cost": "increased_cost_of_working",
    "icow": "increased_cost_of_working",
}


def quote_eear(sum_insured: float, *, location: str = "premises", conn=None) -> Quote:
    own = conn is None
    conn = conn or connect()
    try:
        cat = _EEAR_CAT.get(location, "equipment_at_premises")
        q = Quote(product="eear", sum_insured=sum_insured)
        rate, _ = get_rate("eear", cat, conn=conn)
        q.rate = rate
        q.add(f"Computer/EEAR '{cat}': {rate}% on {sum_insured:,.0f}")
        q.gross_premium = q.net_premium = premium_from_rate(sum_insured, rate)
        fee = policy_fee(conn=conn)
        q.policy_fee = fee
        q.final_premium = q.net_premium + fee
        ep, em = _excess_note("eear", conn, 10.0, 100_000)
        q.excess = f"{ep}% of claim, min Rwf{em:,.0f}"
        q.add(f"Policy fee = {fee:,.0f}; FINAL = {q.final_premium:,.0f}")
        return q
    finally:
        if own:
            conn.close()


def quote_plate_glass(sum_insured: float, *, conn=None) -> Quote:
    own = conn is None
    conn = conn or connect()
    try:
        q = Quote(product="plate_glass", sum_insured=sum_insured)
        rate, _ = get_rate("plate_glass", "standard", conn=conn)
        q.rate = rate
        q.add(f"Plate glass rate: {rate}% on {sum_insured:,.0f}")
        q.gross_premium = q.net_premium = premium_from_rate(sum_insured, rate)
        fee = policy_fee(conn=conn)
        q.policy_fee = fee
        q.final_premium = q.net_premium + fee
        ep, em = _excess_note("plate_glass", conn, 5.0, 100_000)
        q.excess = f"{ep}% each loss, min Rwf{em:,.0f}"
        q.add(f"Policy fee = {fee:,.0f}; FINAL = {q.final_premium:,.0f}")
        return q
    finally:
        if own:
            conn.close()
