from __future__ import annotations

import math
from dataclasses import dataclass

import requests

from integrations.request_failure import request_failure_reason

LOCATION_LOOKUP_URL = "https://ipapi.co/json/"
LOCATION_REQUEST_TIMEOUT_SECONDS = 8.0


@dataclass(frozen=True)
class DetectedLocation:
    latitude: float
    longitude: float
    city: str | None = None


class LocationDetectionUnavailable(RuntimeError):
    """Raised when a city-level location cannot be detected."""

    def __init__(self, message: str, *, reason: str, http_status: int | None = None) -> None:
        super().__init__(message)
        self.reason = reason
        self.http_status = http_status


def detect_city_location() -> DetectedLocation:
    """Estimate editable city-level coordinates from the machine's public IP.

    Raises:
        LocationDetectionUnavailable: If the provider cannot be reached or
            returns an incomplete or invalid location.
    """

    try:
        response = requests.get(
            LOCATION_LOOKUP_URL,
            headers={"User-Agent": "WEScheduler"},
            timeout=LOCATION_REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise LocationDetectionUnavailable("location provider is unavailable", reason=request_failure_reason(exc)) from exc

    if response.status_code != 200:
        raise LocationDetectionUnavailable("location provider rejected the request", reason="http_status", http_status=response.status_code)

    try:
        payload = response.json()
    except ValueError as exc:
        raise LocationDetectionUnavailable("location provider returned invalid JSON", reason="invalid_json") from exc

    if not isinstance(payload, dict) or payload.get("error") is True:
        raise LocationDetectionUnavailable("location provider returned an error", reason="provider_error")

    latitude = _finite_coordinate(payload.get("latitude"), minimum=-90, maximum=90)
    longitude = _finite_coordinate(payload.get("longitude"), minimum=-180, maximum=180)
    if latitude is None or longitude is None:
        raise LocationDetectionUnavailable("location provider returned incomplete data", reason="invalid_response")

    city = payload.get("city")
    return DetectedLocation(
        latitude=latitude,
        longitude=longitude,
        city=city.strip() if isinstance(city, str) and city.strip() else None,
    )


def _finite_coordinate(value: object, *, minimum: float, maximum: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    coordinate = float(value)
    if not math.isfinite(coordinate) or not minimum <= coordinate <= maximum:
        return None
    return coordinate
