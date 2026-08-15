import pytest

from scorer import earthquake_rule_table, flood_rule_table
from scorer.rule_table import RULE_TABLE, lookup
from scorer.score import score, score_earthquake, score_flood
from tests.fixtures import (
    EARTHQUAKE_TRANSIENT_FAILURE_FETCH,
    EVERGREEN_CO_FETCH,
    FLOOD_TRANSIENT_FAILURE_FETCH,
    FRA_WITHIN_CA_FETCH,
    GUERNEVILLE_FLOOD_FETCH,
    MIAMI_BEACH_EARTHQUAKE_FETCH,
    MIAMI_BEACH_FLOOD_FETCH,
    PARADISE_CA_FETCH,
    PARADISE_EARTHQUAKE_FETCH,
    TRANSIENT_FAILURE_FETCH,
)


class TestRuleTable:
    def test_all_eight_combinations_present(self):
        classes = ["Non-Wildland", "Moderate", "High", "Very High"]
        areas = ["SRA", "LRA"]
        for c in classes:
            for a in areas:
                assert (c, a) in RULE_TABLE, f"missing rule for ({c}, {a})"

    def test_sra_moderate_is_statutory(self):
        assert lookup("Moderate", "SRA").statutory is True

    def test_lra_moderate_is_not_statutory(self):
        assert lookup("Moderate", "LRA").statutory is False

    def test_lra_high_is_not_statutory(self):
        assert lookup("High", "LRA").statutory is False

    def test_lra_very_high_is_statutory(self):
        # The one LRA class that IS statutory (Arch-2 finding).
        assert lookup("Very High", "LRA").statutory is True

    def test_sra_and_lra_moderate_score_differently(self):
        sra = lookup("Moderate", "SRA").verdict
        lra = lookup("Moderate", "LRA").verdict
        assert sra != lra, "LRA Moderate (informational) must not score like SRA Moderate (statutory)"

    def test_unknown_combination_returns_none(self):
        assert lookup("Extreme", "SRA") is None
        assert lookup(None, "SRA") is None
        assert lookup("High", None) is None


class TestScorePaddisonAndEvergreen:
    def test_paradise_ca_very_high_lra_is_hard_to_place(self):
        result = score(PARADISE_CA_FETCH)
        assert result["verdict"] == "likely_hard_to_place"
        assert "CALFIRE_FHSZ" in result["data_sources"]
        assert result["mitigations"], "should list mitigation actions"

    def test_evergreen_co_out_of_scope(self):
        result = score(EVERGREEN_CO_FETCH)
        assert result["verdict"] == "out_of_scope"
        assert result["mitigations"] == []

    def test_fra_within_ca_is_low_confidence_not_out_of_scope(self):
        result = score(FRA_WITHIN_CA_FETCH)
        assert result["verdict"] == "low_confidence"
        assert "missing_inputs" in result

    def test_transient_failure_is_low_confidence(self):
        result = score(TRANSIENT_FAILURE_FETCH)
        assert result["verdict"] == "low_confidence"


class TestCounterfactualOverrides:
    def test_defensible_space_cleared_softens_verdict(self):
        baseline = score(PARADISE_CA_FETCH)
        countered = score(PARADISE_CA_FETCH, overrides={"defensible_space_cleared": True})
        assert countered["verdict"] != baseline["verdict"] or baseline["verdict"] == "likely_insurable"

    def test_override_excludes_covered_mitigations(self):
        result = score(PARADISE_CA_FETCH, overrides={"defensible_space_cleared": True})
        actions = [m["action"] for m in result["mitigations"]]
        assert "PRC 4291 defensible space compliance" not in actions

    def test_override_is_never_silent(self):
        result = score(PARADISE_CA_FETCH, overrides={"defensible_space_cleared": True})
        assert any("Counterfactual" in f for f in result["driving_factors"])

    def test_no_override_keeps_all_mitigations(self):
        result = score(PARADISE_CA_FETCH)
        actions = [m["action"] for m in result["mitigations"]]
        assert "PRC 4291 defensible space compliance" in actions


class TestMitigationCostGaps:
    def test_community_level_actions_have_no_fabricated_cost(self):
        result = score(PARADISE_CA_FETCH)
        community_actions = [
            m for m in result["mitigations"]
            if m["action"] in ("Fire Risk Reduction Community designation", "Firewise USA site in good standing")
        ]
        assert community_actions
        for action in community_actions:
            assert action["est_cost_usd"] is None, "community-level actions must not have a fabricated cost"

    def test_priced_actions_have_a_range(self):
        result = score(PARADISE_CA_FETCH)
        priced = [m for m in result["mitigations"] if m["action"] == "Spark arrestor on chimney"]
        assert priced
        assert priced[0]["est_cost_usd"] == [100, 500]


