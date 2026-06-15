"""Tests for the ASSAR pricing engine. Expected values are hand-computed from the
manual so a regression in the rates or the composition logic is caught immediately.

Run:  pytest -q
"""
import math

import pytest

from assar.pricing.base import (
    get_rate, premium_from_rate, short_period_fraction, voluntary_deductible_discount,
    RateNotFound,
)
from assar.pricing.fire import quote_burglary, quote_consequential_loss, quote_fire
from assar.pricing.products import (
    quote_bond, quote_car_ear, quote_cpm, quote_liability, quote_machinery,
    quote_pa_gpa, quote_pvt,
)
from assar.pricing.transit import quote_git, quote_marine_cargo
from assar.pricing.registry import run_tool


def approx(a, b, tol=0.01):
    return math.isclose(a, b, abs_tol=tol)


# --------------------------------------------------------------------------- #
# Lookups
# --------------------------------------------------------------------------- #
def test_fire_rate_lookup():
    rate, unit = get_rate("fire", "banks")           # standard fire
    assert rate == 0.125 and unit == "percent"
    alt, _ = get_rate("fire", "banks", alt=True)     # all special perils
    assert alt == 0.2000


def test_pvt_is_per_mille():
    rate, unit = get_rate("pvt", "hotels_banks")
    assert rate == 1.50 and unit == "per_mille"


def test_missing_rate_raises():
    with pytest.raises(RateNotFound):
        get_rate("fire", "does_not_exist")


def test_premium_unit_conversion():
    assert approx(premium_from_rate(1_000_000, 0.15, "percent"), 1_500)
    assert approx(premium_from_rate(1_000_000, 1.50, "per_mille"), 1_500)


# --------------------------------------------------------------------------- #
# Fire
# --------------------------------------------------------------------------- #
def test_fire_basic_all_perils():
    # Hotel, SI 100,000,000, all special perils -> 0.2200%
    q = quote_fire("hotels", 100_000_000, special_perils=True)
    assert approx(q.gross_premium, 100_000_000 * 0.2200 / 100)   # 220,000
    assert approx(q.final_premium, 220_000 + 5_000)              # + policy fee


def test_fire_standard_only():
    q = quote_fire("offices", 50_000_000, special_perils=False)  # 0.125%
    assert approx(q.gross_premium, 62_500)


def test_fire_fea_discount_on_fire_portion_only():
    # FEA 15% applies to fire portion; with industrial loading the loading is NOT discounted
    q = quote_fire("tanneries", 200_000_000, special_perils=False,
                   industrial=True, fea_available=True)
    fire_portion = 200_000_000 * 0.150 / 100        # 300,000
    process = 200_000_000 * 0.025 / 100             # 50,000
    ext = 25_000
    gross = fire_portion + process + ext
    net = gross - fire_portion * 0.15               # FEA on fire portion only
    assert approx(q.gross_premium, gross)
    assert approx(q.net_premium, net)


def test_fire_voluntary_deductible_capped():
    # Saving is capped at 33.33% of the excess amount.
    # Use 200,000 -> unambiguously in the "up to 250,000" = 5.0% band.
    pct, saving = voluntary_deductible_discount(200_000, gross_premium=10_000_000)
    assert pct == 5.0
    # 5% of 10m = 500,000, but cap = 33.33% of 200,000 = 66,660 -> capped
    assert approx(saving, 200_000 * 33.33 / 100)


def test_voluntary_deductible_boundary_goes_to_higher_band():
    # MANUAL AMBIGUITY: bands overlap at the edges ("up to 250,000" then
    # "250,000 up to 500,000"). The engine resolves the exact boundary to the
    # higher band (the one whose lower bound equals the value). Documented here
    # so the behaviour is intentional, not accidental. Confirm with ASSAR.
    pct, _ = voluntary_deductible_discount(250_000, gross_premium=10_000_000)
    assert pct == 7.5


# --------------------------------------------------------------------------- #
# Short period
# --------------------------------------------------------------------------- #
def test_short_period_months():
    assert short_period_fraction(3) == 0.5
    assert short_period_fraction(6) == 0.75
    assert short_period_fraction(12) == 1.0
    assert short_period_fraction(None) == 1.0


def test_short_period_days():
    assert approx(short_period_fraction(None, period_days=1), 1/24)
    assert approx(short_period_fraction(None, period_days=7), 1/8)


# --------------------------------------------------------------------------- #
# Transit
# --------------------------------------------------------------------------- #
def test_git_all_risks_containerized():
    # Pharmaceuticals all-risks containerized -> 0.5850%
    q = quote_git("pharmaceuticals", 10_000_000, cover="all_risks", containerized=True)
    assert approx(q.rate, 0.5850)
    assert approx(q.gross_premium, 10_000_000 * 0.5850 / 100)   # 58,500


def test_transporters_liability_outside_rwanda_load():
    base = quote_git("semi_fragile", 10_000_000).rate
    loaded = quote_git("semi_fragile", 10_000_000, transporters_liability=True,
                       outside_rwanda=True).rate
    assert approx(loaded, base * 1.30)


def test_marine_cargo_mode_and_clause_discount():
    # ICC-A pharmaceuticals containerized 0.650%, sea (-20%), clause B (-25%)
    q = quote_marine_cargo("pharmaceuticals", 10_000_000, mode="sea", clause="B")
    expected = 0.650 * 0.80 * 0.75
    assert approx(q.rate, expected)


