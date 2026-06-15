"""Build the ASSAR rate database. Run:  python -m assar.build_db"""
from __future__ import annotations

from . import seed
from .db import DB_PATH, connect, init_schema


def _ins_rate(conn, scheme, rows, two_col=False, unit="percent"):
    for row in rows:
        if two_col:
            cat, r, ralt = row
            conn.execute(
                "INSERT INTO rate(scheme,category,rate,rate_alt,unit) VALUES(?,?,?,?,?)",
                (scheme, cat, r, ralt, unit),
            )
        else:
            cat, r = row
            conn.execute(
                "INSERT INTO rate(scheme,category,rate,unit) VALUES(?,?,?,?)",
                (scheme, cat, r, unit),
            )


def _ins_noted(conn, scheme, rows, unit="percent"):
    """rows: (category, rate, rate_alt, note)."""
    for cat, r, ralt, note in rows:
        conn.execute(
            "INSERT INTO rate(scheme,category,rate,rate_alt,unit,note) VALUES(?,?,?,?,?,?)",
            (scheme, cat, r, ralt, unit, note),
        )


def _ins_amount(conn, scheme, rows):
    """rows: (category, amount, note) -> stored with unit='amount'."""
    for cat, amt, note in rows:
        conn.execute(
            "INSERT INTO rate(scheme,category,rate,unit,note) VALUES(?,?,?,?,?)",
            (scheme, cat, float(amt), "amount", note),
        )


def _ins_transit(conn, scheme, rows):
    for code, commodity, rac, ranc, arc, aranc, excess in rows:
        conn.execute(
            "INSERT INTO transit_rate(scheme,code,commodity,ra_containerized,"
            "ra_noncontainerized,ar_containerized,ar_noncontainerized,excess) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (scheme, code, commodity, rac, ranc, arc, aranc, excess),
        )


def _ins_schedule(conn, name, rows, kind):
    for i, row in enumerate(rows):
        if len(row) == 4:
            lower, upper, label, value = row
        elif len(row) == 3:
            upper, value, label = row
            lower = None
        else:
            (upper, value) = row
            lower, label = None, None
        conn.execute(
            "INSERT INTO schedule(name,lower,upper,label,value,kind,ord) "
            "VALUES(?,?,?,?,?,?,?)",
            (name, lower, upper, label, value, kind, i),
        )


def build(db_path=DB_PATH) -> None:
    conn = connect(db_path)
    init_schema(conn)

    # Special perils: rate=commercial/industrial, rate_alt=residential
    _ins_rate(conn, "special_perils", seed.SPECIAL_PERILS, two_col=True)
    # Fire: rate=standard fire, rate_alt=all special perils
    _ins_rate(conn, "fire", seed.FIRE, two_col=True)

    _ins_rate(conn, "public_liability", seed.PUBLIC_LIABILITY)
    _ins_rate(conn, "employers_liability", seed.EMPLOYERS_LIABILITY)
    _ins_rate(conn, "product_liability", seed.PRODUCT_LIABILITY)
    _ins_rate(conn, "professional_indemnity", seed.PROFESSIONAL_INDEMNITY)
    _ins_rate(conn, "pa_gpa", seed.PA_GPA)
    _ins_rate(conn, "bond", seed.BONDS)
    _ins_rate(conn, "fidelity", seed.FIDELITY)
    _ins_rate(conn, "bbb", seed.BBB)
    _ins_rate(conn, "do_liability", seed.DO_LIABILITY)
    _ins_rate(conn, "pvt", seed.PVT, unit="per_mille")        # <-- per mille!
    _ins_rate(conn, "ear_car", seed.EAR_CAR)
    _ins_rate(conn, "machinery", seed.MACHINERY)

    # CPM matrix -> category like "B/2"
    cpm_rows = [(f"{cls}/{grp}", rate) for (cls, grp), rate in seed.CPM.items()]
    _ins_rate(conn, "cpm", cpm_rows)

    # Additional tables completing manual coverage
    _ins_noted(conn, "money", seed.MONEY_RATES)
    _ins_noted(conn, "money_carryings", seed.MONEY_CARRYINGS)
    _ins_amount(conn, "school_liability", seed.SCHOOL_LIABILITY)
    _ins_noted(conn, "boiler", seed.BOILER_RATES)
    _ins_noted(conn, "eear", seed.EEAR_RATES)
    _ins_noted(conn, "aviation", seed.AVIATION_RATES)
    _ins_noted(conn, "marine_hull", seed.MARINE_HULL_RATES)
    _ins_amount(conn, "marine_hull_occupant", seed.MARINE_HULL_OCCUPANT)
    _ins_noted(conn, "plate_glass", seed.PLATE_GLASS_RATES)

    _ins_transit(conn, "git", seed.GIT)
    _ins_transit(conn, "marine_cargo", seed.MARINE_CARGO)

    _ins_schedule(conn, "voluntary_deductible", seed.VOLUNTARY_DEDUCTIBLE, "discount_pct")
    _ins_schedule(conn, "short_period_months", seed.SHORT_PERIOD_MONTHS, "fraction")
    _ins_schedule(conn, "short_period_days", seed.SHORT_PERIOD_DAYS, "fraction")
    _ins_schedule(conn, "short_period_school", seed.SHORT_PERIOD_SCHOOL, "fraction")
    _ins_schedule(conn, "short_period_cpm", seed.SHORT_PERIOD_CPM, "fraction")
    _ins_schedule(conn, "ci_indemnity", seed.CI_INDEMNITY, "multiplier_pct")
    _ins_schedule(conn, "ci_time_excess", seed.CI_VOLUNTARY_TIME_EXCESS, "discount_pct")
    _ins_schedule(conn, "first_loss", seed.FIRST_LOSS, "multiplier_pct")

    # Product rules
    for product, rules in seed.PRODUCT_RULES.items():
        for key, value in rules.items():
            conn.execute(
                "INSERT INTO product_rule(product,key,value) VALUES(?,?,?)",
                (product, key, float(value)),
            )

    conn.commit()

    # Report
    counts = {
        t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        for t in ("rate", "transit_rate", "schedule", "product_rule")
    }
    conn.close()
    print(f"Built {db_path}")
    for t, n in counts.items():
        print(f"  {t:14s}: {n} rows")


if __name__ == "__main__":
    build()
