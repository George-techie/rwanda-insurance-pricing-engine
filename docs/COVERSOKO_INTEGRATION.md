# CoverSoko integration

This assistant (the AI/LLM layer) can price through the **CoverSoko Underwriter**
API (the production underwriting engine) instead of the bundled local
calculators. The split mirrors how the team is built: the AI layer owns the
conversation, retrieval, grounding and tracing; CoverSoko owns the rate data,
the underwriting rules, and the per-insurer tariff overrides.

This is the typed-tool / endpoint pattern we standardised on: the model never
writes SQL and never picks the tenant. It only fills the parameters of a typed
tool; our client calls `POST /api/quote`; CoverSoko runs the query.

## How it works

- When `COVERSOKO_API_URL` is set, the assistant exposes a `quote_property` tool
  (`assar/integrations/coversoko.py`). The LLM fills `perilType`, `sumInsured`,
  `coverType`, `attributes`, and the special-perils flags; the client posts them
  to CoverSoko and normalises the response into the same shape the chat already
  renders (so the step-by-step breakdown, grounding guard, and trace all work).
- When it is unset, nothing changes: the local ASSAR calculators are used.
- The tenant (`ownerId`) is taken from `COVERSOKO_OWNER_ID`, never from the model,
  so a chat message can never choose whose tariff overrides apply.

## Run it end to end

1. Start the CoverSoko stack (in the `coversoko-underwriter` repo):
   ```bash
   cp .env.example .env   # fill in DB values
   docker compose up --build
   ```
   The API comes up on http://localhost:3500 (Swagger at /api-docs).

2. Point this assistant at it (in this repo's `.env`):
   ```bash
   COVERSOKO_API_URL=http://localhost:3500
   # COVERSOKO_OWNER_ID=<insurer-uuid>   # to apply that insurer's overrides
   ```

3. Smoke-test the client directly:
   ```bash
   python -m assar.integrations.coversoko
   ```
   It prints reachability and one example quote (Fire_Allied_Perils, Banks).

4. Run the app (`streamlit run app.py`) and ask, for example,
   "price fire and allied perils for a commercial bank, sum insured 10,000,000".
   The model calls `quote_property`; the premium and breakdown come from CoverSoko.

## Contract (from the CoverSoko source)

Request `POST /api/quote`:

| Field | Type | Notes |
|---|---|---|
| `perilType` | string | e.g. `Fire_Allied_Perils` |
| `sumInsured` | number | |
| `coverType` | string | rate key in the classification, e.g. `standardFireRate` |
| `attributes` | object | risk attributes; `propertyCategory` selects the classification, `propertyType` (commercial/residential) selects the special-perils rate |
| `specialPerilNames` | string[] | optional |
| `includeAllSpecialPerils` | boolean | optional |
| `ownerId` | uuid | optional tenant; set server-side, not by the model |

Response `data`: `{ baseRate, specialPerilsRate, totalRate, premium, breakdown:[{label, rate}] }`.
Rates are fractions (`premium = sumInsured * totalRate`); we display them as percent.

## Mapping between the two systems

| This assistant | CoverSoko |
|---|---|
| pricing scheme (e.g. `fire`) | `perilType` |
| risk category / occupancy (e.g. `hotels`, `banks`) | `attributes.propertyCategory` |
| standard vs all-special-perils column | `coverType` + `includeAllSpecialPerils` |
| acting insurer (`current_insurer()` / tenant) | `ownerId` |
| per-insurer `rate_override` overlay | `Override` / `ClassificationOverride` (`ownerId`) |

The two tenancy models are the same overlay-on-base design; wiring real auth means
mapping our authenticated insurer to the CoverSoko `ownerId`.

## Tests

`tests/test_coversoko.py` mocks the HTTP layer, so the integration is verified
offline: request shaping, response normalization, tenant handling, error
surfacing (unreachable backend returns a tool error, never crashes), and that the
tool is registered only when the backend is configured.
