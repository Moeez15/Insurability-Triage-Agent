"""Deterministic scorer: Mireye fields -> structured verdict.

No LLM involved here (verdict pipeline split, Approach A) — reproducible
and auditable. `mcp_server/narrate.py` turns this module's output into
plain English and must never introduce a factor this module didn't emit.
"""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

import yaml

from scorer.rule_table import VERDICT_SOFTEN_ONE_TIER, lookup

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@functools.lru_cache(maxsize=1)
def _load_actions() -> dict:
    with open(DATA_DIR / "safer_from_wildfires_actions.yaml") as f:
        return yaml.safe_load(f)


@functools.lru_cache(maxsize=1)
def _load_costs() -> dict:
    with open(DATA_DIR / "mitigation_costs.yaml") as f:
        return yaml.safe_load(f)


def _all_actions() -> list[dict]:
    actions = _load_actions()
    out = []
    for cat in actions["categories"].values():
        out.extend(cat["actions"])
    return out


def _mitigation_list(exclude_action_ids: set[str]) -> list[dict]:
    """Every Safer From Wildfires action not already covered by an override,
    each tagged with its cost range (or an explicit gap if none exists)."""
    costs = _load_costs()["costs_usd"]
    result = []
    for action in _all_actions():
        if action["id"] in exclude_action_ids:
            continue
        cost = costs.get(action["id"], {})
        low, high = cost.get("low"), cost.get("high")
        result.append(
            {
                "action": action["name"],
                "est_cost_usd": [low, high] if low is not None else None,
                "cost_note": cost.get("note", "no cost data available — explicit gap"),
                "safer_from_wildfires_recognized": True,
            }
        )
    return result


def _field(fields: dict, name: str) -> dict:
    return fields.get(name, {"value": None, "status": "absent", "retryable": False})


def score(mireye_fetch_response: dict, overrides: dict[str, Any] | None = None) -> dict:
    """Score a Mireye /v1/fetch(preset="wildfire_underwrite") response.

    `overrides` (e.g. {"defensible_space_cleared": True}) powers grounded
    counterfactual re-scoring for Approach C follow-ups — never a free LLM
    guess. It is also the only way this design can account for mitigation
    already done, since Mireye's fields carry no structure-level signal.
    """
    overrides = overrides or {}
    fields = mireye_fetch_response.get("fields", {})

    zone_field = _field(fields, "fire_hazard_severity_zone_class")
    area_field = _field(fields, "fire_hazard_responsibility_area")

    data_sources = sorted(
        {f.get("source") for f in fields.values() if f.get("source")}
    )
    missing_inputs = [
        name for name, f in fields.items() if f.get("status") != "ok"
    ]

    # --- out_of_scope / low_confidence per Data Gaps & Fallbacks (Arch-4) ---
    if zone_field["status"] == "absent" and area_field["status"] == "absent":
        notes = (zone_field.get("notes") or "") + (area_field.get("notes") or "")
        if "outside california" in notes.lower():
            return {
                "verdict": "out_of_scope",
                "driving_factors": ["Address is outside California."],
                "mitigations": [],
                "data_sources": data_sources,
                "missing_inputs": missing_inputs,
                "disclaimer": (
                    "Coverage not available outside California yet — CAL FIRE's "
                    "Fire Hazard Severity Zone data is a California-only regulatory "
                    "product, not evidence of low wildfire hazard elsewhere."
                ),
            }
        return {
            "verdict": "low_confidence",
            "driving_factors": [
                "No CAL FIRE hazard-zone classification at this point — likely "
                "Federal Responsibility Area land (CAL FIRE has no statutory "
                "mandate to zone it). This is a jurisdiction artifact, not a "
                "finding of low hazard."
            ],
            "mitigations": [],
            "data_sources": data_sources,
            "missing_inputs": missing_inputs,
            "disclaimer": (
                "Hazard-zone data unavailable at this point; verdict is not based "
                "on a confirmed low-hazard finding."
            ),
        }

    if zone_field["status"] == "failed" or area_field["status"] == "failed":
        return {
            "verdict": "low_confidence",
            "driving_factors": ["Mireye returned a transient error for hazard-zone data."],
            "mitigations": [],
            "data_sources": data_sources,
            "missing_inputs": missing_inputs,
            "disclaimer": "Hazard-zone lookup failed after retry — verdict is not reliable.",
        }

    zone_class = zone_field["value"]
    area = area_field["value"]
    row = lookup(zone_class, area)
    if row is None:
        return {
            "verdict": "low_confidence",
            "driving_factors": [
                f"Unrecognized (class={zone_class!r}, area={area!r}) combination "
                "— not in the scoring rule table."
            ],
            "mitigations": [],
            "data_sources": data_sources,
            "missing_inputs": missing_inputs,
            "disclaimer": "Hazard classification did not match a known rule — verdict is not reliable.",
        }

    verdict = row.verdict

    # --- counterfactual override (Approach C follow-ups) ---
    exclude_action_ids: set[str] = set()
    driving_factors = [
        f"{zone_class} fire hazard severity zone in {area} "
        f"({'statutory' if row.statutory else 'informational, not statutory'}). "
        f"{row.rationale}"
    ]

    if overrides.get("defensible_space_cleared"):
        verdict = VERDICT_SOFTEN_ONE_TIER.get(verdict, verdict)
        exclude_action_ids |= {
            "prc_4291_compliance",
            "noncombustible_wall_base_clearance",
            "combustible_structure_30ft_removal",
        }
        driving_factors.append(
            "Counterfactual: defensible_space_cleared=True assumed — verdict "
            "softened one tier and defensible-space actions removed from the "
            "mitigation list. This is a hypothetical, not a verified finding."
        )

    if overrides.get("home_hardened"):
        verdict = VERDICT_SOFTEN_ONE_TIER.get(verdict, verdict)
        exclude_action_ids |= {
            "class_a_roof",
            "enclosed_eaves",
            "ember_resistant_vents",
            "multipane_windows",
            "fire_resistant_siding",
            "spark_arrestor_chimney",
        }
        driving_factors.append(
            "Counterfactual: home_hardened=True assumed — verdict softened one "
            "tier and home-hardening actions removed from the mitigation list. "
            "This is a hypothetical, not a verified finding."
        )

    return {
        "verdict": verdict,
        "driving_factors": driving_factors,
        "mitigations": _mitigation_list(exclude_action_ids),
        "data_sources": data_sources,
        "missing_inputs": missing_inputs,
        "disclaimer": (
            "Heuristic verdict from public hazard-zone and mitigation-regulation "
            "data, not an actuarial or underwriting determination. Not a guarantee "
            "of insurability, non-renewal, or pricing."
        ),
    }
