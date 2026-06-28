"""Client for the CoverSoko Underwriter API (the production pricing backend).

CoverSoko (TypeScript/Express/Postgres) exposes POST /api/quote, which evaluates
underwriting rules against submitted risk attributes and returns a premium. This
module is the thin Python wrapper our assistant calls as a typed tool: the LLM
fills parameters, this client runs the HTTP request, and CoverSoko owns the data
and the per-insurer tariff overrides (its `ownerId`). The model never builds a
query or chooses the tenant.

Contract (from the CoverSoko source):
  POST /api/quote
    { perilType, sumInsured, coverType, attributes{propertyType, propertyCategory, ...},
      specialPerilNames?, includeAllSpecialPerils?, ownerId? }
  -> { success, message, data: { baseRate, specialPerilsRate, totalRate, premium,
                                 breakdown: [{label, rate}] } }
  Rates are fractions (premium = sumInsured * totalRate); we display them as %.

Config (env):
  COVERSOKO_API_URL   base URL, e.g. http://localhost:3500 (unset = integration off)
  COVERSOKO_OWNER_ID  insurer UUID for tariff overrides (the tenant; server-side)
  COVERSOKO_API_KEY   optional bearer token
  COVERSOKO_TIMEOUT   seconds (default 15)
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


def base_url() -> str:
    return os.getenv("COVERSOKO_API_URL", "").rstrip("/")


def enabled() -> bool:
    """True when a CoverSoko backend URL is configured."""
    return bool(base_url())


def _timeout() -> float:
    try:
        return float(os.getenv("COVERSOKO_TIMEOUT", "15"))
    except ValueError:
        return 15.0


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    key = os.getenv("COVERSOKO_API_KEY")
    if key:
        h["Authorization"] = f"Bearer {key}"
    return h


def _request(method: str, path: str, payload: dict | None = None) -> dict:
    url = base_url() + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=_headers())
    with urllib.request.urlopen(req, timeout=_timeout()) as resp:  # noqa: S310 (trusted base URL)
        return json.loads(resp.read().decode() or "{}")


def available() -> bool:
    """Cheap reachability check (best-effort, short timeout)."""
    if not enabled():
        return False
    try:
        req = urllib.request.Request(base_url() + "/api/perils", method="GET", headers=_headers())
        with urllib.request.urlopen(req, timeout=min(_timeout(), 4)):  # noqa: S310
            return True
    except Exception:
        return False


def _pct(fraction) -> float:
    """CoverSoko stores rates as fractions; show them as percent of sum insured."""
    return round(float(fraction or 0) * 100.0, 6)


def _normalize(data: dict, peril_type: str, sum_insured: float, cover_type: str) -> dict:
    """Map a CoverSoko QuoteResult into the same shape our quote renderer/trace use
    (so render_quote_card and the grounding guard work unchanged)."""
    premium = round(float(data.get("premium", 0)), 2)
    total = _pct(data.get("totalRate"))
    lines = [
        f"Base rate: {_pct(data.get('baseRate')):g}%",
        f"Special perils rate: {_pct(data.get('specialPerilsRate')):g}%",
    ]
    for b in data.get("breakdown", []):
        lines.append(f"{b.get('label')}: {_pct(b.get('rate')):g}%")
    lines.append(f"Total rate {total:g}% x sum insured {float(sum_insured):,.0f} = {premium:,.0f}")
    return {
        "product": f"{peril_type} ({cover_type})",
        "sum_insured": sum_insured,
        "rate": total,
        "rate_unit": "percent",
        "gross_premium": premium,
        "net_premium": premium,
        "final_premium": premium,
        "policy_fee": 0,
        "breakdown": lines,
        "warnings": ["Priced by the CoverSoko underwriting engine."],
        "source": "coversoko",
        "raw": data,
    }


def quote(
    peril_type: str,
    sum_insured: float,
    cover_type: str,
    attributes: dict,
    *,
    special_peril_names: list[str] | None = None,
    include_all_special_perils: bool = False,
    owner_id: str | None = None,
) -> dict:
    """Call CoverSoko POST /api/quote and return a normalized quote dict, or
    {"error": ...} on any failure (so the router surfaces it like any tool error).

    owner_id (the tenant) defaults to COVERSOKO_OWNER_ID and is NEVER taken from
    the model: the acting insurer is server/config controlled, not user-chosen.
    """
    if not enabled():
        return {"error": "CoverSoko backend not configured (set COVERSOKO_API_URL)."}

    payload: dict = {
        "perilType": peril_type,
        "sumInsured": sum_insured,
        "coverType": cover_type,
        "attributes": attributes or {},
    }
    if special_peril_names:
        payload["specialPerilNames"] = special_peril_names
    if include_all_special_perils:
        payload["includeAllSpecialPerils"] = True
    oid = owner_id or os.getenv("COVERSOKO_OWNER_ID")
    if oid:
        payload["ownerId"] = oid

    try:
        resp = _request("POST", "/api/quote", payload)
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode()).get("message", str(e))
        except Exception:
            msg = str(e)
        return {"error": f"CoverSoko {e.code}: {msg}"}
    except Exception as e:  # noqa: BLE001 (connection refused, timeout, DNS, ...)
        return {"error": f"CoverSoko unreachable at {base_url() or '(unset)'}: {e}"}

    if not resp.get("success"):
        return {"error": resp.get("message", "CoverSoko quote failed")}
    return _normalize(resp.get("data", {}), peril_type, sum_insured, cover_type)


def _demo():
    """python -m assar.integrations.coversoko -> one quote against the configured API."""
    print(f"CoverSoko URL: {base_url() or '(unset; set COVERSOKO_API_URL)'}")
    print(f"reachable: {available()}")
    res = quote(
        "Fire_Allied_Perils", 10_000_000, "standardFireRate",
        {"propertyType": "commercial", "propertyCategory": "Banks"},
        special_peril_names=["Earthquake", "Riot & Strike"],
    )
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    _demo()
