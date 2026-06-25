"""Tenancy: per-insurer rate overrides overlay the shared base, scoped so an
insurer can only ever see the base plus its own overrides."""
from assar.pricing.base import get_rate
from assar.pricing.fire import quote_fire
from assar.tenancy import current_insurer, list_overrides, using_insurer

RADIANT, PRIME = 1, 2


def test_base_rate_when_no_insurer():
    # No insurer in context -> the shared ASSAR base rate.
    assert get_rate("fire", "hotels", alt=True) == (0.22, "percent")


def test_override_applied_per_insurer():
    with using_insurer(RADIANT):
        assert get_rate("fire", "hotels", alt=True)[0] == 0.18
    with using_insurer(PRIME):
        assert get_rate("fire", "hotels", alt=True)[0] == 0.28


def test_explicit_insurer_id_argument():
    # The same overlay is reachable explicitly (how an endpoint would pass auth).
    assert get_rate("fire", "hotels", alt=True, insurer_id=RADIANT)[0] == 0.18


def test_fallback_to_base_when_no_override():
    # Radiant has no override for 'banks' -> falls through to the base rate.
    with using_insurer(RADIANT):
        assert get_rate("fire", "banks", alt=True) == get_rate("fire", "banks", alt=True, insurer_id=None) == (0.2, "percent")


def test_quote_reflects_the_acting_insurer():
    base = quote_fire("hotels", 10_000_000).gross_premium
    with using_insurer(RADIANT):
        radiant = quote_fire("hotels", 10_000_000).gross_premium
    with using_insurer(PRIME):
        prime = quote_fire("hotels", 10_000_000).gross_premium
    assert round(base) == 22_000      # 10,000,000 x 0.22%
    assert round(radiant) == 18_000   # Radiant's negotiated 0.18%
    assert round(prime) == 28_000     # Prime's loaded 0.28%


def test_isolation_each_insurer_sees_only_its_own():
    radiant = {(o["scheme"], o["category"]) for o in list_overrides(RADIANT)}
    prime = {(o["scheme"], o["category"]) for o in list_overrides(PRIME)}
    assert ("fire", "offices") in radiant      # Radiant's own
    assert ("fire", "offices") not in prime    # not visible to Prime
    assert radiant.isdisjoint(prime - radiant)  # no leakage of the other's rows


def test_context_is_restored_after_block():
    assert current_insurer() is None
    with using_insurer(RADIANT):
        assert current_insurer() == RADIANT
    assert current_insurer() is None
