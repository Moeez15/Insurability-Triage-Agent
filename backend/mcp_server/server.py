"""MCP server exposing multi-hazard property risk tools.

Each hazard (wildfire, flood, earthquake) is its own sub-agent: an
independent (Mireye preset, deterministic rule table, mitigation list)
triple sharing one fetch -> score -> enrich -> narrate pipeline. Adding a
hazard means adding one entry to _HAZARD_PRESETS and a scorer/*_rule_table
module, not touching the others. full_risk_report is the one tool that
orchestrates all three; every other tool calls exactly one sub-agent.

No custom agent-loop framework (Premise 8) — whatever MCP host is
connected (Claude Desktop, Claude Code, etc.) already handles multi-turn
conversation and re-invokes check_insurability with follow-up `overrides`
when a user asks a hypothetical like "what if I clear the brush?".
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

from mcp.server.mcpserver import MCPServer  # noqa: E402

from mireye_client.client import (  # noqa: E402
    AddressNotFoundError,
    AddressTooCoarseError,
    MireyeAuthError,
    MireyeClient,
    MireyeError,
    MireyeRetryableError,
    MireyeUnconfiguredError,
)
from mcp_server.narrate import narrate  # noqa: E402
from scorer.score import score, score_earthquake, score_flood  # noqa: E402

_CITY_STATE_RE = re.compile(r",\s*([A-Za-z .]+),\s*([A-Z]{2})(?:\s+\d{5}(?:-\d{4})?)?\s*$")

DEMO_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "demo_cache.json"

# Each hazard "sub-agent" is a (Mireye preset, deterministic scorer) pair —
# same fetch -> score -> narrate pipeline as wildfire, just pointed at a
# different Mireye preset and rule table. Adding a hazard means adding one
# entry here plus a scorer/*_rule_table.py, not touching the pipeline.
_HAZARD_PRESETS: dict[str, tuple[str, Any]] = {
    "wildfire": ("wildfire_underwrite", score),
    "flood": ("flood_risk", score_flood),
    "earthquake": ("natural_hazard", score_earthquake),
}

mcp = MCPServer(
    name="insurability-triage",
    version="0.1.0",
    description=(
        "Multi-hazard property risk triage for a US address — wildfire "
        "(California), flood (FEMA SFHA), and earthquake (USGS/ASCE seismic "
        "design category) verdicts, driving factors, and mitigation lists. "
        "Heuristic, not an actuarial or underwriting determination."
    ),
)


def _load_demo_cache() -> dict:
    if not DEMO_CACHE_PATH.exists():
        return {}
    with open(DEMO_CACHE_PATH) as f:
        data = json.load(f)
    data.pop("_comment", None)
    return data


def _fire_station_drive_time(client: MireyeClient, address: str) -> dict | None:
    """Best-effort: real driving time to the nearest fire station, not just
    straight-line distance — fire-response time is a real input to ISO
    Public Protection Classification, which insurers use in wildfire
    pricing. Never raises; returns None on any failure, since this is
    supplementary context, not required for a verdict."""
    try:
        station_fields = client.fetch_fields(
            address, ["nearest_fire_station_name", "nearest_fire_station_distance_m"]
        )
    except MireyeError:
        return None

    name_field = station_fields.get("fields", {}).get("nearest_fire_station_name", {})
    dist_field = station_fields.get("fields", {}).get("nearest_fire_station_distance_m", {})
    station_name = name_field.get("value")
    if not station_name or name_field.get("status") != "ok":
        return None

    match = _CITY_STATE_RE.search(address)
    destination = f"{station_name}, {match.group(1)}, {match.group(2)}" if match else station_name

    drive = client.proximity_drive_time(origin=address, destination=destination)
    if drive is None:
        return None

    return {
        "station_name": station_name,
        "straight_line_distance_m": dist_field.get("value"),
        "drive_minutes": drive["duration_minutes"],
        "drive_miles": drive["distance_miles"],
        "destination_match_confidence": drive["destination_accuracy"],
    }


def _resolve_and_fetch(
    address: str, preset: str = "wildfire_underwrite"
) -> tuple[dict, str, float | None, float | None]:
    """Try the live Mireye API; fall back to the demo cache on failure.

    `preset` selects which Mireye /v1/fetch preset to pull — one per hazard
    sub-agent (see _HAZARD_PRESETS). Returns (fetch_response, source, lat,
    lng) where source is "live" or "demo_cache". lat/lng are None only if
    geocoding itself failed (caller doesn't reach this far in that case —
    see the AddressTooCoarseError / AddressNotFoundError branches below).
    """
    try:
        with MireyeClient() as client:
            geo = client.geocode(address)
            fetch_response = client.fetch_with_retry(geo.lat, geo.lng, preset=preset)
            return fetch_response, "live", geo.lat, geo.lng
    except AddressTooCoarseError:
        raise
    except AddressNotFoundError:
        raise
    except (MireyeRetryableError, MireyeUnconfiguredError, MireyeAuthError, MireyeError):
        cache = _load_demo_cache()
        cached = cache.get(address)
        if cached:
            cached_geo = cached.get("geocode", {})
            # "fetch" (no suffix) is the legacy key for the wildfire preset,
            # kept as-is for backward compatibility; other presets live
            # under fetch_by_preset.
            cached_fetch = (
                cached["fetch"]
                if preset == "wildfire_underwrite"
                else cached.get("fetch_by_preset", {}).get(preset)
            )
            if cached_fetch:
                return (
                    cached_fetch,
                    "demo_cache",
                    cached_geo.get("lat"),
                    cached_geo.get("lng"),
                )
        raise


def _tool_check_insurability(
    address: str, overrides: dict[str, Any] | None = None, _enrich: bool = True
) -> dict:
    """_enrich controls whether the extra fire-station-drive-time and
    parcel-boundary lookups run (each is 1-2 more Mireye calls). On by
    default for a single-address deep dive; compare_addresses turns it
    off so a 6-address batch doesn't make 5x the API calls it needs to
    just produce a ranking."""
    try:
        fetch_response, source, lat, lng = _resolve_and_fetch(
            address, preset="wildfire_underwrite"
        )
    except AddressTooCoarseError:
        return {
            "address": address,
            "verdict": "low_confidence",
            "driving_factors": [],
            "mitigations": [],
            "data_sources": [],
            "missing_inputs": ["address"],
            "disclaimer": (
                "Address only resolves to a coarse (ZIP/city/county) centroid, "
                "not a specific parcel — provide a more precise street address."
            ),
            "narration": "This address is too coarse to place on a specific parcel.",
            "lat": None,
            "lng": None,
            "parcel_boundary_geojson": None,
            "parcel_apn": None,
            "fire_station": None,
        }
    except AddressNotFoundError:
        return {
            "address": address,
            "verdict": "low_confidence",
            "driving_factors": [],
            "mitigations": [],
            "data_sources": [],
            "missing_inputs": ["address"],
            "disclaimer": "Address could not be resolved to a location.",
            "narration": "This address could not be found.",
            "lat": None,
            "lng": None,
            "parcel_boundary_geojson": None,
            "parcel_apn": None,
            "fire_station": None,
        }
    except MireyeError as exc:
        return {
            "address": address,
            "verdict": "low_confidence",
            "driving_factors": [],
            "mitigations": [],
            "data_sources": [],
            "missing_inputs": [],
            "disclaimer": f"Mireye lookup failed and no demo-cache fallback matched: {exc}",
            "narration": "Live data is unavailable for this address right now.",
            "lat": None,
            "lng": None,
            "parcel_boundary_geojson": None,
            "parcel_apn": None,
            "fire_station": None,
        }

    result = score(fetch_response, overrides=overrides)
    result["data_source_mode"] = source
    result["address"] = address
    result["lat"] = lat
    result["lng"] = lng
    result["parcel_boundary_geojson"] = None
    result["parcel_apn"] = None
    result["fire_station"] = None

    if _enrich and source == "live":
        # Enrichment is pure upside — a bug or an unexpected response shape
        # here must never destroy a verdict that already scored correctly.
        # lookup_parcel/proximity_drive_time already return None on known
        # Mireye-level failures; this is the outer backstop for anything
        # else (including a bug in this code).
        try:
            with MireyeClient() as client:
                parcel = client.lookup_parcel(address)
                if parcel:
                    result["parcel_boundary_geojson"] = parcel.get("geometry")
                    result["parcel_apn"] = parcel.get("apn")

                fire_station = _fire_station_drive_time(client, address)
                if fire_station:
                    result["fire_station"] = fire_station
                    mins = fire_station["drive_minutes"]
                    result["driving_factors"].append(
                        f"Nearest fire station ({fire_station['station_name']}) is "
                        f"~{mins:.0f} min drive under typical conditions — informational "
                        f"only, not part of the verdict (response time isn't in the "
                        f"Safer From Wildfires rule table)."
                    )
        except Exception:  # noqa: BLE001 — enrichment must degrade, never take the verdict down with it
            pass

    result["narration"] = narrate(result)
    return result


@mcp.tool()
def check_insurability(address: str, overrides: dict[str, Any] | None = None) -> dict:
    """Wildfire insurability triage for a California street address.

    Args:
        address: A US street address, e.g. "5555 Skyway, Paradise, CA 95969".
        overrides: Optional hypothetical flags for counterfactual re-scoring,
            e.g. {"defensible_space_cleared": true} or {"home_hardened": true}.
            Used to answer follow-up questions like "what if I clear the
            brush?" by re-running the real scorer, never a free-floating guess.

    Returns:
        address, lat, lng, verdict, driving_factors, mitigations (each with
        a cost range and Safer From Wildfires recognition), data_sources,
        missing_inputs, disclaimer, a plain-English narration,
        parcel_boundary_geojson + parcel_apn (for mapping the actual
        parcel, not just a pin), and fire_station (real drive time to the
        nearest station — informational, not part of the verdict).
    """
    return _tool_check_insurability(address, overrides)


def _empty_check_result(address: str, disclaimer: str, narration: str) -> dict:
    """Shared shape for the address-resolution failure branches (too
    coarse, not found, Mireye unavailable) across all hazard sub-agents."""
    return {
        "address": address,
        "verdict": "low_confidence",
        "driving_factors": [],
        "mitigations": [],
        "data_sources": [],
        "missing_inputs": ["address"],
        "disclaimer": disclaimer,
        "narration": narration,
        "lat": None,
        "lng": None,
        "parcel_boundary_geojson": None,
        "parcel_apn": None,
    }


def _tool_check_hazard(address: str, hazard: str, _enrich: bool = True) -> dict:
    """Shared fetch -> score -> enrich -> narrate pipeline for the flood
    and earthquake sub-agents. check_insurability (wildfire) keeps its own
    version above since it additionally supports counterfactual overrides
    and fire-station drive time, which the other two hazards don't have."""
    preset, scorer = _HAZARD_PRESETS[hazard]
    try:
        fetch_response, source, lat, lng = _resolve_and_fetch(address, preset=preset)
    except AddressTooCoarseError:
        return _empty_check_result(
            address,
            "Address only resolves to a coarse (ZIP/city/county) centroid, "
            "not a specific parcel — provide a more precise street address.",
            "This address is too coarse to place on a specific parcel.",
        )
    except AddressNotFoundError:
        return _empty_check_result(
            address,
            "Address could not be resolved to a location.",
            "This address could not be found.",
        )
    except MireyeError as exc:
        return _empty_check_result(
            address,
            f"Mireye lookup failed and no demo-cache fallback matched: {exc}",
            "Live data is unavailable for this address right now.",
        )

    result = scorer(fetch_response)
    result["data_source_mode"] = source
    result["address"] = address
    result["lat"] = lat
    result["lng"] = lng
    result["parcel_boundary_geojson"] = None
    result["parcel_apn"] = None

    if _enrich and source == "live":
        # Same enrichment-must-degrade-not-destroy contract as
        # check_insurability above.
        try:
            with MireyeClient() as client:
                parcel = client.lookup_parcel(address)
                if parcel:
                    result["parcel_boundary_geojson"] = parcel.get("geometry")
                    result["parcel_apn"] = parcel.get("apn")
        except Exception:  # noqa: BLE001
            pass

    result["narration"] = narrate(result)
    return result


