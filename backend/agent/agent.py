"""Standalone conversational agent.

This is the actual agent: Claude reasons about what the user is asking,
decides which tool (if any) it needs, decides what arguments to pass, and
decides how to present the result — real tool-use decisions, not a fixed
script. It reuses the exact same backend as the MCP tools
(mcp_server/server.py) — the scorer, Mireye client, and data files are not
duplicated, just driven from a different front door.

Three hazard sub-agents, each its own (Mireye preset, deterministic rule
table, mitigation list) triple, plus three tools that use them:
- check_insurability — wildfire, single address, in depth (verdict,
  driving factors, mitigations, narration, parcel boundary, fire-station
  drive time).
- check_flood_risk — flood, single address, in depth. Verdict driven by
  whether the parcel is inside a FEMA Special Flood Hazard Area.
- check_earthquake_risk — earthquake, single address, in depth. Verdict
  driven by ASCE 7-22 Seismic Design Category.
- full_risk_report — orchestrates all three sub-agents for one address
  and returns one overall verdict (the worst of the three) plus each
  hazard's own verdict — use for "what's the full risk picture" requests
  instead of calling the three single-hazard tools yourself.
- compare_addresses — multiple addresses, ranked by WILDFIRE risk (not
  multi-hazard — see its own docstring). Powers both "compare these two"
  and "scan my listing book" (Approach B) with one tool, since they're the
  same operation at different N.
- ask_about_location — open-ended questions Mireye can answer that are
  OUTSIDE all three hazard scorers (schools, demographics, amenities,
  etc.), via Mireye's /v1/ask. Deliberately separate: its answer has its
  own citations and must never feed a verdict.

Self-contained on purpose: a judge can run this directly without needing
their own MCP-capable client connected (the one demo-logistics risk
flagged against Approach C when it was just a bare MCP tool).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import anthropic  # noqa: E402

from mcp_server.server import (  # noqa: E402
    _tool_ask_about_location,
    _tool_check_earthquake_risk,
    _tool_check_flood_risk,
    _tool_check_insurability,
    _tool_compare_addresses,
    _tool_full_risk_report,
)

MODEL = "claude-sonnet-5"

SAMPLE_LISTINGS_PATH = Path(__file__).resolve().parent.parent / "data" / "sample_listings.json"


def _load_sample_listings() -> list[str]:
    if not SAMPLE_LISTINGS_PATH.exists():
        return []
    with open(SAMPLE_LISTINGS_PATH) as f:
        return json.load(f).get("addresses", [])


_SAMPLE_LISTINGS = _load_sample_listings()

SYSTEM_PROMPT = f"""You are a property-hazard insurability triage assistant for \
real estate agents and title companies. You cover three hazards — wildfire \
(California), flood (nationwide, FEMA), and earthquake (nationwide, USGS) — \
each its own independent sub-agent with its own deterministic scorer. You \
have six tools, all backed by Mireye's data — but different grounding paths, \
and you must never blur them:

