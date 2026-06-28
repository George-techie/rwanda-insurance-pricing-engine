"""Central registry of pricing calculators and the JSON tool schemas the LLM uses.

Keeping a curated set of typed functions (instead of free-form text-to-SQL) means
the arithmetic is deterministic and unit-testable; the model only extracts
parameters and orchestrates.
"""
from __future__ import annotations

import inspect
import re

from ..integrations import coversoko
from .base import list_categories
from .fire import quote_burglary, quote_consequential_loss, quote_fire
from .products import (
    quote_aviation, quote_bbb, quote_bond, quote_boiler, quote_car_ear, quote_cpm,
    quote_do_liability, quote_eear, quote_fidelity, quote_liability, quote_machinery,
    quote_marine_hull, quote_pa_gpa, quote_plate_glass, quote_pvt,
    quote_school_liability,
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

# Transit commodity taxonomy (shared by GIT and marine cargo tool schemas).
_TRANSIT_COMMODITIES = [
    "raw_agricultural_produce", "grains_in_bags", "nonfragile_not_pilferable",
    "nonfragile_pilferable", "semi_fragile", "fragile", "chemical_in_drums",
    "chemicals_cement_fertilizer_bags", "pharmaceuticals", "food_confectionery_cans",
    "food_confectionery_bags", "bulk_petroleum", "bulk_grains_edible_oils",
    "other_liquid_beers", "matches_fireworks_explosives", "copper_precious_metals",
    "household_professionally_packed", "household_not_professionally_packed",
]
_COMMODITY_HINT = (
    "Map the goods to the closest class: semi_fragile = electrical "
    "appliances/electronics; fragile = glass/glassware/chinaware/wines; "
    "nonfragile_pilferable = spare parts/batteries/tyres/cigarettes/paper; "
    "nonfragile_not_pilferable = machinery/iron not prone to pilferage; "
    "chemicals_cement_fertilizer_bags = cement/fertilizer in bags."
)

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
                    "commodity": {"type": "string", "enum": _TRANSIT_COMMODITIES,
                                  "description": _COMMODITY_HINT},
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
    {
        "type": "function",
        "function": {
            "name": "quote_consequential_loss",
            "description": "Price Consequential Loss / business interruption following fire. Basis is the fire material-damage rate for the risk.",
            "parameters": {
                "type": "object",
                "properties": {
                    "risk_category": {"type": "string", "description": "Fire occupancy key, e.g. 'hotels', 'banks'."},
                    "gross_profit_si": {"type": "number", "description": "Sum insured (gross profit / wages)."},
                    "indemnity_period_months": {"type": "integer"},
                    "cover": {"type": "string", "enum": ["gross_profit", "auditors_fees", "wages"]},
                    "period_months": {"type": "number"},
                },
                "required": ["risk_category", "gross_profit_si"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quote_burglary",
            "description": "Price Burglary & Theft cover (full value, or first-loss if a ratio is given).",
            "parameters": {
                "type": "object",
                "properties": {
                    "sum_insured": {"type": "number"},
                    "high_value": {"type": "boolean", "description": "High-value goods such as precious metals."},
                    "first_loss_ratio": {"type": "number", "description": "First-loss SI as a fraction of full value (0-1); omit for full value."},
                    "stock_declaration": {"type": "boolean"},
                    "period_months": {"type": "number"},
                },
                "required": ["sum_insured"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quote_marine_cargo",
            "description": "Price Marine Cargo for a commodity (Institute Cargo Clause A/B/C, by transit mode).",
            "parameters": {
                "type": "object",
                "properties": {
                    "commodity": {"type": "string", "enum": _TRANSIT_COMMODITIES,
                                  "description": _COMMODITY_HINT},
                    "consignment_value": {"type": "number"},
                    "containerized": {"type": "boolean"},
                    "mode": {"type": "string", "enum": ["combined", "road", "air", "sea"]},
                    "clause": {"type": "string", "enum": ["A", "B", "C"]},
                },
                "required": ["commodity", "consignment_value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quote_pa_gpa",
            "description": "Price Personal Accident (PA) or Group Personal Accident (GPA) cover.",
            "parameters": {
                "type": "object",
                "properties": {
                    "risk_class": {"type": "string", "description": "Occupation class, e.g. 'construction_workers', 'office_administration', 'drivers_security_mining'."},
                    "death_benefit": {"type": "number", "description": "Capital sum / death benefit."},
                    "group": {"type": "boolean", "description": "Group PA (true) vs individual PA (false)."},
                    "benefits": {"type": "array", "items": {"type": "string", "enum": ["death", "tpd", "ttd", "medical", "funeral"]}},
                    "student": {"type": "boolean"},
                    "period_months": {"type": "number"},
                },
                "required": ["risk_class", "death_benefit"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quote_car_ear",
            "description": "Price Contractors All Risks (kind='car') or Erection All Risks (kind='ear') for a project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": ["car", "ear"]},
                    "project_type": {"type": "string", "description": "Project key, e.g. 'residential_buildings', 'bridges', 'dams', 'roads_urban'."},
                    "contract_value": {"type": "number"},
                    "duration_months": {"type": "integer"},
                    "tpl_limit": {"type": "number", "description": "Third-party liability limit (0 = none)."},
                },
                "required": ["kind", "project_type", "contract_value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quote_machinery",
            "description": "Price Machinery Breakdown for a machine / industry type.",
            "parameters": {
                "type": "object",
                "properties": {
                    "machine_type": {"type": "string", "description": "Machine/industry key, e.g. 'transformers', 'wood_working', 'metal_producing'."},
                    "sum_insured": {"type": "number"},
                    "period_months": {"type": "number"},
                },
                "required": ["machine_type", "sum_insured"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quote_cpm",
            "description": "Price Contractors Plant & Machinery (CPM) by plant group and hazard class.",
            "parameters": {
                "type": "object",
                "properties": {
                    "plant_group": {"type": "string", "enum": ["1", "2", "3"], "description": "1=Cranes, 2=Mobile plant, 3=Non-mobile plant."},
                    "hazard_class": {"type": "string", "enum": ["A", "B", "C"]},
                    "sum_insured": {"type": "number"},
                    "period_months": {"type": "number"},
                },
                "required": ["plant_group", "hazard_class", "sum_insured"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quote_fidelity",
            "description": "Price Fidelity Guarantee (cover against staff fraud/dishonesty).",
            "parameters": {
                "type": "object",
                "properties": {
                    "risk": {"type": "string", "enum": ["financial_services",
                             "distribution_sales_purchasing", "other_offices", "security_firms"]},
                    "sum_insured": {"type": "number", "description": "Guarantee amount."},
                    "blanket": {"type": "boolean", "description": "Blanket cover (Rwf30,000 per capita)."},
                    "employees": {"type": "integer", "description": "Number of employees (blanket only)."},
                    "period_months": {"type": "number"},
                },
                "required": ["risk", "sum_insured"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quote_bbb",
            "description": "Price Bankers Blanket Bond for a financial institution.",
            "parameters": {
                "type": "object",
                "properties": {"limit_of_indemnity": {"type": "number"}},
                "required": ["limit_of_indemnity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quote_do_liability",
            "description": "Price Directors & Officers liability on a selected limit.",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit_of_indemnity": {"type": "number"},
                    "risk": {"type": "string", "enum": ["financial_services", "other_offices"]},
                },
                "required": ["limit_of_indemnity"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quote_school_liability",
            "description": "Price School Liability (flat premium per student, annual).",
            "parameters": {
                "type": "object",
                "properties": {
                    "school_category": {"type": "string", "enum": ["nursery_primary",
                                        "secondary_non_technical", "secondary_technical", "university"]},
                    "num_students": {"type": "integer"},
                    "period_months": {"type": "number"},
                },
                "required": ["school_category", "num_students"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quote_aviation",
            "description": "Price an aviation risk class (hull, cargo, liabilities, passenger).",
            "parameters": {
                "type": "object",
                "properties": {
                    "risk_class": {"type": "string", "enum": ["hull_all_risks", "cargo_low",
                                   "cargo_high", "airport_operators_liability",
                                   "hanger_keeper_liability", "pax_liability_per_seat"]},
                    "sum_insured": {"type": "number", "description": "Hull value or selected limit (per-seat limit for PAX)."},
                    "seats": {"type": "integer", "description": "Number of seats (PAX liability only)."},
                },
                "required": ["risk_class", "sum_insured"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quote_marine_hull",
            "description": "Price Marine Hull (hull all risks) or its third-party liability.",
            "parameters": {
                "type": "object",
                "properties": {
                    "vessel_value": {"type": "number"},
                    "cover": {"type": "string", "enum": ["hull", "tpl"]},
                },
                "required": ["vessel_value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quote_boiler",
            "description": "Price Boilers & Pressure Vessels (material damage or third-party liability).",
            "parameters": {
                "type": "object",
                "properties": {
                    "sum_insured": {"type": "number"},
                    "cover": {"type": "string", "enum": ["material_damage", "third_party_liability"]},
                },
                "required": ["sum_insured"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quote_eear",
            "description": "Price Computer / Electronic Equipment All Risks (EEAR).",
            "parameters": {
                "type": "object",
                "properties": {
                    "sum_insured": {"type": "number"},
                    "location": {"type": "string", "enum": ["premises", "portable", "unspecified", "increased_cost"],
                                 "description": "premises=at insured's premises; portable=away; unspecified=tender; increased_cost=data reconstruction."},
                },
                "required": ["sum_insured"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quote_plate_glass",
            "description": "Price Plate Glass insurance.",
            "parameters": {
                "type": "object",
                "properties": {"sum_insured": {"type": "number"}},
                "required": ["sum_insured"],
            },
        },
    },
]

# CoverSoko underwriting-engine tool. Exposed only when the backend is configured
# (COVERSOKO_API_URL set), so default/offline behaviour is unchanged. Note: the
# tenant (ownerId) is NOT a model parameter; it is set server-side from config.
COVERSOKO_TOOL = {
    "type": "function",
    "function": {
        "name": "quote_property",
        "description": "Calculate a property insurance premium via the CoverSoko "
                       "underwriting engine (rules + classification + special perils). "
                       "Use for property/fire-type risks when CoverSoko is available.",
        "parameters": {
            "type": "object",
            "properties": {
                "perilType": {"type": "string", "description": "e.g. 'Fire_Allied_Perils'."},
                "sumInsured": {"type": "number"},
                "coverType": {"type": "string", "description": "Rate key in the classification, e.g. 'standardFireRate'."},
                "attributes": {"type": "object", "description": "Risk attributes, e.g. {\"propertyType\": \"commercial\", \"propertyCategory\": \"Banks\"}."},
                "specialPerilNames": {"type": "array", "items": {"type": "string"}},
                "includeAllSpecialPerils": {"type": "boolean"},
            },
            "required": ["perilType", "sumInsured", "coverType", "attributes"],
        },
    },
}

# Groq/Llama sometimes emit numeric AND boolean args as JSON strings ("1000000",
# "true"), which the provider then rejects against a strict {"type":"number"} or
# {"type":"boolean"} schema (400 tool_use_failed). Relax those fields to accept
# the type OR string; we coerce back to real values in run_tool().
for _t in TOOL_SCHEMAS + [COVERSOKO_TOOL]:
    for _p in _t["function"]["parameters"]["properties"].values():
        if _p.get("type") in ("number", "integer", "boolean"):
            _p["type"] = [_p["type"], "string"]


def get_tool_schemas() -> list[dict]:
    """Tools offered to the LLM: the local ASSAR calculators, plus the CoverSoko
    property tool when the underwriting backend is configured."""
    return TOOL_SCHEMAS + ([COVERSOKO_TOOL] if coversoko.enabled() else [])


_TRUE = {"true", "yes"}
_FALSE = {"false", "no"}


def _coerce_numbers(args: dict) -> dict:
    """Turn stringified scalars from the model into real values: 'true'/'false'
    into booleans, and numeric strings ('1,000,000', '12') into numbers. Note
    '0'/'1' are kept numeric (not booleans) so enum and amount fields are safe."""
    out = {}
    for k, v in args.items():
        if isinstance(v, str):
            low = v.strip().lower()
            if low in _TRUE:
                out[k] = True
                continue
            if low in _FALSE:
                out[k] = False
                continue
            s = v.strip().replace(",", "").replace("_", "")
            try:
                out[k] = int(s) if re.fullmatch(r"-?\d+", s) else float(s)
                continue
            except ValueError:
                pass
        out[k] = v
    return out


def _quote_property(perilType, sumInsured, coverType, attributes,
                    specialPerilNames=None, includeAllSpecialPerils=False):
    """Bridge the LLM's CoverSoko tool call to the HTTP client. The tenant
    (ownerId) is taken from config inside the client, never from the model."""
    return coversoko.quote(
        perilType, sumInsured, coverType, attributes,
        special_peril_names=specialPerilNames,
        include_all_special_perils=bool(includeAllSpecialPerils),
    )


# name in schema -> python callable
DISPATCH = {
    "quote_fire": quote_fire,
    "quote_property": _quote_property,
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
    "quote_fidelity": quote_fidelity,
    "quote_bbb": quote_bbb,
    "quote_do_liability": quote_do_liability,
    "quote_school_liability": quote_school_liability,
    "quote_aviation": quote_aviation,
    "quote_marine_hull": quote_marine_hull,
    "quote_boiler": quote_boiler,
    "quote_eear": quote_eear,
    "quote_plate_glass": quote_plate_glass,
}


def run_tool(name: str, args: dict) -> dict:
    """Dispatch an LLM tool call to a calculator and return the quote dict."""
    fn = DISPATCH.get(name)
    if fn is None:
        return {"error": f"unknown tool '{name}'"}
    args = _coerce_numbers(args)
    # Drop any arguments the calculator doesn't accept (the LLM occasionally
    # invents a kwarg, e.g. passing 'cover' to a tool that has no such param).
    params = inspect.signature(fn).parameters
    if not any(p.kind == p.VAR_KEYWORD for p in params.values()):
        args = {k: v for k, v in args.items() if k in params}
    try:
        result = fn(**args)
        # Local calculators return a Quote; the CoverSoko bridge returns a dict.
        return result.as_dict() if hasattr(result, "as_dict") else result
    except Exception as exc:  # surfaced back to the LLM as a tool result
        return {"error": str(exc)}


def categories_for(scheme: str) -> list[str]:
    """Helper for the UI: list valid category keys for a scheme."""
    return list_categories(scheme)
