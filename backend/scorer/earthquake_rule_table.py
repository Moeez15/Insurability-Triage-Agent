"""Declarative earthquake verdict rule table.

Keyed on ASCE 7-22 Seismic Design Category (A-F), Mireye's
`seismic_design_category` field — a single code-mandated classification
that already synthesizes ground motion (PGA), site soil class, and risk
category into one categorical value, the same shape of hook the wildfire
scorer uses for FHSZ class.

Unlike wildfire's FHSZ (CA disclosure law) or flood's SFHA (NFIP purchase
mandate), SDC is a *building-code* trigger, not an insurance-purchase
mandate — California has no legal requirement to carry earthquake
insurance (CEA coverage is optional). `statutory` here means "this
category triggers mandatory seismic design/construction provisions under
IBC/ASCE 7", not "insurance is legally required" — the rationale text
below is explicit about that distinction so nothing overstates it.
"""

from __future__ import annotations

from scorer.rule_table import RuleRow

# seismic_design_category -> RuleRow
EARTHQUAKE_RULE_TABLE: dict[str, RuleRow] = {
    "A": RuleRow(
        "likely_insurable", False,
        "SDC A — minimal seismic hazard, standard design provisions apply.",
    ),
    "B": RuleRow(
        "likely_insurable", False,
        "SDC B — low-to-moderate seismic hazard, standard design provisions apply.",
    ),
    "C": RuleRow(
        "likely_insurable", False,
        "SDC C — moderate seismic hazard, standard design provisions apply.",
    ),
    "D": RuleRow(
        "harder_to_place", True,
        "SDC D triggers mandatory seismic design provisions under ASCE 7/IBC "
        "— a real code-mandated construction requirement, not an insurance "
        "purchase mandate.",
    ),
    "E": RuleRow(
        "likely_hard_to_place", True,
        "SDC E — near-fault/high-hazard sites, the most stringent seismic "
        "design provisions under ASCE 7/IBC apply.",
    ),
    "F": RuleRow(
        "likely_hard_to_place", True,
        "SDC F — reserved for essential/high-risk facilities on the highest-"
        "hazard sites, the most stringent seismic design provisions apply.",
    ),
}


def lookup(seismic_design_category: str | None) -> RuleRow | None:
    if seismic_design_category is None:
        return None
    return EARTHQUAKE_RULE_TABLE.get(seismic_design_category)