def _tool_check_flood_risk(address: str, _enrich: bool = True) -> dict:
    """Flood insurability triage for a US street address — verdict driven
    by whether the parcel sits inside a FEMA Special Flood Hazard Area,
    the National Flood Insurance Program's mandatory-purchase trigger."""
    return _tool_check_hazard(address, "flood", _enrich=_enrich)


def _tool_check_earthquake_risk(address: str, _enrich: bool = True) -> dict:
    """Earthquake insurability triage for a US street address — verdict
    driven by ASCE 7-22 Seismic Design Category at the parcel."""
    return _tool_check_hazard(address, "earthquake", _enrich=_enrich)


@mcp.tool()
def check_flood_risk(address: str) -> dict:
    """Flood insurability triage for a single US street address.

    Args:
        address: A US street address, e.g. "100 Ocean Dr, Miami Beach, FL 33139".

    Returns:
        address, lat, lng, verdict, driving_factors, a ranked flood-
        mitigation list with cost ranges, data_sources, missing_inputs,
        disclaimer, a plain-English narration, and parcel_boundary_geojson
        + parcel_apn for mapping. Verdict is driven by whether the parcel
        is inside a FEMA Special Flood Hazard Area (SFHA) — the NFIP's
        mandatory flood-insurance-purchase trigger for federally-backed
        mortgages, not a California-only concept.
    """
    return _tool_check_flood_risk(address)


