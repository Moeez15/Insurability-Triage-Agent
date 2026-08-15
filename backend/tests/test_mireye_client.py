import httpx
import pytest
import respx

from mireye_client.client import (
    AddressNotFoundError,
    AddressTooCoarseError,
    MireyeAuthError,
    MireyeClient,
    MireyeError,
    MireyeRetryableError,
    MireyeUnconfiguredError,
)


@pytest.fixture
def client():
    c = MireyeClient(token="test-token")
    yield c
    c.close()


class TestGeocode:
    @respx.mock
    def test_success_rooftop(self, client):
        respx.post("https://api.mireye.com/v1/geocode").mock(
            return_value=httpx.Response(
                200,
                json={
                    "lat": 39.749521,
                    "lng": -121.63408,
                    "accuracy": 1.0,
                    "accuracy_type": "rooftop",
                    "normalized_address": "5555 Skyway, Paradise, CA 95969",
                    "provider": "geocodio",
                },
            )
        )
        result = client.geocode("5555 Skyway, Paradise, CA 95969")
        assert result.accuracy_type == "rooftop"
        assert result.lat == 39.749521

    @respx.mock
    def test_address_too_coarse(self, client):
        respx.post("https://api.mireye.com/v1/geocode").mock(
            return_value=httpx.Response(404, json={"code": "address_too_coarse"})
        )
        with pytest.raises(AddressTooCoarseError):
            client.geocode("Los Angeles, CA")

    @respx.mock
    def test_address_not_found(self, client):
        respx.post("https://api.mireye.com/v1/geocode").mock(
            return_value=httpx.Response(404, json={"code": "address_not_found"})
        )
        with pytest.raises(AddressNotFoundError):
            client.geocode("asdkjfh not a real address")

    @respx.mock
    def test_retryable_5xx_carries_retry_after(self, client):
        respx.post("https://api.mireye.com/v1/geocode").mock(
            return_value=httpx.Response(504, headers={"Retry-After": "2"})
        )
        with pytest.raises(MireyeRetryableError) as exc_info:
            client.geocode("5555 Skyway, Paradise, CA 95969")
        assert exc_info.value.retry_after == 2.0

    @respx.mock
    def test_retryable_429(self, client):
        respx.post("https://api.mireye.com/v1/geocode").mock(return_value=httpx.Response(429))
        with pytest.raises(MireyeRetryableError):
            client.geocode("5555 Skyway, Paradise, CA 95969")

    @respx.mock
    def test_unconfigured_503(self, client):
        respx.post("https://api.mireye.com/v1/geocode").mock(return_value=httpx.Response(503))
        with pytest.raises(MireyeUnconfiguredError):
            client.geocode("5555 Skyway, Paradise, CA 95969")

    @respx.mock
    def test_auth_failure_401(self, client):
        respx.post("https://api.mireye.com/v1/geocode").mock(return_value=httpx.Response(401))
        with pytest.raises(MireyeAuthError):
            client.geocode("5555 Skyway, Paradise, CA 95969")

    @respx.mock
    def test_auth_failure_403(self, client):
        respx.post("https://api.mireye.com/v1/geocode").mock(return_value=httpx.Response(403))
        with pytest.raises(MireyeAuthError):
            client.geocode("5555 Skyway, Paradise, CA 95969")

    @respx.mock
    def test_connection_error_becomes_retryable(self, client):
        """A real outage (no HTTP response at all) must map onto the same
        MireyeRetryableError as a 5xx — this is what lets the demo-cache
        fallback trigger on an actual network failure, not just an error
        status code."""
        respx.post("https://api.mireye.com/v1/geocode").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        with pytest.raises(MireyeRetryableError):
            client.geocode("5555 Skyway, Paradise, CA 95969")

    @respx.mock
    def test_timeout_becomes_retryable(self, client):
        respx.post("https://api.mireye.com/v1/geocode").mock(
            side_effect=httpx.ConnectTimeout("timed out")
        )
        with pytest.raises(MireyeRetryableError):
            client.geocode("5555 Skyway, Paradise, CA 95969")

    @respx.mock
    def test_unexpected_status_raises_mireye_error(self, client):
        respx.post("https://api.mireye.com/v1/geocode").mock(return_value=httpx.Response(418))
        with pytest.raises(MireyeError):
            client.geocode("5555 Skyway, Paradise, CA 95969")

    @respx.mock
    def test_non_json_response_raises_mireye_error(self, client):
        respx.post("https://api.mireye.com/v1/geocode").mock(
            return_value=httpx.Response(200, text="<html>not json</html>")
        )
        with pytest.raises(MireyeError):
            client.geocode("5555 Skyway, Paradise, CA 95969")