- check_insurability: one address, wildfire only, in depth — verdict, \
driving factors, a ranked mitigation list with costs, parcel boundary, and \
real drive time to the nearest fire station. Backed by a DETERMINISTIC \
scorer over CAL FIRE hazard-zone data and California's Safer From Wildfires \
mitigation-action list. California addresses only (verdict is out_of_scope \
elsewhere) — the verdict is computed by code, not by you or by Mireye's Q&A.
- check_flood_risk: one address, flood only, in depth — verdict driven by \
whether the parcel is inside a FEMA Special Flood Hazard Area (the National \
Flood Insurance Program's mandatory-purchase trigger), plus a ranked flood-\
mitigation list. Works for any US address, not just California. Also a \
DETERMINISTIC scorer, not an LLM guess.
- check_earthquake_risk: one address, earthquake only, in depth — verdict \
driven by ASCE 7-22 Seismic Design Category (A-F) at the parcel, plus a \
ranked seismic-retrofit mitigation list. Works for any US address. Also a \
DETERMINISTIC scorer. Seismic Design Category is a building-code trigger, \
NOT an insurance-purchase mandate — never claim earthquake coverage is \
legally required (unlike flood's SFHA/NFIP trigger or wildfire's CA \
disclosure law).
- full_risk_report: one address, ALL THREE hazards at once — returns an \
overall_verdict (the single worst of the three) plus each hazard's own \
verdict and top driving factor. Use this for "what's the full risk on this \
property" / "any red flags on this address" requests instead of calling the \
three single-hazard tools yourself in a row.
- compare_addresses: two or more addresses, ranked by WILDFIRE risk only (not \
multi-hazard) — use this for "compare these", "which is safer", or "check my \
listings/portfolio" requests instead of calling check_insurability repeatedly \
yourself. If the user clearly wants multi-hazard comparison across several \
addresses, call full_risk_report once per address instead and summarize \
yourself — there is no batch multi-hazard tool yet; say so if asked.
- ask_about_location: open-ended questions about a place that NONE of the \
hazard scorers cover — schools, demographics, nearby amenities, anything \
outside wildfire/flood/earthquake scoring. Backed by Mireye's own citation-\
backed Q&A (/v1/ask), which is a DIFFERENT, separate grounding path from the \
scorers. NEVER use ask_about_location's answer to describe, imply, or adjust \
a hazard verdict — if a question is about wildfire, flood, or earthquake \
insurability risk, use the matching scorer tool instead, even if \
ask_about_location could technically answer it.

If the user asks to check "my listings" or "my portfolio" without giving \
addresses, you may use this sample listing book (NOT a live MLS feed — a \
small hand-picked sample, say so if asked): {_SAMPLE_LISTINGS}

Rules, no exceptions:
- Always call a tool for any specific address(es) the user asks about — \
including ones you believe are out of scope (e.g. wildfire check on a non-CA \
address). Let the tool return out_of_scope/low_confidence itself; never \
assert an address is uncovered, unsupported, or otherwise unanswerable from \
your own inference. Never guess or state a verdict from memory or general \
knowledge.
- Default to check_insurability (wildfire) ONLY when the user's question is \
specifically about wildfire, or gives no hazard preference AND the address is \
in California (the flagship use case). If the user's question doesn't name a \
hazard and could reasonably mean "is this insurable at all", or explicitly \
asks for "the full picture"/"any risks"/"red flags", prefer full_risk_report \
over guessing which single hazard they meant.
- If the user asks a wildfire hypothetical ("what if they clear the brush?", \
"what if the roof were replaced?"), re-call check_insurability for the SAME \
address with the appropriate overrides field set (defensible_space_cleared \
and/or home_hardened) rather than answering from the prior result or your \
own judgment. overrides only applies to check_insurability — flood and \
earthquake have no counterfactual override yet; say so if asked for one.
- If an address is missing, ambiguous, or clearly not a real street address, \
ask a clarifying question instead of guessing or calling a tool anyway.
- Always relay the disclaimer(s). Never claim this determines actual insurer \
underwriting, non-renewal, or pricing outcomes — it's a heuristic over \
public data, not an actuarial determination, for any of the three hazards.
- When relaying an ask_about_location answer, keep its confidence/citations \
and any data_gaps intact — don't upgrade a "low confidence" answer to sound \
certain, and don't drop the caveat that a field wasn't available.
- The fire-station drive time in check_insurability's result is informational \
only — it never changes the verdict tier. Present it as context, not as a \
scoring factor.
- Keep responses conversational and concise — you're a real estate agent's \
assistant in a live conversation, not a report generator. For a single \
hazard, lead with the verdict, then the one or two most important reasons, \
then the single most cost-effective mitigation if relevant. For \
full_risk_report, lead with the overall verdict and which hazard is driving \
it, then briefly note the other two. For a comparison, lead with the ranking \
and the standout best/worst, not a wall of per-address detail."""

CHECK_INSURABILITY_SCHEMA = {
    "name": "check_insurability",
    "description": (
        "Wildfire insurability triage for a single California street address. "
        "Returns a verdict (likely_insurable / harder_to_place / "
        "likely_hard_to_place / low_confidence / out_of_scope), driving "
        "factors, a ranked mitigation list with cost ranges, data sources, "
        "and a disclaimer. Use `overrides` for hypothetical follow-ups — "
        "it re-runs the real scorer rather than guessing."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "address": {
                "type": "string",
                "description": "A US street address, e.g. '5555 Skyway, Paradise, CA 95969'.",
            },
            "overrides": {
                "type": "object",
                "description": "Hypothetical flags for counterfactual re-scoring.",
                "properties": {
                    "defensible_space_cleared": {
                        "type": "boolean",
                        "description": "Assume defensible-space work (brush clearance, etc.) is already done.",
                    },
                    "home_hardened": {
                        "type": "boolean",
                        "description": "Assume home-hardening work (roof, vents, siding, etc.) is already done.",
                    },
                },
            },
        },
        "required": ["address"],
    },
}

COMPARE_ADDRESSES_SCHEMA = {
    "name": "compare_addresses",
    "description": (
        "Check and rank multiple California addresses by wildfire "
        "insurability risk, most concerning first. Use for comparisons "
        "or for scanning a whole listing book — do not call "
        "check_insurability in a loop yourself instead of using this."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "addresses": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Two or more US street addresses to check and rank.",
            },
        },
        "required": ["addresses"],
    },
}

ASK_ABOUT_LOCATION_SCHEMA = {
    "name": "ask_about_location",
    "description": (
        "Answers an open-ended question about a US address that is NOT "
        "about wildfire, flood, or earthquake insurability risk (schools, "
        "demographics, nearby amenities, etc.). Never use this for anything "
        "that should inform a hazard verdict — use check_insurability, "
        "check_flood_risk, check_earthquake_risk, or full_risk_report instead."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "address": {
                "type": "string",
                "description": "A US street address.",
            },
            "question": {
                "type": "string",
                "description": "The open-ended question to ask about that location.",
            },
        },
        "required": ["address", "question"],
    },
}

CHECK_FLOOD_RISK_SCHEMA = {
    "name": "check_flood_risk",
    "description": (
        "Flood insurability triage for a single US street address. Returns "
        "a verdict (likely_insurable / harder_to_place / likely_hard_to_place "
        "/ low_confidence), driving factors, a ranked flood-mitigation list "
        "with cost ranges, data sources, and a disclaimer. Verdict is driven "
        "by whether the parcel is inside a FEMA Special Flood Hazard Area "
        "(SFHA) — the NFIP's mandatory-purchase trigger for federally-backed "
        "mortgages. Works for any US address, not just California."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "address": {
                "type": "string",
                "description": "A US street address, e.g. '100 Ocean Dr, Miami Beach, FL 33139'.",
            },
        },
        "required": ["address"],
    },
}

CHECK_EARTHQUAKE_RISK_SCHEMA = {
    "name": "check_earthquake_risk",
    "description": (
        "Earthquake insurability triage for a single US street address. "
        "Returns a verdict (likely_insurable / harder_to_place / "
        "likely_hard_to_place / low_confidence), driving factors, a ranked "
        "seismic-retrofit mitigation list with cost ranges, data sources, "
        "and a disclaimer. Verdict is driven by ASCE 7-22 Seismic Design "
        "Category (A-F) at the parcel — a building-code classification, not "
        "an insurance-purchase mandate. Works for any US address."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "address": {
                "type": "string",
                "description": "A US street address, e.g. '100 Ocean Dr, Miami Beach, FL 33139'.",
            },
        },
        "required": ["address"],
    },
}

FULL_RISK_REPORT_SCHEMA = {
    "name": "full_risk_report",
    "description": (
        "Combined multi-hazard property risk report for a single US street "
        "address — runs the wildfire, flood, and earthquake sub-agents and "
        "returns one overall_verdict (the worst of the three) plus each "
        "hazard's own verdict and top driving factor. Use this instead of "
        "calling check_insurability, check_flood_risk, and "
        "check_earthquake_risk separately when the user wants the full "
        "picture on a property rather than one specific hazard."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "address": {
                "type": "string",
                "description": "A US street address.",
            },
        },
        "required": ["address"],
    },
}

TOOLS = [
    CHECK_INSURABILITY_SCHEMA,
    CHECK_FLOOD_RISK_SCHEMA,
    CHECK_EARTHQUAKE_RISK_SCHEMA,
    FULL_RISK_REPORT_SCHEMA,
    COMPARE_ADDRESSES_SCHEMA,
    ASK_ABOUT_LOCATION_SCHEMA,
]


class InsurabilityAgent:
    """A minimal tool-use agent loop. No agent framework (LangGraph, etc.)
    — a plain Anthropic tool-use loop is enough here and keeps the
    dependency surface small (same "boring by default" call as Premise 8,
    just applied to our own driver instead of an external MCP host)."""

    MAX_TOOL_TURNS = 6

    def __init__(self, model: str = MODEL, verbose: bool = True, max_tool_turns: int | None = None):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY not set — the agent needs it to reason "
                "and narrate. Set it in .env."
            )
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._verbose = verbose
        self._max_tool_turns = max_tool_turns or self.MAX_TOOL_TURNS
        self._messages: list[dict] = []

    def ask(self, user_message: str) -> str:
        """Text-only reply — used by the CLI."""
        return self.ask_verbose(user_message)["reply"]

    def _run_tool(self, name: str, tool_input: dict) -> tuple[dict, dict]:
        """Executes one tool call. Returns (result, trace_entry). A tool
        crash degrades to a low_confidence result rather than propagating
        — one bad tool call must not take down the whole turn."""
        try:
            if name == "check_insurability":
                address = tool_input.get("address", "")
                overrides = tool_input.get("overrides")
                if self._verbose:
                    print(
                        f"  [agent] calling check_insurability("
                        f"address={address!r}, overrides={overrides})"
                    )
                result = _tool_check_insurability(address, overrides=overrides)
                trace = {
                    "tool": name,
                    "input": {"address": address, "overrides": overrides},
                    "verdict": result.get("verdict"),
                    "data_source_mode": result.get("data_source_mode"),
                    "lat": result.get("lat"),
                    "lng": result.get("lng"),
                    "parcel_boundary_geojson": result.get("parcel_boundary_geojson"),
                    "fire_station": result.get("fire_station"),
                }
            elif name == "check_flood_risk":
                address = tool_input.get("address", "")
                if self._verbose:
                    print(f"  [agent] calling check_flood_risk(address={address!r})")
                result = _tool_check_flood_risk(address)
                trace = {
                    "tool": name,
                    "input": {"address": address},
                    "verdict": result.get("verdict"),
                    "data_source_mode": result.get("data_source_mode"),
                    "lat": result.get("lat"),
                    "lng": result.get("lng"),
                    "parcel_boundary_geojson": result.get("parcel_boundary_geojson"),
                }
            elif name == "check_earthquake_risk":
                address = tool_input.get("address", "")
                if self._verbose:
                    print(f"  [agent] calling check_earthquake_risk(address={address!r})")
                result = _tool_check_earthquake_risk(address)
                trace = {
                    "tool": name,
                    "input": {"address": address},
                    "verdict": result.get("verdict"),
                    "data_source_mode": result.get("data_source_mode"),
                    "lat": result.get("lat"),
                    "lng": result.get("lng"),
                    "parcel_boundary_geojson": result.get("parcel_boundary_geojson"),
                }
            elif name == "full_risk_report":
                address = tool_input.get("address", "")
                if self._verbose:
                    print(f"  [agent] calling full_risk_report(address={address!r})")
                result = _tool_full_risk_report(address)
                trace = {
                    "tool": name,
                    "input": {"address": address},
                    "overall_verdict": result.get("overall_verdict"),
                    "hazards": result.get("hazards", []),
                    "lat": result.get("lat"),
                    "lng": result.get("lng"),
                }
            elif name == "compare_addresses":
                addresses = tool_input.get("addresses", [])
                if self._verbose:
                    print(f"  [agent] calling compare_addresses(addresses={addresses!r})")
                result = _tool_compare_addresses(addresses)
                trace = {
                    "tool": name,
                    "input": {"addresses": addresses},
                    "results": result.get("results", []),
                    "summary": result.get("summary"),
                }
            elif name == "ask_about_location":
                address = tool_input.get("address", "")
                question = tool_input.get("question", "")
                if self._verbose:
                    print(
                        f"  [agent] calling ask_about_location("
                        f"address={address!r}, question={question!r})"
                    )
                result = _tool_ask_about_location(address, question)
                trace = {
                    "tool": name,
                    "input": {"address": address, "question": question},
                    "confidence": result.get("confidence"),
                }
            else:
                result = {"error": f"Unknown tool: {name}"}
                trace = {"tool": name, "input": tool_input, "error": result["error"]}
        except Exception as exc:  # noqa: BLE001 — a tool crash must not crash the agent
            result = {
                "verdict": "low_confidence",
                "driving_factors": [],
                "mitigations": [],
                "data_sources": [],
                "missing_inputs": [],
                "disclaimer": f"Tool call failed unexpectedly: {exc}",
            }
            trace = {"tool": name, "input": tool_input, "error": str(exc)}
        return result, trace

    def ask_verbose(self, user_message: str) -> dict:
        """Reply plus a trace of which tool calls the agent decided to make
        and with what arguments/results — used by the web API so the UI can
        show the agent actually reasoning and acting, not just answering.

        Robustness: caps tool-call turns (a pathological response could
        otherwise loop indefinitely) and catches Anthropic API failures
        (rate limits, timeouts, outages) so a bad turn degrades to a clear
        error message instead of crashing the caller. Either failure mode
        rolls the conversation history back to before this turn, so the
        next message isn't sent against corrupted state (e.g. two
        consecutive user-role messages, which the API rejects)."""
        turn_start = len(self._messages)
        self._messages.append({"role": "user", "content": user_message})
        tool_call_trace: list[dict] = []

        try:
            for _ in range(self._max_tool_turns):
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=1024,
                    system=SYSTEM_PROMPT,
                    tools=TOOLS,
                    messages=self._messages,
                )
                self._messages.append(
                    {"role": "assistant", "content": response.content}
                )

                if response.stop_reason != "tool_use":
                    reply = "".join(
                        block.text for block in response.content if block.type == "text"
                    ).strip()
                    return {"reply": reply, "tool_calls": tool_call_trace}

                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    result, trace = self._run_tool(block.name, block.input)
                    tool_call_trace.append(trace)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result),
                        }
                    )
                self._messages.append({"role": "user", "content": tool_results})

            # Exhausted max_tool_turns without a final text response.
            self._messages = self._messages[:turn_start]
            return {
                "reply": (
                    "I made several tool calls but couldn't reach a final answer "
                    "for that — something's off. Could you rephrase the question?"
                ),
                "tool_calls": tool_call_trace,
            }
        except anthropic.APIError as exc:
            self._messages = self._messages[:turn_start]
            return {
                "reply": (
                    f"Sorry, I hit an error talking to the model "
                    f"({type(exc).__name__}) — please try again in a moment."
                ),
                "tool_calls": tool_call_trace,
            }


def main():
    agent = InsurabilityAgent()
    print("Insurability Triage Agent — ask about a California address (Ctrl-C to exit)\n")
    while True:
        try:
            user_input = input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user_input.strip():
            continue
        reply = agent.ask(user_input)
        print(f"\n{reply}\n")


if __name__ == "__main__":
    main()