@mcp.tool()
def check_earthquake_risk(address: str) -> dict:
    """Earthquake insurability triage for a single US street address.

    Args:
        address: A US street address, e.g. "100 Ocean Dr, Miami Beach, FL 33139".

    Returns:
        address, lat, lng, verdict, driving_factors, a ranked seismic-
        retrofit mitigation list with cost ranges, data_sources,
        missing_inputs, disclaimer, a plain-English narration, and
        parcel_boundary_geojson + parcel_apn for mapping. Verdict is
        driven by ASCE 7-22 Seismic Design Category (A-F) at the parcel —
        a building-code classification, not an insurance-purchase mandate
        (California has no legal requirement to carry earthquake coverage).
    """
    return _tool_check_earthquake_risk(address)


# Verdict severity, most to least concerning — drives compare_addresses'
# ranking. out_of_scope/low_confidence aren't "low risk", they're "no
# answer" — sorted last, not treated as good news.
_VERDICT_SEVERITY = {
    "likely_hard_to_place": 0,
    "harder_to_place": 1,
    "likely_insurable": 2,
    "low_confidence": 3,
    "out_of_scope": 4,
}


def _tool_compare_addresses(addresses: list[str]) -> dict:
    """Check multiple addresses and rank them by insurability risk —
    reuses check_insurability's exact pipeline per address (including the
    demo-cache fallback), so nothing is duplicated. Powers both the
    "compare these two" and "scan my listing book" use cases with the
    same tool, since they're the same operation at different N."""
    if not addresses:
        return {"results": [], "summary": "No addresses provided."}

    results = []
    for address in addresses:
        r = _tool_check_insurability(address, _enrich=False)
        results.append(
            {
                "address": address,
                "verdict": r["verdict"],
                "lat": r.get("lat"),
                "lng": r.get("lng"),
                "top_driving_factor": r["driving_factors"][0] if r["driving_factors"] else None,
                "cheapest_mitigation": (
                    min(
                        (m for m in r["mitigations"] if m.get("est_cost_usd")),
                        # Midpoint, not the low end — a $0-2000 range isn't
                        # "cheaper" than a tight $100-500 range just because
                        # its floor is lower; the typical cost is what matters.
                        key=lambda m: sum(m["est_cost_usd"]) / 2,
                        default=None,
                    )
                    if r["mitigations"]
                    else None
                ),
                "data_source_mode": r.get("data_source_mode"),
            }
        )

    results.sort(key=lambda r: _VERDICT_SEVERITY.get(r["verdict"], 99))

    counts: dict[str, int] = {}
    for r in results:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    summary = f"{len(results)} addresses checked: " + ", ".join(
        f"{n} {v.replace('_', ' ')}" for v, n in counts.items()
    )

    return {
        "results": results,
        "ranked_by": "risk (most concerning first)",
        "summary": summary,
        "disclaimer": (
            "Heuristic verdicts from public hazard/mitigation data, not "
            "actuarial or underwriting determinations."
        ),
    }