class TestFetchAuthAndNetworkFailures:
    @respx.mock
    def test_fetch_auth_failure(self, client):
        respx.post("https://api.mireye.com/v1/fetch").mock(return_value=httpx.Response(403))
        with pytest.raises(MireyeAuthError):
            client.fetch(39.7, -121.6, "wildfire_underwrite")

    @respx.mock
    def test_fetch_connection_error_becomes_retryable(self, client):
        respx.post("https://api.mireye.com/v1/fetch").mock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        with pytest.raises(MireyeRetryableError):
            client.fetch(39.7, -121.6, "wildfire_underwrite")


class TestFetchWithRetry:
    @respx.mock
    def test_no_retry_needed_when_all_ok(self, client):
        route = respx.post("https://api.mireye.com/v1/fetch").mock(
            return_value=httpx.Response(
                200,
                json={"fields": {"elevation": {"value": 492.8, "status": "ok"}}},
            )
        )
        result = client.fetch_with_retry(39.7, -121.6, "wildfire_underwrite")
        assert result["fields"]["elevation"]["status"] == "ok"
        assert route.call_count == 1

    @respx.mock
    def test_retries_once_on_retryable_failure_then_succeeds(self, client):
        responses = [
            httpx.Response(
                200,
                json={
                    "fields": {
                        "soil_shrink_swell_class": {
                            "value": None,
                            "status": "failed",
                            "retryable": True,
                        }
                    }
                },
            ),
            httpx.Response(
                200,
                json={
                    "fields": {
                        "soil_shrink_swell_class": {
                            "value": "high",
                            "status": "ok",
                            "retryable": False,
                        }
                    }
                },
            ),
        ]
        route = respx.post("https://api.mireye.com/v1/fetch").mock(side_effect=responses)
        result = client.fetch_with_retry(39.7, -121.6, "natural_hazard", max_retries=1)
        assert result["fields"]["soil_shrink_swell_class"]["status"] == "ok"
        assert route.call_count == 2

    @respx.mock
    def test_does_not_retry_non_retryable_failure(self, client):
        route = respx.post("https://api.mireye.com/v1/fetch").mock(
            return_value=httpx.Response(
                200,
                json={
                    "fields": {
                        "fire_hazard_severity_zone_class": {
                            "value": None,
                            "status": "absent",
                            "retryable": False,
                        }
                    }
                },
            )
        )
        result = client.fetch_with_retry(39.7, -121.6, "wildfire_underwrite", max_retries=1)
        assert result["fields"]["fire_hazard_severity_zone_class"]["status"] == "absent"
        assert route.call_count == 1

    @respx.mock
    def test_retry_that_itself_fails_returns_first_result_not_an_exception(self, client):
        """If the retry attempt hits a network failure, the caller still
        gets the original (partially-failed) result back rather than an
        exception — a flaky retry must not destroy an otherwise-usable
        first response."""
        responses = [
            httpx.Response(
                200,
                json={
                    "fields": {
                        "soil_shrink_swell_class": {
                            "value": None,
                            "status": "failed",
                            "retryable": True,
                        }
                    }
                },
            ),
            httpx.ConnectError("Connection refused"),
        ]
        respx.post("https://api.mireye.com/v1/fetch").mock(side_effect=responses)
        result = client.fetch_with_retry(39.7, -121.6, "natural_hazard", max_retries=1)
        assert result["fields"]["soil_shrink_swell_class"]["status"] == "failed"


class TestFetchFields:
    @respx.mock
    def test_success(self, client):
        respx.post("https://api.mireye.com/v1/fetch").mock(
            return_value=httpx.Response(
                200,
                json={"fields": {"nearest_fire_station_name": {"value": "Station 1", "status": "ok"}}},
            )
        )
        result = client.fetch_fields("5555 Skyway, Paradise, CA 95969", ["nearest_fire_station_name"])
        assert result["fields"]["nearest_fire_station_name"]["value"] == "Station 1"

    @respx.mock
    def test_auth_failure(self, client):
        respx.post("https://api.mireye.com/v1/fetch").mock(return_value=httpx.Response(401))
        with pytest.raises(MireyeAuthError):
            client.fetch_fields("5555 Skyway, Paradise, CA 95969", ["x"])


