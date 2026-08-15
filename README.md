# Insurability Triage Agent

Multi-hazard property insurability triage for a US street address —
combines [Mireye](https://www.mireye.com/)'s physical/regulatory hazard
data with real regulatory hooks for each hazard (California's **Safer
From Wildfires** mitigation regulation, FEMA's NFIP mandatory flood
insurance trigger, ASCE 7 seismic design category) to produce a specific,
actionable verdict per hazard: is this address likely to be hard to place
with an insurer, and what mitigation work would change that.


## What it is

A property-hazard triage **agent** for real estate agents and title
companies, built around three hazard **sub-agents** — wildfire (California,
CAL FIRE), flood (nationwide, FEMA), earthquake (nationwide, USGS/ASCE) —
each its own independent (Mireye preset, deterministic rule table,
mitigation list) triple sharing one fetch → score → narrate pipeline
(`backend/tools/hazard_tools.py`'s `_HAZARD_PRESETS`). The top-level agent
reasons about what you're asking, decides which sub-agent(s) to call,
decides what arguments to pass (including re-scoring with `overrides` for
a wildfire hypothetical like "what if they clear the brush?"), and decides
how to present the result — real tool-use decisions, not a fixed script.

- `check_insurability(address, overrides)` — wildfire, one address, in
  depth. Also pulls the actual parcel boundary (`/v1/lookup`) and real
  driving time to the nearest fire station (`/v1/proximity`) —
  informational context only, never a scoring input. California only.
- `check_flood_risk(address)` — flood, one address, in depth. Verdict
  driven by whether the parcel is inside a FEMA Special Flood Hazard Area
  (the NFIP's mandatory-purchase trigger). Any US address.
- `check_earthquake_risk(address)` — earthquake, one address, in depth.
  Verdict driven by ASCE 7-22 Seismic Design Category (A-F) — a
  building-code trigger, explicitly not framed as an insurance mandate
  (unlike flood/wildfire, CA has no legal requirement to carry earthquake
  coverage). Any US address.
- `full_risk_report(address)` — orchestrates all three sub-agents for one
  address and returns one `overall_verdict` (the worst of the three) plus
  each hazard's own verdict and top driving factor. The address-entry
  screen's default action.
- `compare_addresses(addresses)` — two or more addresses, ranked by
  **wildfire** risk (not multi-hazard). Powers both "compare these two"
  and "scan my listing book" (Approach B) with one tool, since they're the
  same operation at different N. When asked to check "my listings" without
  addresses, the agent can pull a small hand-picked sample book
  (`backend/data/sample_listings.json`) — clearly not a live MLS feed,
  just enough real, geocode-verified addresses to demo the ranking. Skips
  the parcel/fire-station enrichment to stay fast across N addresses.
- `ask_about_location(address, question)` — open-ended questions Mireye's
  `/v1/ask` can answer that none of the three scorers cover (schools,
  demographics, nearby amenities). Deliberately on a separate grounding
  path from any verdict — its citations/confidence pass through as-is,
  and it's never allowed to describe or adjust a hazard verdict.

The chat UI renders a map (Leaflet, OpenStreetMap tiles, no API key) for
every result — the actual parcel boundary polygon plus a pin for a single
address, or bounds-fit color-coded pins for a comparison.

```
insurability-triage-agent/
├── backend/     Python — agent, scorer, Mireye client, hazard tools, FastAPI wrapper
└── frontend/    Next.js — chat UI (primary demo path)
```

Two front doors onto the same backend logic (`backend/tools/`,
`backend/mireye_client/`, `backend/scorer/`, `backend/data/` — no
duplicated logic):

- **`frontend/` + `backend/api/`** — a Next.js chat UI backed by a thin
  FastAPI wrapper around the agent. **This is the primary demo path.** The
  UI shows the agent's tool calls transparently (which address it checked,
  the verdict, and any counterfactual assumptions) so it visibly reasons
  and acts, not just answers.
- **`backend/agent/agent.py`** — the actual agent: Claude + native tool-use
  (no LangGraph, no MCP indirection — the agent calls its tools as plain
  Python functions), runnable standalone as a CLI too.

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in MIREYE_API_TOKEN (required) and ANTHROPIC_API_KEY (optional)
```

`ANTHROPIC_API_KEY` is required for `agent/agent.py` (it's the agent's
reasoning). Without it, `tools/hazard_tools.py`'s functions still work on
their own — narration falls back to a plain-text rendering of the
structured verdict instead of an LLM-written paragraph.

## Run the web UI (primary demo path)

Two processes, two terminals, from the repo root:

```bash
# Terminal 1 — backend
cd backend
source .venv/bin/activate
uvicorn api.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm run dev
```

Open http://localhost:3000. `frontend/.env.local` already points at
`http://localhost:8000`.

## Run the agent as a CLI (no browser)

```bash
cd backend
source .venv/bin/activate
python -m agent.agent
```

```
> Is 5555 Skyway, Paradise, CA 95969 going to be hard to insure?
> What if the defensible space is already cleared?
> Can you check my listing book and rank them by risk?
> Give me the full risk picture for 100 Ocean Dr, Miami Beach, FL 33139
> Is that address in a flood zone that requires mandatory insurance?
```

## Run the tests

```bash
cd backend
source .venv/bin/activate
pytest -v
```

## Architecture

```
Next.js chat UI (frontend/, renders a Leaflet map per result)
    -> FastAPI (backend/api/main.py, one InsurabilityAgent per session)
        -> backend/agent/agent.py (Claude + tool-use loop — decides which
           tool/sub-agent to call)
            -> check_insurability(address, overrides)   [wildfire, CA only]
            -> check_flood_risk(address)                 [flood, any US address]
            -> check_earthquake_risk(address)             [earthquake, any US address]
            -> full_risk_report(address)                 [orchestrates the three above]
            -> compare_addresses(addresses)              [wildfire, ranked, N addresses]
                -> Mireye /v1/geocode -> /v1/fetch(preset=<hazard's preset>)
                -> deterministic scorer (backend/scorer/*_rule_table.py)
                -> LLM narration (backend/tools/narrate.py, narrates only, never scores)
```

Each hazard sub-agent is one entry in `backend/tools/hazard_tools.py`'s
`_HAZARD_PRESETS` dict: a (Mireye preset, scorer function) pair sharing
one fetch → score → enrich → narrate pipeline (`_tool_check_hazard`).
Adding a fourth hazard means adding one entry there plus a
`scorer/*_rule_table.py` module — not touching wildfire, flood, or
earthquake. `full_risk_report` is the one tool that orchestrates all
three; every other tool calls exactly one sub-agent, and `compare_addresses`
reuses `check_insurability`'s exact pipeline per address — no duplicated
logic anywhere, just a loop plus a rank-by-severity sort.

If a live Mireye call fails, falls back to a small cache of pre-verified
demo addresses (`backend/data/demo_cache.json`, one entry per hazard
preset under `fetch_by_preset`) rather than stalling a live demo.

## Scope (v1)

Wildfire (`check_insurability`, `compare_addresses`) is California only —
Mireye's CAL FIRE Fire Hazard Severity Zone data is explicitly
California-only (live-verified). Flood and earthquake work for any US
address (FEMA NFHL and USGS/ASCE data are nationwide). See the design
doc's Constraints and Next Steps for further expansion plans.
