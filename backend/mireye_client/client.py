"""Thin client for the Mireye API (/v1/geocode, /v1/fetch).

Wraps Mireye's own error taxonomy rather than inventing a generic one:
geocode failures are distinct (too-coarse vs. not-found vs. retryable),
and fetch responses carry a per-field status (ok/absent/failed) plus a
retryable flag that the scorer's fallback logic depends on directly.

Every network call is wrapped so a real outage (DNS failure, connection
refused, a timeout with no response at all) surfaces as MireyeRetryableError
just like a 5xx/429 does — that's what lets the demo-cache fallback in
mcp_server/server.py actually trigger on "the live API is down," not just
on "the live API returned an error status."
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx

MIREYE_BASE_URL = "https://api.mireye.com"


class MireyeError(Exception):
    """Base class for all Mireye client errors."""


class AddressTooCoarseError(MireyeError):
    """Upstream could only place the address at a ZIP/city/county/state centroid."""


class AddressNotFoundError(MireyeError):
    """Upstream had no match at all for the address."""


class MireyeRetryableError(MireyeError):
    """5xx/429/network-level failure — transient. Caller should retry,
    honoring retry_after if set."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class MireyeUnconfiguredError(MireyeError):
    """503 — operator problem (missing credential upstream), not worth retrying."""


class MireyeAuthError(MireyeError):
    """401/403 — the API token is missing, invalid, or expired. Not worth
    retrying without fixing the credential."""


@dataclass
class GeocodeResult:
    lat: float
    lng: float
    accuracy: float
    accuracy_type: str
    normalized_address: str
    provider: str


