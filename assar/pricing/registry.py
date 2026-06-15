"""Central registry of pricing calculators and the JSON tool schemas the LLM uses.

Keeping a curated set of typed functions (instead of free-form text-to-SQL) means
the arithmetic is deterministic and unit-testable; the model only extracts
parameters and orchestrates.
"""
from __future__ import annotations

import re

from .base import list_categories
from .fire import quote_burglary, quote_consequential_loss, quote_fire
from .products import (
    quote_bond, quote_car_ear, quote_cpm, quote_liability, quote_machinery,
    quote_pa_gpa, quote_pvt,
)
from .transit import quote_git, quote_marine_cargo

CALCULATORS = {
    "fire": quote_fire,
    "consequential_loss": quote_consequential_loss,
    "burglary": quote_burglary,
    "git": quote_git,
    "marine_cargo": quote_marine_cargo,
    "liability": quote_liability,
    "pa_gpa": quote_pa_gpa,
    "bond": quote_bond,
    "pvt": quote_pvt,
    "car_ear": quote_car_ear,
    "machinery": quote_machinery,
    "cpm": quote_cpm,
}

# Tool schemas (OpenAI/Groq function-calling format). The LLM picks one and
# fills the args; we dispatch to CALCULATORS.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "quote_fire",
            "description": "Price Fire & Allied Perils material damage cover for a property risk.",
            "parameters": {
                "type": "object",
                "properties": {
                    "risk_category": {"type": "string", "description": "Occupancy key, e.g. 'banks', 'tanneries', 'hotels'."},
                    "sum_insured": {"type": "number"},
                    "special_perils": {"type": "boolean", "description": "Include all special perils (default true)."},
                    "industrial": {"type": "boolean"},
                    "fea_available": {"type": "boolean", "description": "Fire extinguishing appliances present."},
                    "voluntary_excess": {"type": "number"},
                    "period_months": {"type": "number"},
                },
                "required": ["risk_category", "sum_insured"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quote_liability",
            "description": "Price public/employers/product/professional liability on a limit of indemnity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["public", "employers", "product", "professional"]},
                    "occupation": {"type": "string"},
                    "limit_of_indemnity": {"type": "number"},
                    "period_months": {"type": "number"},
                },
                "required": ["kind", "occupation", "limit_of_indemnity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quote_git",
            "description": "Price Goods in Transit / Transporters Liability for a commodity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "commodity": {"type": "string"},
                    "consignment_value": {"type": "number"},
                    "cover": {"type": "string", "enum": ["all_risks", "road_accident"]},
                    "containerized": {"type": "boolean"},
                    "transporters_liability": {"type": "boolean"},
                    "outside_rwanda": {"type": "boolean"},
                    "trips_period_months": {"type": "integer"},
                },
                "required": ["commodity", "consignment_value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quote_pvt",
            "description": "Price Political Violence & Terrorism cover. Rates are per mille.",
            "parameters": {
                "type": "object",
                "properties": {
                    "risk_type": {"type": "string"},
                    "sum_insured": {"type": "number"},
                    "security_features_discount": {"type": "number"},
                },
                "required": ["risk_type", "sum_insured"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quote_bond",
            "description": "Price a bond/guarantee (performance, advance payment, bid, customs, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "bond_type": {"type": "string"},
                    "bond_value": {"type": "number"},
                    "cash_collateral_100": {"type": "boolean"},
                },
                "required": ["bond_type", "bond_value"],
            },
        },
    },
]

# Groq/Llama sometimes emit numeric args as JSON strings ("1000000"), which the
# provider then rejects against a strict {"type":"number"} schema (400
# tool_use_failed). Relax every numeric field to accept number OR string; we
# coerce back to a real number in run_tool().
for _t in TOOL_SCHEMAS:
    for _p in _t["function"]["parameters"]["properties"].values():
        if _p.get("type") in ("number", "integer"):
            _p["type"] = [_p["type"], "string"]


def _coerce_numbers(args: dict) -> dict:
    """Turn numeric-looking strings ('1,000,000', '12') into real numbers."""
    out = {}
    for k, v in args.items():
        if isinstance(v, str):
            s = v.strip().replace(",", "").replace("_", "")
            try:
                out[k] = int(s) if re.fullmatch(r"-?\d+", s) else float(s)
                continue
            except ValueError:
                pass
        out[k] = v
    return out


# name in schema -> python callable
DISPATCH = {
    "quote_fire": quote_fire,
    "quote_liability": quote_liability,
    "quote_git": quote_git,
    "quote_pvt": quote_pvt,
    "quote_bond": quote_bond,
    "quote_consequential_loss": quote_consequential_loss,
    "quote_burglary": quote_burglary,
    "quote_marine_cargo": quote_marine_cargo,
    "quote_pa_gpa": quote_pa_gpa,
    "quote_car_ear": quote_car_ear,
    "quote_machinery": quote_machinery,
    "quote_cpm": quote_cpm,
}


def run_tool(name: str, args: dict) -> dict:
    """Dispatch an LLM tool call to a calculator and return the quote dict."""
    fn = DISPATCH.get(name)
    if fn is None:
        return {"error": f"unknown tool '{name}'"}
    try:
        return fn(**_coerce_numbers(args)).as_dict()
    except Exception as exc:  # surfaced back to the LLM as a tool result
        return {"error": str(exc)}


def categories_for(scheme: str) -> list[str]:
    """Helper for the UI: list valid category keys for a scheme."""
    return list_categories(scheme)
