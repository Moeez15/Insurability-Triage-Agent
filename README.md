# Insurability Triage Agent

Wildfire insurability triage for a California street address — combines
[Mireye](https://www.mireye.com/)'s physical/regulatory hazard data
(terrain, vegetation, CAL FIRE Fire Hazard Severity Zone) with California's
**Safer From Wildfires** insurer-mitigation regulation to produce a
specific, actionable verdict: is this address likely to be hard to place
with an insurer, and what mitigation work would change that.

Built for the Mireye "build an agent" hackathon challenge. Full design
rationale, alternatives considered, and review history:
[design doc](~/.gstack/projects/moeezahmad/moeezahmad-unknown-design-20260814-170826.md).

## What it is

A wildfire-insurability triage **agent** for real estate agents and title
companies: it reasons about what you're asking, decides which of its two
tools to call (a single address in depth, or several addresses ranked),
decides what arguments to pass (including re-scoring with `overrides` for
a hypothetical like "what if they clear the brush?"), and decides how to
present the result — real tool-use decisions, not a fixed script or a
report generator.

- `check_insurability(address, overrides)` — one address, in depth. Also
  pulls the actual parcel boundary (`/v1/lookup`) and real driving time to
  the nearest fire station (`/v1/proximity`) — the latter is informational
  context only, never a scoring input.
- `compare_addresses(addresses)` — two or more addresses, ranked by risk.
  Powers both "compare these two" and "scan my listing book" (Approach B)
  with one tool, since they're the same operation at different N. When
  asked to check "my listings" without addresses, the agent can pull a
  small hand-picked sample book (`backend/data/sample_listings.json`) —
  clearly not a live MLS feed, just enough real, geocode-verified
  addresses to demo the ranking. Skips the parcel/fire-station enrichment
  to stay fast across N addresses.
- `ask_about_location(address, question)` — open-ended questions Mireye's
  `/v1/ask` can answer that the scorer doesn't cover (schools,
  demographics, flood-zone detail). Deliberately on a separate grounding
  path from the verdict — its citations/confidence pass through as-is,
  and it's never allowed to describe or adjust an insurability verdict.

The chat UI renders a map (Leaflet, OpenStreetMap tiles, no API key) for
every result — the actual parcel boundary polygon plus a pin for a single
address, or bounds-fit color-coded pins for a comparison.

```
insurability-triage-agent/
├── backend/     Python — agent, scorer, Mireye client, MCP tool, FastAPI wrapper
└── frontend/    Next.js — chat UI (primary demo path)
```

Three front doors onto the same backend logic (`backend/mireye_client/`,
`backend/scorer/`, `backend/data/` — no duplicated logic):

- **`frontend/` + `backend/api/`** — a Next.js chat UI backed by a thin
  FastAPI wrapper around the agent. **This is the primary demo path.** The
  UI shows the agent's tool calls transparently (which address it checked,
  the verdict, and any counterfactual assumptions) so it visibly reasons
  and acts, not just answers.
- **`backend/agent/agent.py`** — the actual agent: Claude + native tool-use
  (no LangGraph), runnable standalone as a CLI too.
- **`backend/mcp_server/server.py`** — the same `check_insurability` and
  `compare_addresses` tools exposed over MCP, for anyone who wants to plug
  them into their own MCP-capable host (Claude Desktop, Claude Code, etc.)
  instead.

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in MIREYE_API_TOKEN (required) and ANTHROPIC_API_KEY (optional)
```

`ANTHROPIC_API_KEY` is required for `agent/agent.py` (it's the agent's
reasoning). Without it, `mcp_server/server.py`'s tool still works on its
own — narration falls back to a plain-text rendering of the structured
verdict instead of an LLM-written paragraph.

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
```

## Run the MCP server (alternate — plug into your own MCP host)

```bash
cd backend
source .venv/bin/activate
python -m mcp_server.server
```

Point an MCP-capable client at this process (stdio transport) to try it
that way instead.

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
           tool to call, check_insurability or compare_addresses)
            -> check_insurability(address, overrides)   [single address]
            -> compare_addresses(addresses)              [ranked, N addresses]
                -> Mireye /v1/geocode -> /v1/fetch(preset=wildfire_underwrite)
                -> deterministic scorer (rule table, backend/scorer/rule_table.py)
                -> LLM narration (backend/mcp_server/narrate.py, narrates only, never scores)
```

`compare_addresses` reuses `check_insurability`'s exact pipeline per
address — no duplicated logic, just a loop plus a rank-by-severity sort.

`backend/mcp_server/server.py` exposes both tools over the MCP protocol
as an alternate front door, for anyone with their own MCP host instead of
this repo's UI.

If the live Mireye call fails, falls back to a small cache of pre-verified
demo addresses (`backend/data/demo_cache.json`) rather than stalling a
live demo.

## Scope (v1)

California only — Mireye's CAL FIRE Fire Hazard Severity Zone data is
explicitly California-only (live-verified). See the design doc's
Constraints and Next Steps for the Colorado expansion plan.