class TestLookupParcel:
    @respx.mock
    def test_success_returns_parcel(self, client):
        respx.post("https://api.mireye.com/v1/lookup").mock(
            return_value=httpx.Response(
                200,
                json={
                    "disposition": "resolved",
                    "parcel_unavailable": False,
                    "parcel": {"geometry": '{"type":"Polygon"}', "apn": "052-250-077-000"},
                },
            )
        )
        parcel = client.lookup_parcel("5555 Skyway, Paradise, CA 95969")
        assert parcel["apn"] == "052-250-077-000"

    @respx.mock
    def test_parcel_unavailable_returns_none(self, client):
        respx.post("https://api.mireye.com/v1/lookup").mock(
            return_value=httpx.Response(
                200, json={"disposition": "resolved", "parcel_unavailable": True}
            )
        )
        assert client.lookup_parcel("5555 Skyway, Paradise, CA 95969") is None

    @respx.mock
    def test_no_match_returns_none(self, client):
        respx.post("https://api.mireye.com/v1/lookup").mock(
            return_value=httpx.Response(200, json={"disposition": "no_match", "reason": "unresolvable"})
        )
        assert client.lookup_parcel("gibberish") is None

    @respx.mock
    def test_network_failure_returns_none_not_raises(self, client):
        """Enrichment data must degrade silently, never raise — this is
        the contract server.py's enrichment step relies on."""
        respx.post("https://api.mireye.com/v1/lookup").mock(side_effect=httpx.ConnectError("down"))
        assert client.lookup_parcel("5555 Skyway, Paradise, CA 95969") is None

    @respx.mock
    def test_server_error_returns_none_not_raises(self, client):
        respx.post("https://api.mireye.com/v1/lookup").mock(return_value=httpx.Response(500))
        assert client.lookup_parcel("5555 Skyway, Paradise, CA 95969") is None


class TestProximityDriveTime:
    @respx.mock
    def test_success(self, client):
        respx.post("https://api.mireye.com/v1/proximity").mock(
            return_value=httpx.Response(
                200,
                json={
                    "legs": [{"duration_minutes": 6.1, "distance_miles": 2.2, "flag": None}],
                    "resolved_destinations": [
                        {"formatted_address": "Paradise Ave, Paradise, CA", "accuracy": 0.88}
                    ],
                },
            )
        )
        result = client.proximity_drive_time(
            "5555 Skyway, Paradise, CA 95969", "Paradise Fire Department, Paradise, CA"
        )
        assert result["duration_minutes"] == pytest.approx(6.1)
        assert result["destination_accuracy"] == pytest.approx(0.88)

    @respx.mock
    def test_flagged_leg_returns_none(self, client):
        """A flagged leg means the driving matrix itself reported a problem
        for this pair — don't present it as a real answer."""
        respx.post("https://api.mireye.com/v1/proximity").mock(
            return_value=httpx.Response(
                200, json={"legs": [{"flag": "unresolvable_destination"}]}
            )
        )
        result = client.proximity_drive_time("origin", "nonsense destination")
        assert result is None

    @respx.mock
    def test_service_unconfigured_returns_none(self, client):
        respx.post("https://api.mireye.com/v1/proximity").mock(return_value=httpx.Response(503))
        assert client.proximity_drive_time("a", "b") is None

    @respx.mock
    def test_network_failure_returns_none(self, client):
        respx.post("https://api.mireye.com/v1/proximity").mock(side_effect=httpx.ConnectTimeout("timeout"))
        assert client.proximity_drive_time("a", "b") is None


class TestAsk:
    @respx.mock
    def test_success(self, client):
        respx.post("https://api.mireye.com/v1/ask").mock(
            return_value=httpx.Response(
                200,
                json={
                    "answer": "Zone X, not in a flood hazard area.",
                    "confidence": "high",
                    "citations": [{"source": "FEMA_NFHL"}],
                    "data_gaps": [],
                },
            )
        )
        result = client.ask("5555 Skyway, Paradise, CA 95969", "Is this in a flood zone?")
        assert result["confidence"] == "high"
        assert "Zone X" in result["answer"]

    @respx.mock
    def test_failure_returns_none(self, client):
        respx.post("https://api.mireye.com/v1/ask").mock(return_value=httpx.Response(500))
        assert client.ask("5555 Skyway, Paradise, CA 95969", "anything?") is None

    @respx.mock
    def test_network_failure_returns_none(self, client):
        respx.post("https://api.mireye.com/v1/ask").mock(side_effect=httpx.ConnectError("down"))
        assert client.ask("5555 Skyway, Paradise, CA 95969", "anything?") is None