def test_git_multi_trip_multiplier():
    q = quote_git("grains_in_bags", 5_000_000, trips_period_months=6)
    annual = quote_git("grains_in_bags", 5_000_000).gross_premium
    assert approx(q.net_premium, annual * 0.60)


# --------------------------------------------------------------------------- #
# Liability + minimum premiums
# --------------------------------------------------------------------------- #
def test_public_liability_rate():
    q = quote_liability("public", "manufacturing", 50_000_000)   # 0.80%
    assert approx(q.gross_premium, 400_000)


def test_liability_minimum_premium_floor():
    # Tiny LOI -> below Rwf100,000 floor
    q = quote_liability("public", "others", 1_000_000)           # 0.20% = 2,000
    assert q.final_premium == 100_000


def test_pi_agents_lower_minimum():
    q = quote_liability("professional", "insurance_agents", 100_000)  # 1.5% = 1,500
    assert q.final_premium == 25_000


# --------------------------------------------------------------------------- #
# PA / GPA
# --------------------------------------------------------------------------- #
def test_pa_death_and_tpd():
    # Drivers 0.500%, death + tpd both at base rate
    q = quote_pa_gpa("drivers_security_mining", 10_000_000, benefits=("death", "tpd"))
    assert approx(q.gross_premium, 2 * 10_000_000 * 0.500 / 100)   # 100,000


def test_pa_medical_is_10x():
    q = quote_pa_gpa("office_administration", 1_000_000, benefits=("medical",))
    assert approx(q.gross_premium, 1_000_000 * (0.185 * 10) / 100)  # 18,500


def test_gpa_student_minimum():
    q = quote_pa_gpa("student_internship", 1_000_000, group=True, student=True,
                     benefits=("death",))
    # 0.25% of 1m = 2,500 -> floored at GPA student min 30,000
    assert q.final_premium == 30_000


# --------------------------------------------------------------------------- #
# Bonds
# --------------------------------------------------------------------------- #
def test_bond_rate_and_min():
    q = quote_bond("performance_bond", 100_000_000)              # 5%
    assert approx(q.gross_premium, 5_000_000)


def test_bond_cash_collateral():
    q = quote_bond("performance_bond", 100_000_000, cash_collateral_100=True)
    assert approx(q.rate, 3.0)


def test_bid_bond_minimum():
    q = quote_bond("bid_bond", 100_000)                          # 2% = 2,000
    assert q.final_premium == 10_000


# --------------------------------------------------------------------------- #
# PVT — the per-mille trap
# --------------------------------------------------------------------------- #
def test_pvt_per_mille_math():
    # Hotels/Banks 1.50 per mille on SI 1,000,000,000 -> 1,500,000 (NOT 15,000,000)
    q = quote_pvt("hotels_banks", 1_000_000_000)
    assert approx(q.gross_premium, 1_000_000_000 * 1.50 / 1000)  # 1,500,000


def test_pvt_security_discount_capped():
    q = quote_pvt("apartments", 100_000_000, security_features_discount=25)
    base = quote_pvt("apartments", 100_000_000).gross_premium
    assert approx(q.final_premium, base * 0.90)   # discount capped at 10%


# --------------------------------------------------------------------------- #
# Engineering
# --------------------------------------------------------------------------- #
def test_car_duration_loading():
    # Residential 0.2%, 22 months -> +50% (2 blocks of 6 beyond 12)
    q = quote_car_ear("car", "residential_buildings", 100_000_000, duration_months=22)
    assert approx(q.rate, 0.2 * 1.50)


def test_car_tpl_separate_when_over_cap():
    q = quote_car_ear("car", "dams", 100_000_000, duration_months=12,
                      tpl_limit=50_000_000)   # 50% > 15% cap
    works = 100_000_000 * 0.5 / 100
    tpl = 50_000_000 * 0.2 / 100
    assert approx(q.gross_premium, works + tpl)


def test_machinery_excess_band():
    big = quote_machinery("transformers", 10_000_000)     # >5m
    small = quote_machinery("transformers", 1_000_000)    # <=5m
    assert "500,000" in big.excess and "250,000" in small.excess


def test_cpm_matrix():
    q = quote_cpm("2", "B", 20_000_000)   # class B, group 2 -> 1.10%
    assert approx(q.rate, 1.10)


# --------------------------------------------------------------------------- #
# Consequential loss
# --------------------------------------------------------------------------- #
def test_consequential_loss_gross_profit():
    # Banks fire MD 0.125%, gross profit 150% -> basis 0.1875%, 12m indemnity 150%
    q = quote_consequential_loss("banks", 40_000_000, indemnity_period_months=12,
                                 cover="gross_profit")
    basis = 0.125 * 1.5            # 0.1875
    eff = basis * 1.5             # 12m -> 150%
    assert approx(q.rate, eff)


# --------------------------------------------------------------------------- #
# LLM tool dispatch
# --------------------------------------------------------------------------- #
def test_run_tool_dispatch():
    out = run_tool("quote_fire", {"risk_category": "banks", "sum_insured": 10_000_000})
    assert "final_premium" in out and out["product"] == "fire"


def test_run_tool_unknown_category_returns_error():
    out = run_tool("quote_fire", {"risk_category": "nope", "sum_insured": 10_000_000})
    assert "error" in out
