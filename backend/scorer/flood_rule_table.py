"""Declarative flood verdict rule table.

Keyed on a single boolean — Mireye's `within_floodplain_polygon` field,
live-verified to track FEMA NFHL's SFHA_TF flag exactly (confirmed against
a Zone AE Miami Beach address returning True and multiple Zone X addresses
returning False). That flag is the real legal hook: a property inside a
Special Flood Hazard Area (SFHA) is subject to the National Flood Insurance
Program's mandatory-purchase requirement for any federally-backed mortgage
(42 U.S.C. Sec. 4012a) — the same kind of statutory trigger the wildfire
scorer keys on for FHSZ, just a federal one instead of a California one.
"""

from __future__ import annotations

from scorer.rule_table import RuleRow

# within_floodplain_polygon (True = inside a FEMA Special Flood Hazard Area) -> RuleRow
FLOOD_RULE_TABLE: dict[bool, RuleRow] = {
    True: RuleRow(
        "likely_hard_to_place",
        True,
        "Inside a FEMA Special Flood Hazard Area (SFHA) — the National Flood "
        "Insurance Program's mandatory-purchase requirement applies to any "
        "federally-backed mortgage on this property (42 U.S.C. Sec. 4012a).",
    ),
    False: RuleRow(
        "likely_insurable",
        False,
        "Outside FEMA's mapped Special Flood Hazard Area — flood insurance "
        "is optional here, not a purchase-mandate trigger. FEMA notes a "
        "meaningful share of claims still come from outside mapped SFHAs, "
        "so this is not a finding of zero flood risk.",
    ),
}


def lookup(within_sfha: bool | None) -> RuleRow | None:
    if within_sfha is None:
        return None
    return FLOOD_RULE_TABLE.get(bool(within_sfha))
