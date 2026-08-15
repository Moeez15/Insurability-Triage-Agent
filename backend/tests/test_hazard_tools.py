import pytest

from tools.narrate import narrate
from tools.hazard_tools import (
    _resolve_and_fetch,
    _tool_ask_about_location,
    _tool_check_earthquake_risk,
    _tool_check_flood_risk,
    _tool_check_insurability,
    _tool_compare_addresses,
    _tool_full_risk_report,
)
from mireye_client.client import GeocodeResult, MireyeRetryableError
from tests.fixtures import (
    EVERGREEN_CO_FETCH,
    GUERNEVILLE_FLOOD_FETCH,
    LOW_RISK_CA_FETCH,
    MIAMI_BEACH_FLOOD_FETCH,
    PARADISE_CA_FETCH,
    PARADISE_EARTHQUAKE_FETCH,
)


class TestNarrationFallback:
    def test_falls_back_without_api_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        scorer_output = {
            "verdict": "likely_hard_to_place",
            "driving_factors": ["Very High in LRA"],
            "mitigations": [{"action": "Spark arrestor on chimney"}],
            "disclaimer": "Heuristic, not actuarial.",
        }
        text = narrate(scorer_output)
        assert "Narration unavailable" in text
        assert "likely_hard_to_place" in text
        assert "Heuristic, not actuarial." in text

    def test_fallback_never_crashes_on_empty_output(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        text = narrate({})
        assert "Narration unavailable" in text


class TestDemoCacheFallback:
    def test_falls_back_to_cache_on_retryable_mireye_error(self, monkeypatch):
        def fake_resolve(address):
            raise MireyeRetryableError("simulated live outage")

        # Patch the live path to always fail, forcing the cache path.
        import tools.hazard_tools as tools_mod

        class FakeClient:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                pass

            def geocode(self, address):
                raise MireyeRetryableError("simulated live outage")

        monkeypatch.setattr(tools_mod, "MireyeClient", lambda: FakeClient())

        fetch_response, source, lat, lng = _resolve_and_fetch("5555 Skyway, Paradise, CA 95969")
        assert source == "demo_cache"
        assert fetch_response["fields"]["fire_hazard_severity_zone_class"]["value"] == "Very High"
        assert lat == pytest.approx(39.749521)
        assert lng == pytest.approx(-121.63408)


class TestCheckInsurabilityTool:
    def test_end_to_end_with_mocked_live_client(self, monkeypatch):
        import tools.hazard_tools as tools_mod

        class FakeClient:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                pass

            def geocode(self, address):
                return GeocodeResult(
                    lat=39.749521,
                    lng=-121.63408,
                    accuracy=1.0,
                    accuracy_type="rooftop",
                    normalized_address=address,
                    provider="geocodio",
                )

            def fetch_with_retry(self, lat, lng, preset, max_retries=1):
                return PARADISE_CA_FETCH

            def lookup_parcel(self, address):
                return {"geometry": '{"type":"Polygon","coordinates":[]}', "apn": "052-250-077-000"}

            def fetch_fields(self, address, fields):
                return {
                    "fields": {
                        "nearest_fire_station_name": {
                            "value": "Paradise Fire Department Station 81", "status": "ok",
                        },
                        "nearest_fire_station_distance_m": {"value": 931.0, "status": "ok"},
                    }
                }

            def proximity_drive_time(self, origin, destination):
                return {
                    "duration_minutes": 6.1,
                    "distance_miles": 2.2,
                    "destination_matched": "Paradise Ave, Paradise, CA 95969",
                    "destination_accuracy": 0.88,
                }

        monkeypatch.setattr(tools_mod, "MireyeClient", lambda: FakeClient())
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        result = _tool_check_insurability("5555 Skyway, Paradise, CA 95969")
        assert result["verdict"] == "likely_hard_to_place"
        assert result["data_source_mode"] == "live"
        assert "narration" in result
        assert result["mitigations"]
        assert result["lat"] == pytest.approx(39.749521)
        assert result["lng"] == pytest.approx(-121.63408)
        assert result["address"] == "5555 Skyway, Paradise, CA 95969"
        assert result["parcel_apn"] == "052-250-077-000"
        assert result["parcel_boundary_geojson"] is not None
        assert result["fire_station"]["station_name"] == "Paradise Fire Department Station 81"
        assert result["fire_station"]["drive_minutes"] == pytest.approx(6.1)
        assert any("fire station" in f.lower() for f in result["driving_factors"])

    def test_counterfactual_overrides_flow_through(self, monkeypatch):
        import tools.hazard_tools as tools_mod

        class FakeClient:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                pass

            def geocode(self, address):
                return GeocodeResult(39.75, -121.63, 1.0, "rooftop", address, "geocodio")

            def fetch_with_retry(self, lat, lng, preset, max_retries=1):
                return PARADISE_CA_FETCH

        monkeypatch.setattr(tools_mod, "MireyeClient", lambda: FakeClient())
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        # _enrich=False: this test is about override logic, not enrichment
        # (covered separately in test_end_to_end_with_mocked_live_client).
        baseline = _tool_check_insurability("5555 Skyway, Paradise, CA 95969", _enrich=False)
        countered = _tool_check_insurability(
            "5555 Skyway, Paradise, CA 95969",
            overrides={"defensible_space_cleared": True},
            _enrich=False,
        )
        assert countered["verdict"] != baseline["verdict"] or baseline["verdict"] == "likely_insurable"
        assert any("Counterfactual" in f for f in countered["driving_factors"])


class TestCompareAddresses:
    ADDRESS_FIXTURES = {
        "5555 Skyway, Paradise, CA 95969": PARADISE_CA_FETCH,
        "1 Market St, San Francisco, CA 94105": LOW_RISK_CA_FETCH,
        "29029 Upper Bear Creek Rd, Evergreen, CO 80439": EVERGREEN_CO_FETCH,
    }

    def _patch_multi_address_client(self, monkeypatch):
        import tools.hazard_tools as tools_mod

        fixtures = self.ADDRESS_FIXTURES

        class FakeClient:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                pass

            def geocode(self, address):
                data = fixtures[address]
                return GeocodeResult(data["lat"], data["lng"], 1.0, "rooftop", address, "geocodio")

            def fetch_with_retry(self, lat, lng, preset, max_retries=1):
                for data in fixtures.values():
                    if data["lat"] == lat and data["lng"] == lng:
                        return data
                raise AssertionError("unexpected lat/lng in test")

        monkeypatch.setattr(tools_mod, "MireyeClient", lambda: FakeClient())
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    def test_ranks_most_severe_first(self, monkeypatch):
        self._patch_multi_address_client(monkeypatch)
        result = _tool_compare_addresses(list(self.ADDRESS_FIXTURES.keys()))
        verdicts = [r["verdict"] for r in result["results"]]
        assert verdicts[0] == "likely_hard_to_place"
        assert "out_of_scope" in verdicts
        assert verdicts.index("likely_hard_to_place") < verdicts.index("out_of_scope")

    def test_includes_lat_lng_per_result(self, monkeypatch):
        self._patch_multi_address_client(monkeypatch)
        result = _tool_compare_addresses(["5555 Skyway, Paradise, CA 95969"])
        assert result["results"][0]["lat"] == pytest.approx(39.749521)

    def test_summary_counts_verdicts(self, monkeypatch):
        self._patch_multi_address_client(monkeypatch)
        result = _tool_compare_addresses(list(self.ADDRESS_FIXTURES.keys()))
        assert "3 addresses checked" in result["summary"]

    def test_cheapest_mitigation_is_actually_the_cheapest(self, monkeypatch):
        self._patch_multi_address_client(monkeypatch)
        result = _tool_compare_addresses(["5555 Skyway, Paradise, CA 95969"])
        cheapest = result["results"][0]["cheapest_mitigation"]
        assert cheapest["action"] == "Spark arrestor on chimney"

    def test_empty_list_returns_empty_results(self):
        result = _tool_compare_addresses([])
        assert result["results"] == []


class TestCheckFloodRiskTool:
    def test_end_to_end_with_mocked_live_client(self, monkeypatch):
        import tools.hazard_tools as tools_mod

        class FakeClient:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                pass

            def geocode(self, address):
                return GeocodeResult(
                    lat=25.769783,
                    lng=-80.133277,
                    accuracy=1.0,
                    accuracy_type="rooftop",
                    normalized_address=address,
                    provider="geocodio",
                )

            def fetch_with_retry(self, lat, lng, preset, max_retries=1):
                assert preset == "flood_risk"
                return MIAMI_BEACH_FLOOD_FETCH

            def lookup_parcel(self, address):
                return None

        monkeypatch.setattr(tools_mod, "MireyeClient", lambda: FakeClient())
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        result = _tool_check_flood_risk("100 Ocean Dr, Miami Beach, FL 33139")
        assert result["verdict"] == "likely_hard_to_place"
        assert result["data_source_mode"] == "live"
        assert "narration" in result
        assert result["mitigations"]
        assert "fire_station" not in result

    def test_outside_sfha_is_likely_insurable(self, monkeypatch):
        import tools.hazard_tools as tools_mod

        class FakeClient:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                pass

            def geocode(self, address):
                return GeocodeResult(
                    lat=38.502246, lng=-122.997475, accuracy=1.0,
                    accuracy_type="rooftop", normalized_address=address, provider="geocodio",
                )

            def fetch_with_retry(self, lat, lng, preset, max_retries=1):
                return GUERNEVILLE_FLOOD_FETCH

            def lookup_parcel(self, address):
                return None

        monkeypatch.setattr(tools_mod, "MireyeClient", lambda: FakeClient())
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        result = _tool_check_flood_risk("16209 Main St, Guerneville, CA 95446")
        assert result["verdict"] == "likely_insurable"


class TestCheckEarthquakeRiskTool:
    def test_end_to_end_with_mocked_live_client(self, monkeypatch):
        import tools.hazard_tools as tools_mod

        class FakeClient:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                pass

            def geocode(self, address):
                return GeocodeResult(
                    lat=39.749521, lng=-121.63408, accuracy=1.0,
                    accuracy_type="rooftop", normalized_address=address, provider="geocodio",
                )

            def fetch_with_retry(self, lat, lng, preset, max_retries=1):
                assert preset == "natural_hazard"
                return PARADISE_EARTHQUAKE_FETCH

            def lookup_parcel(self, address):
                return None

        monkeypatch.setattr(tools_mod, "MireyeClient", lambda: FakeClient())
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        result = _tool_check_earthquake_risk("5555 Skyway, Paradise, CA 95969")
        assert result["verdict"] == "harder_to_place"
        assert result["data_source_mode"] == "live"
        assert "narration" in result
        assert result["mitigations"]
        assert "fire_station" not in result


class TestFullRiskReportTool:
    def _patch_all_three(self, monkeypatch, wildfire_verdict, flood_verdict, earthquake_verdict):
        import tools.hazard_tools as tools_mod

        def fake_result(verdict, driving_factor):
            return {
                "verdict": verdict,
                "driving_factors": [driving_factor] if driving_factor else [],
                "narration": f"narrated {verdict}",
                "lat": 39.7,
                "lng": -121.6,
            }

        monkeypatch.setattr(
            tools_mod, "_tool_check_insurability",
            lambda address, _enrich=True: fake_result(wildfire_verdict, "wildfire factor"),
        )
        monkeypatch.setattr(
            tools_mod, "_tool_check_flood_risk",
            lambda address, _enrich=True: fake_result(flood_verdict, "flood factor"),
        )
        monkeypatch.setattr(
            tools_mod, "_tool_check_earthquake_risk",
            lambda address, _enrich=True: fake_result(earthquake_verdict, "earthquake factor"),
        )

    def test_overall_verdict_is_the_worst_of_the_three(self, monkeypatch):
        self._patch_all_three(
            monkeypatch,
            wildfire_verdict="likely_insurable",
            flood_verdict="likely_hard_to_place",
            earthquake_verdict="harder_to_place",
        )
        result = _tool_full_risk_report("some address")
        assert result["overall_verdict"] == "likely_hard_to_place"

    def test_returns_one_entry_per_hazard(self, monkeypatch):
        self._patch_all_three(monkeypatch, "likely_insurable", "likely_insurable", "likely_insurable")
        result = _tool_full_risk_report("some address")
        hazards = {h["hazard"] for h in result["hazards"]}
        assert hazards == {"wildfire", "flood", "earthquake"}

    def test_low_confidence_hazards_excluded_from_worst_calculation(self, monkeypatch):
        self._patch_all_three(
            monkeypatch,
            wildfire_verdict="low_confidence",
            flood_verdict="likely_insurable",
            earthquake_verdict="likely_insurable",
        )
        result = _tool_full_risk_report("some address")
        # low_confidence must not accidentally "win" as best or worst.
        assert result["overall_verdict"] == "likely_insurable"

    def test_all_low_confidence_falls_back_to_low_confidence(self, monkeypatch):
        self._patch_all_three(monkeypatch, "low_confidence", "low_confidence", "low_confidence")
        result = _tool_full_risk_report("some address")
        assert result["overall_verdict"] == "low_confidence"

    def test_never_lets_one_hazard_score_another(self, monkeypatch):
        self._patch_all_three(
            monkeypatch,
            wildfire_verdict="likely_hard_to_place",
            flood_verdict="likely_insurable",
            earthquake_verdict="likely_insurable",
        )
        result = _tool_full_risk_report("some address")
        by_hazard = {h["hazard"]: h["verdict"] for h in result["hazards"]}
        assert by_hazard["wildfire"] == "likely_hard_to_place"
        assert by_hazard["flood"] == "likely_insurable"
        assert by_hazard["earthquake"] == "likely_insurable"


class TestAskAboutLocation:
    def test_success(self, monkeypatch):
        import tools.hazard_tools as tools_mod

        class FakeClient:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                pass

            def ask(self, address, question):
                return {
                    "answer": "Zone X, not a flood hazard area.",
                    "confidence": "high",
                    "citations": [{"source": "FEMA_NFHL"}],
                    "data_gaps": [],
                }

        monkeypatch.setattr(tools_mod, "MireyeClient", lambda: FakeClient())

        result = _tool_ask_about_location(
            "5555 Skyway, Paradise, CA 95969", "Is this in a flood zone?"
        )
        assert result["confidence"] == "high"
        assert "Zone X" in result["answer"]
        assert result["citations"]

    def test_failure_degrades_gracefully(self, monkeypatch):
        import tools.hazard_tools as tools_mod

        class FakeClient:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                pass

            def ask(self, address, question):
                return None

        monkeypatch.setattr(tools_mod, "MireyeClient", lambda: FakeClient())

        result = _tool_ask_about_location("5555 Skyway, Paradise, CA 95969", "anything?")
        assert result["confidence"] is None
        assert "couldn't reach" in result["answer"].lower()

    def test_never_returns_a_verdict_field(self, monkeypatch):
        """ask_about_location's result shape must not resemble
        check_insurability's — this is the structural guard against the
        agent ever mistaking one for the other's grounding path."""
        import tools.hazard_tools as tools_mod

        class FakeClient:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                pass

            def ask(self, address, question):
                return {"answer": "x", "confidence": "low", "citations": [], "data_gaps": []}

        monkeypatch.setattr(tools_mod, "MireyeClient", lambda: FakeClient())

        result = _tool_ask_about_location("5555 Skyway, Paradise, CA 95969", "anything?")
        assert "verdict" not in result