class MireyeClient:
    def __init__(self, token: str | None = None, timeout: float = 10.0):
        self._token = token or os.environ.get("MIREYE_API_TOKEN")
        if not self._token:
            raise MireyeError(
                "MIREYE_API_TOKEN not set — export it or pass token= explicitly."
            )
        self._client = httpx.Client(
            base_url=MIREYE_BASE_URL,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "MireyeClient":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    def _post(self, path: str, json: dict) -> httpx.Response:
        """POST wrapped so any network-level failure (no response at all —
        DNS failure, connection refused, a timeout) becomes a
        MireyeRetryableError, same as an HTTP 5xx/429 would. Without this,
        the exact "live API is down" scenario the demo-cache fallback
        exists for would crash uncaught instead of triggering it."""
        try:
            return self._client.post(path, json=json)
        except httpx.TimeoutException as exc:
            raise MireyeRetryableError(f"Mireye request timed out: {exc}") from exc
        except httpx.TransportError as exc:
            # Connection refused, DNS failure, etc. — anything below the
            # HTTP layer. TimeoutException is also a TransportError subtype
            # but is caught above first for a clearer message.
            raise MireyeRetryableError(f"Mireye request failed: {exc}") from exc

    def _safe_json(self, resp: httpx.Response) -> dict:
        try:
            return resp.json()
        except ValueError as exc:
            raise MireyeError(f"Mireye returned a non-JSON response: {exc}") from exc

    def geocode(self, address: str) -> GeocodeResult:
        """Resolve a US street address to a coordinate.

        Raises AddressTooCoarseError, AddressNotFoundError,
        MireyeAuthError, MireyeUnconfiguredError, or MireyeRetryableError
        (with retry_after populated from the Retry-After header when
        present, including for network-level failures) on failure.
        """
        resp = self._post("/v1/geocode", json={"address": address})

        if resp.status_code == 200:
            data = self._safe_json(resp)
            try:
                return GeocodeResult(
                    lat=data["lat"],
                    lng=data["lng"],
                    accuracy=data["accuracy"],
                    accuracy_type=data["accuracy_type"],
                    normalized_address=data["normalized_address"],
                    provider=data["provider"],
                )
            except KeyError as exc:
                raise MireyeError(f"Geocode response missing expected field: {exc}") from exc

        if resp.status_code == 404:
            body = self._safe_json(resp) if resp.headers.get(
                "content-type", ""
            ).startswith("application/json") else {}
            code = body.get("code") or body.get("detail", "")
            if "too_coarse" in str(code):
                raise AddressTooCoarseError(
                    f"Address resolves only to a coarse centroid: {address!r}"
                )
            raise AddressNotFoundError(f"No match for address: {address!r}")

        if resp.status_code in (401, 403):
            raise MireyeAuthError(
                "Mireye rejected the API token (401/403) — it may be missing, "
                "invalid, or expired. Check MIREYE_API_TOKEN."
            )

        if resp.status_code == 503:
            raise MireyeUnconfiguredError(
                "Mireye geocode service is unconfigured upstream (operator issue)."
            )

        if resp.status_code == 429 or resp.status_code >= 500:
            retry_after = resp.headers.get("Retry-After")
            raise MireyeRetryableError(
                f"Geocode transiently failed with {resp.status_code}",
                retry_after=float(retry_after) if retry_after else None,
            )

        raise MireyeError(
            f"Unexpected geocode response: {resp.status_code} {resp.text[:200]}"
        )

    def fetch(self, lat: float, lng: float, preset: str) -> dict:
        """Call /v1/fetch with a preset. Returns the raw response dict —
        the scorer reads each field's `status`/`retryable` directly rather
        than this client collapsing them into a generic error.
        """
        resp = self._post("/v1/fetch", json={"lat": lat, "lng": lng, "preset": preset})

        if resp.status_code == 200:
            return self._safe_json(resp)

        if resp.status_code in (401, 403):
            raise MireyeAuthError(
                "Mireye rejected the API token (401/403) — it may be missing, "
                "invalid, or expired. Check MIREYE_API_TOKEN."
            )

        if resp.status_code == 503:
            raise MireyeUnconfiguredError(
                "Mireye fetch service is unconfigured upstream (operator issue)."
            )

        if resp.status_code == 429 or resp.status_code >= 500:
            retry_after = resp.headers.get("Retry-After")
            raise MireyeRetryableError(
                f"Fetch transiently failed with {resp.status_code}",
                retry_after=float(retry_after) if retry_after else None,
            )

        raise MireyeError(
            f"Unexpected fetch response: {resp.status_code} {resp.text[:200]}"
        )

    def fetch_with_retry(
        self, lat: float, lng: float, preset: str, max_retries: int = 1
    ) -> dict:
        """Fetch, then retry exactly once per Arch-4 for any field whose
        status is "failed" and retryable is true. Returns the best
        available response after at most `max_retries` extra attempts.

        A retry that itself fails (including a network-level failure,
        which raises MireyeRetryableError via `_post`) is swallowed —
        the first result stands rather than losing a partially-good
        response to a flaky retry.
        """
        result = self.fetch(lat, lng, preset)
        for _ in range(max_retries):
            retryable_fields = [
                name
                for name, field in result.get("fields", {}).items()
                if field.get("status") == "failed" and field.get("retryable")
            ]
            if not retryable_fields:
                break
            time.sleep(0.5)
            try:
                retry_result = self.fetch(lat, lng, preset)
            except MireyeError:
                break
            for name in retryable_fields:
                if retry_result["fields"].get(name, {}).get("status") == "ok":
                    result["fields"][name] = retry_result["fields"][name]
        return result

    def fetch_fields(self, address: str, fields: list[str]) -> dict:
        """Like fetch(), but by address + explicit field names instead of
        lat/lng + preset — for pulling a couple of specific fields (e.g.
        nearest fire station name/distance) without the cost of a full
        preset. Best-effort semantics: same status codes as fetch()."""
        resp = self._post("/v1/fetch", json={"address": address, "fields": fields})

        if resp.status_code == 200:
            return self._safe_json(resp)
        if resp.status_code in (401, 403):
            raise MireyeAuthError(
                "Mireye rejected the API token (401/403) — it may be missing, "
                "invalid, or expired. Check MIREYE_API_TOKEN."
            )
        if resp.status_code == 503:
            raise MireyeUnconfiguredError("Mireye fetch service is unconfigured upstream.")
        if resp.status_code == 429 or resp.status_code >= 500:
            retry_after = resp.headers.get("Retry-After")
            raise MireyeRetryableError(
                f"Fetch transiently failed with {resp.status_code}",
                retry_after=float(retry_after) if retry_after else None,
            )
        raise MireyeError(f"Unexpected fetch response: {resp.status_code} {resp.text[:200]}")

    def lookup_parcel(self, address: str) -> dict | None:
        """POST /v1/lookup — resolves an address to a parcel, including
        boundary geometry (GeoJSON), APN, and zoning. Returns None on any
        failure or disposition other than "resolved" — this is enhancement
        data for the map, never required for a verdict."""
        try:
            resp = self._post("/v1/lookup", json={"input": address, "include_parcel": True})
        except MireyeRetryableError:
            return None
        if resp.status_code != 200:
            return None
        data = self._safe_json(resp)
        if data.get("disposition") != "resolved" or data.get("parcel_unavailable"):
            return None
        return data.get("parcel")

    def proximity_drive_time(self, origin: str, destination: str) -> dict | None:
        """POST /v1/proximity (op=distance) — real driving time/distance
        between two locators. Returns None on any failure (unresolvable
        destination, service unconfigured, transient error) — this is
        supplementary context, never required for a verdict."""
        try:
            resp = self._post(
                "/v1/proximity",
                json={
                    "op": "distance",
                    "origins": [origin],
                    "destinations": [destination],
                    "mode": "driving",
                },
            )
        except MireyeRetryableError:
            return None
        if resp.status_code != 200:
            return None
        data = self._safe_json(resp)
        legs = data.get("legs", [])
        if not legs or legs[0].get("flag"):
            return None
        dest_resolved = (data.get("resolved_destinations") or [{}])[0]
        return {
            "duration_minutes": legs[0].get("duration_minutes"),
            "distance_miles": legs[0].get("distance_miles"),
            "destination_matched": dest_resolved.get("formatted_address"),
            "destination_accuracy": dest_resolved.get("accuracy"),
        }

    def ask(self, address: str, question: str) -> dict | None:
        """POST /v1/ask — natural-language Q&A over a location, with its
        own citations/confidence/data_gaps. Used ONLY for questions outside
        what the insurability scorer covers (Premise: never let this feed
        the verdict — see agent.py's ask_about_location tool). Returns
        None on failure rather than raising, since this is always a
        secondary, best-effort capability."""
        try:
            resp = self._post("/v1/ask", json={"address": address, "question": question})
        except MireyeRetryableError:
            return None
        if resp.status_code != 200:
            return None
        return self._safe_json(resp)
