from __future__ import annotations

import math
from dataclasses import dataclass

import requests

LOCATION_LOOKUP_URL = "https://ipapi.co/json/"
LOCATION_REQUEST_TIMEOUT_SECONDS = 8.0


@dataclass(frozen=True)
class DetectedLocation:
    name: str
    latitude: float
    longitude: float


class LocationDetectionUnavailable(RuntimeError):
    """Raised when a city-level location cannot be detected."""


def detect_city_location() -> DetectedLocation:
    """Detect an editable city-level location from the machine's public IP.

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
        raise LocationDetectionUnavailable("location provider is unavailable") from exc

    if response.status_code != 200:
        raise LocationDetectionUnavailable("location provider rejected the request")

    try:
        payload = response.json()
    except ValueError as exc:
        raise LocationDetectionUnavailable("location provider returned invalid JSON") from exc

    if not isinstance(payload, dict) or payload.get("error") is True:
        raise LocationDetectionUnavailable("location provider returned an error")

    latitude = _finite_coordinate(payload.get("latitude"), minimum=-90, maximum=90)
    longitude = _finite_coordinate(payload.get("longitude"), minimum=-180, maximum=180)
    name = _location_name(payload)
    if latitude is None or longitude is None or not name:
        raise LocationDetectionUnavailable("location provider returned incomplete data")

    return DetectedLocation(name=name, latitude=latitude, longitude=longitude)


def _finite_coordinate(value: object, *, minimum: float, maximum: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    coordinate = float(value)
    if not math.isfinite(coordinate) or not minimum <= coordinate <= maximum:
        return None
    return coordinate


def _location_name(payload: dict[object, object]) -> str:
    values = [payload.get("city"), payload.get("region"), payload.get("country_name")]
    parts: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        part = value.strip()
        normalized = part.casefold()
        if part and normalized not in seen:
            parts.append(part)
            seen.add(normalized)
    return ", ".join(parts)