@mcp.tool()
def compare_addresses(addresses: list[str]) -> dict:
    """Check and rank multiple California addresses by wildfire
    insurability risk — same underlying check as check_insurability, run
    across a list. Use for "compare these addresses" or "scan my listing
    book" requests; use check_insurability for a single address in depth.

    Args:
        addresses: A list of US street addresses (2 or more).

    Returns:
        results (one summary entry per address: verdict, top driving
        factor, cheapest mitigation, lat/lng), ranked_by, summary, and a
        disclaimer.
    """
    return _tool_compare_addresses(addresses)


def _tool_full_risk_report(address: str) -> dict:
    """Runs all three hazard sub-agents (wildfire, flood, earthquake) for
    one address and combines them into a single report. Each sub-agent
    keeps its own independent deterministic scorer and rule table — this
    function only orchestrates and picks the overall verdict, it never
    re-derives or overrides a per-hazard verdict itself."""
    wildfire = _tool_check_insurability(address, _enrich=False)
    flood = _tool_check_flood_risk(address, _enrich=False)
    earthquake = _tool_check_earthquake_risk(address, _enrich=False)

    per_hazard = [
        {
            "hazard": hazard,
            "verdict": r["verdict"],
            "top_driving_factor": r["driving_factors"][0] if r["driving_factors"] else None,
            "narration": r.get("narration"),
        }
        for hazard, r in (("wildfire", wildfire), ("flood", flood), ("earthquake", earthquake))
    ]

    # Overall verdict is the single worst real per-hazard verdict — the
    # most concerning hazard drives insurability, not an average across
    # three unrelated risk models. low_confidence/out_of_scope hazards are
    # excluded from that comparison (they're "no answer", not "good news"
    # — same reasoning _VERDICT_SEVERITY already encodes for compare_addresses).
    real_verdicts = [
        h["verdict"] for h in per_hazard if h["verdict"] not in ("low_confidence", "out_of_scope")
    ]
    overall_verdict = (
        min(real_verdicts, key=lambda v: _VERDICT_SEVERITY.get(v, 99))
        if real_verdicts
        else "low_confidence"
    )

    concerning = [h["hazard"] for h in per_hazard if h["verdict"] in ("likely_hard_to_place", "harder_to_place")]
    summary = (
        f"{', '.join(concerning) or 'no hazard'} driving the overall verdict "
        f"({overall_verdict.replace('_', ' ')})"
    )

    return {
        "address": address,
        "lat": wildfire.get("lat"),
        "lng": wildfire.get("lng"),
        "overall_verdict": overall_verdict,
        "hazards": per_hazard,
        "summary": summary,
        "disclaimer": (
            "Heuristic verdicts from three independent public-data sub-agents "
            "(wildfire, flood, earthquake) — not actuarial or underwriting "
            "determinations. Not a guarantee of insurability, non-renewal, or pricing."
        ),
    }