class TestFloodRuleTable:
    def test_both_sfha_states_present(self):
        assert True in flood_rule_table.FLOOD_RULE_TABLE
        assert False in flood_rule_table.FLOOD_RULE_TABLE

    def test_within_sfha_is_statutory(self):
        # NFIP mandatory-purchase trigger for federally-backed mortgages.
        assert flood_rule_table.lookup(True).statutory is True

    def test_outside_sfha_is_not_statutory(self):
        assert flood_rule_table.lookup(False).statutory is False

    def test_within_sfha_scores_worse_than_outside(self):
        inside = flood_rule_table.lookup(True).verdict
        outside = flood_rule_table.lookup(False).verdict
        assert inside != outside

    def test_lookup_none_returns_none(self):
        assert flood_rule_table.lookup(None) is None


class TestScoreFlood:
    def test_sfha_is_likely_hard_to_place(self):
        result = score_flood(MIAMI_BEACH_FLOOD_FETCH)
        assert result["verdict"] == "likely_hard_to_place"
        assert "FEMA_NFHL" in result["data_sources"]
        assert result["mitigations"], "should list flood mitigation actions"

    def test_outside_sfha_is_likely_insurable(self):
        result = score_flood(GUERNEVILLE_FLOOD_FETCH)
        assert result["verdict"] == "likely_insurable"

    def test_transient_failure_is_low_confidence(self):
        result = score_flood(FLOOD_TRANSIENT_FAILURE_FETCH)
        assert result["verdict"] == "low_confidence"

    def test_driving_factors_mention_sfha_not_wildfire(self):
        result = score_flood(MIAMI_BEACH_FLOOD_FETCH)
        joined = " ".join(result["driving_factors"])
        assert "Special Flood Hazard Area" in joined
        assert "fire" not in joined.lower()

    def test_mitigations_have_real_cost_ranges(self):
        result = score_flood(MIAMI_BEACH_FLOOD_FETCH)
        actions = {m["action"]: m["est_cost_usd"] for m in result["mitigations"]}
        assert actions["Elevate utilities/mechanicals above Base Flood Elevation"] == [5000, 20000]


class TestEarthquakeRuleTable:
    def test_all_six_categories_present(self):
        for cat in ["A", "B", "C", "D", "E", "F"]:
            assert cat in earthquake_rule_table.EARTHQUAKE_RULE_TABLE, f"missing rule for SDC {cat}"

    def test_low_categories_not_statutory(self):
        for cat in ["A", "B", "C"]:
            assert earthquake_rule_table.lookup(cat).statutory is False

    def test_high_categories_are_statutory(self):
        for cat in ["D", "E", "F"]:
            assert earthquake_rule_table.lookup(cat).statutory is True

    def test_severity_increases_with_category(self):
        low = earthquake_rule_table.lookup("A").verdict
        high = earthquake_rule_table.lookup("F").verdict
        assert low != high

    def test_unknown_category_returns_none(self):
        assert earthquake_rule_table.lookup("Z") is None
        assert earthquake_rule_table.lookup(None) is None


class TestScoreEarthquake:
    def test_sdc_d_is_harder_to_place(self):
        result = score_earthquake(PARADISE_EARTHQUAKE_FETCH)
        assert result["verdict"] == "harder_to_place"
        assert "USGS_DESIGNMAPS_ASCE7" in result["data_sources"]
        assert result["mitigations"], "should list seismic retrofit actions"

    def test_sdc_a_is_likely_insurable(self):
        result = score_earthquake(MIAMI_BEACH_EARTHQUAKE_FETCH)
        assert result["verdict"] == "likely_insurable"

    def test_transient_failure_is_low_confidence(self):
        result = score_earthquake(EARTHQUAKE_TRANSIENT_FAILURE_FETCH)
        assert result["verdict"] == "low_confidence"

    def test_driving_factors_mention_seismic_not_wildfire(self):
        result = score_earthquake(PARADISE_EARTHQUAKE_FETCH)
        joined = " ".join(result["driving_factors"])
        assert "Seismic Design Category" in joined
        assert "fire" not in joined.lower()

    def test_pga_included_as_context_when_present(self):
        result = score_earthquake(PARADISE_EARTHQUAKE_FETCH)
        joined = " ".join(result["driving_factors"])
        assert "ground acceleration" in joined.lower()
