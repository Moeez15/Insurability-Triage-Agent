"""MCP server exposing `check_insurability` as a plain MCP tool.

No custom agent-loop framework (Premise 8) — whatever MCP host is
connected (Claude Desktop, Claude Code, etc.) already handles multi-turn
conversation and re-invokes this tool with follow-up `overrides` when a
user asks a hypothetical like "what if I clear the brush?".
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
from scorer.score import score  # noqa: E402

_CITY_STATE_RE = re.compile(r",\s*([A-Za-z .]+),\s*([A-Z]{2})(?:\s+\d{5}(?:-\d{4})?)?\s*$")

DEMO_CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "demo_cache.json"

mcp = MCPServer(
    name="insurability-triage",
    version="0.1.0",
    description=(
        "Wildfire insurability triage for a California address — verdict, "
        "driving factors, and a ranked Safer From Wildfires mitigation list. "
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


def _resolve_and_fetch(address: str) -> tuple[dict, str, float | None, float | None]:
    """Try the live Mireye API; fall back to the demo cache on failure.

    Returns (fetch_response, source, lat, lng) where source is "live" or
    "demo_cache". lat/lng are None only if geocoding itself failed (caller
    doesn't reach this far in that case — see the AddressTooCoarseError /
    AddressNotFoundError branches in _tool_check_insurability).
    """
    try:
        with MireyeClient() as client:
            geo = client.geocode(address)
            fetch_response = client.fetch_with_retry(
                geo.lat, geo.lng, preset="wildfire_underwrite"
            )
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
            return (
                cached["fetch"],
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
        fetch_response, source, lat, lng = _resolve_and_fetch(address)
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


def _tool_ask_about_location(address: str, question: str) -> dict:
    """Answers a question about a location that's OUTSIDE what the
    insurability scorer covers (schools, demographics, flood zone detail,
    etc.) via Mireye's /v1/ask. Deliberately separate from
    check_insurability/compare_addresses: this answer must never feed the
    verdict — it has its own citations/confidence, not the scorer's."""
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
    """Answers an open-ended question about a California address that is
    NOT about wildfire insurability risk (e.g. schools, demographics,
    flood zone detail, nearby amenities). Do not use this for anything
    that should inform an insurability verdict — use check_insurability
    or compare_addresses for that; this tool's answer is separate,
    citation-backed context, never a scoring input.

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
