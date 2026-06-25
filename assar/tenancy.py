"""Multi-insurer tenancy: identity and the scoped data-access layer.

The platform serves several insurers over the one shared ASSAR schedule. Each
insurer may keep private rate overrides (see the rate_override table in db.py)
that overlay the base rates for their pricing only.

The authenticated insurer is held in a context variable, NOT taken from user
input, so a chat message can never choose whose data is read. The pricing layer
(assar.pricing.base.get_rate) reads current_insurer() and applies that insurer's
overlay; an insurer can therefore only ever see the base rates plus their own
overrides. This is the server-side boundary that an MCP tool or HTTP endpoint
would set from the caller's auth token.
"""
from __future__ import annotations

import contextvars

from .db import connect

# The current insurer for this execution context. None = the shared ASSAR base,
# no overrides. Set it from authenticated context (a session/token), never from
# the model's output or the user's message text.
_CURRENT_INSURER: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "current_insurer_id", default=None
)


def current_insurer() -> int | None:
    return _CURRENT_INSURER.get()


def set_current_insurer(insurer_id: int | None) -> None:
    _CURRENT_INSURER.set(insurer_id)


class using_insurer:
    """Bind the acting insurer for a block, then restore the previous value.

        with using_insurer(radiant_id):
            quote_fire("hotels", 10_000_000)   # priced under Radiant's overrides
    """

    def __init__(self, insurer_id: int | None):
        self.insurer_id = insurer_id
        self._token = None

    def __enter__(self):
        self._token = _CURRENT_INSURER.set(self.insurer_id)
        return self

    def __exit__(self, *exc):
        _CURRENT_INSURER.reset(self._token)
        return False


# --------------------------------------------------------------------------- #
# Read helpers (all scoped; an insurer_id is required to see overrides)
# --------------------------------------------------------------------------- #
def list_insurers(conn=None) -> list[dict]:
    own = conn is None
    conn = conn or connect()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT id, slug, name FROM insurer ORDER BY name")]
    finally:
        if own:
            conn.close()


def get_insurer(slug: str, conn=None) -> dict | None:
    own = conn is None
    conn = conn or connect()
    try:
        r = conn.execute(
            "SELECT id, slug, name FROM insurer WHERE slug=?", (slug,)).fetchone()
        return dict(r) if r else None
    finally:
        if own:
            conn.close()


def list_overrides(insurer_id: int, conn=None) -> list[dict]:
    """The overrides belonging to ONE insurer. Always filtered by insurer_id, so
    a caller can never enumerate another insurer's overrides."""
    own = conn is None
    conn = conn or connect()
    try:
        return [dict(r) for r in conn.execute(
            "SELECT scheme, category, rate, rate_alt, unit, note FROM rate_override "
            "WHERE insurer_id=? ORDER BY scheme, category", (insurer_id,))]
    finally:
        if own:
            conn.close()
