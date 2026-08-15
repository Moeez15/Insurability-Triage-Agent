"""Declarative verdict rule table (CQ-1).

Keyed on (fire_hazard_severity_zone_class, fire_hazard_responsibility_area)
so every combination is independently testable and the SRA/LRA legal
distinction (Arch-2/Premise 4) is data, not buried in conditionals:

  SRA: all three classes (Moderate/High/Very High) are statutory under
  California Public Resources Code 4201-4204 — no local override.

  LRA: only Very High is statutory (Chapter 7A building code, defensible-
  space enforcement, Civil Code 1103 disclosure). Moderate and High in
  LRA are CAL FIRE's informational model output, not a legal trigger —
  so they score lower than their SRA counterparts.

Verdict labels describe new-business insurability difficulty for a BUYER,
never non-renewal of an existing policy (Premise 7 — a different legal
concept the plan originally conflated).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuleRow:
    verdict: str
    statutory: bool
    rationale: str


# (fire_hazard_severity_zone_class, fire_hazard_responsibility_area) -> RuleRow
RULE_TABLE: dict[tuple[str, str], RuleRow] = {
    ("Non-Wildland", "SRA"): RuleRow(
        "likely_insurable", True,
        "Non-Wildland is a real classification (low-fuel/urban/agriculture), not missing data.",
    ),
    ("Non-Wildland", "LRA"): RuleRow(
        "likely_insurable", True,
        "Non-Wildland is a real classification (low-fuel/urban/agriculture), not missing data.",
    ),
    ("Moderate", "SRA"): RuleRow(
        "harder_to_place", True,
        "SRA: all three classes are the statutory zone under PRC 4201-4204.",
    ),
    ("Moderate", "LRA"): RuleRow(
        "likely_insurable", False,
        "LRA Moderate is CAL FIRE's informational model output, not a statutory trigger.",
    ),
    ("High", "SRA"): RuleRow(
        "likely_hard_to_place", True,
        "SRA: all three classes are the statutory zone under PRC 4201-4204.",
    ),
    ("High", "LRA"): RuleRow(
        "harder_to_place", False,
        "LRA High is CAL FIRE's informational model output, not a statutory trigger — "
        "still a real physical signal worth surfacing, just not legally binding.",
    ),
    ("Very High", "SRA"): RuleRow(
        "likely_hard_to_place", True,
        "SRA: all three classes are the statutory zone under PRC 4201-4204.",
    ),
    ("Very High", "LRA"): RuleRow(
        "likely_hard_to_place", True,
        "LRA Very High is the one LRA class that IS statutory "
        "(Chapter 7A, defensible-space enforcement, Civil Code 1103 disclosure).",
    ),
}

# When a counterfactual override says defensible space is fully cleared and
# hardening is done, soften the verdict one tier — never below what the raw
# hazard class implies is possible, and only for the counterfactual path
# (Approach C / overrides), never as the default verdict for an unverified
# property (Test/Arch gap decision — the agent cannot see structure-level
# mitigation from Mireye's data alone).
VERDICT_SOFTEN_ONE_TIER = {
    "likely_hard_to_place": "harder_to_place",
    "harder_to_place": "likely_insurable",
    "likely_insurable": "likely_insurable",
}


def lookup(zone_class: str | None, responsibility_area: str | None) -> RuleRow | None:
    if zone_class is None or responsibility_area is None:
        return None
    return RULE_TABLE.get((zone_class, responsibility_area))