@mcp.tool()
def full_risk_report(address: str) -> dict:
    """Combined multi-hazard property risk report for a single US street
    address — runs the wildfire, flood, and earthquake sub-agents and
    returns one overall verdict plus each hazard's own verdict and top
    driving factor. Use this instead of calling check_insurability,
    check_flood_risk, and check_earthquake_risk separately when the user
    wants the full picture on a property rather than one specific hazard.

    Args:
        address: A US street address.

    Returns:
        address, lat, lng, overall_verdict (the worst of the three
        per-hazard verdicts), hazards (one entry per hazard: verdict, top
        driving factor, narration), summary, and a disclaimer.
    """
    return _tool_full_risk_report(address)


def _tool_ask_about_location(address: str, question: str) -> dict:
    """Answers a question about a location that's OUTSIDE what the three
    hazard scorers cover (schools, demographics, nearby amenities, etc.)
    via Mireye's /v1/ask. Deliberately separate from
    check_insurability/check_flood_risk/check_earthquake_risk/
    compare_addresses/full_risk_report: this answer must never feed a
    verdict — it has its own citations/confidence, not a scorer's."""
    try:
        with MireyeClient() as client:
            result = client.ask(address, question)
    except MireyeError:
        result = None

    if result is None:
        return {
            "answer": "Couldn't reach Mireye's Q&A for this question right now.",
            "confidence": None,
            "citations": [],
            "data_gaps": [],
        }

    return {
        "answer": result.get("answer"),
        "confidence": result.get("confidence"),
        "citations": result.get("citations", []),
        "data_gaps": result.get("data_gaps", []),
    }


@mcp.tool()
def ask_about_location(address: str, question: str) -> dict:
    """Answers an open-ended question about a US address that is NOT about
    wildfire, flood, or earthquake insurability risk (e.g. schools,
    demographics, nearby amenities). Do not use this for anything that
    should inform a hazard verdict — use check_insurability,
    check_flood_risk, check_earthquake_risk, or full_risk_report for that;
    this tool's answer is separate, citation-backed context, never a
    scoring input.

    Args:
        address: A US street address.
        question: The open-ended question to ask about that location.

    Returns:
        answer, confidence, citations (source + fields used), and
        data_gaps (what the question asked for that Mireye doesn't have).
    """
    return _tool_ask_about_location(address, question)


if __name__ == "__main__":
    mcp.run()
