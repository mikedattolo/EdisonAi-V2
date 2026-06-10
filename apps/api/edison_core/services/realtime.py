"""Real-time context: location (IP-based or client-provided), current local time, and weather.

Uses keyless services: ip-api.com for geolocation and Open-Meteo for weather. Results are
cached briefly so the chat/agent can cheaply include "what time is it / what's the weather"
context on every turn.
"""

from __future__ import annotations

import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx


WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    56: "Light freezing drizzle", 57: "Dense freezing drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    66: "Light freezing rain", 67: "Heavy freezing rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
    85: "Slight snow showers", 86: "Heavy snow showers",
    95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
}


class RealtimeService:
    def __init__(self, http_timeout_seconds: float = 8.0, cache_seconds: float = 300.0) -> None:
        self.http_timeout_seconds = http_timeout_seconds
        self.cache_seconds = cache_seconds
        self._cache: dict[str, Any] | None = None
        self._cache_at = 0.0

    def context(
        self,
        latitude: float | None = None,
        longitude: float | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        use_cache = latitude is None and longitude is None and not force
        if use_cache and self._cache is not None and (_time.monotonic() - self._cache_at) < self.cache_seconds:
            return self._cache

        location = self._location(latitude, longitude)
        weather = None
        if location.get("latitude") is not None and location.get("longitude") is not None:
            weather = self._weather(location["latitude"], location["longitude"])

        utc_offset = (weather or {}).get("utc_offset_seconds")
        tz_name = (weather or {}).get("timezone") or location.get("timezone")
        local_time = self._local_time(utc_offset, tz_name)

        result = {
            "location": location,
            "weather": weather,
            "time": local_time,
            "summary": self._summary(location, weather, local_time),
        }
        if use_cache:
            self._cache = result
            self._cache_at = _time.monotonic()
        return result

    def summary(self) -> str:
        try:
            return str(self.context().get("summary") or "")
        except Exception:  # noqa: BLE001
            return ""

    def _location(self, latitude: float | None, longitude: float | None) -> dict[str, Any]:
        if latitude is not None and longitude is not None:
            return {"latitude": float(latitude), "longitude": float(longitude), "source": "client"}
        try:
            with httpx.Client(timeout=self.http_timeout_seconds) as client:
                response = client.get(
                    "http://ip-api.com/json/",
                    params={"fields": "status,country,regionName,city,lat,lon,timezone"},
                )
                response.raise_for_status()
                data = response.json()
            if data.get("status") == "success":
                return {
                    "city": data.get("city"),
                    "region": data.get("regionName"),
                    "country": data.get("country"),
                    "latitude": data.get("lat"),
                    "longitude": data.get("lon"),
                    "timezone": data.get("timezone"),
                    "source": "ip",
                }
        except Exception:  # noqa: BLE001
            pass
        return {"source": "unavailable"}

    def _weather(self, latitude: float, longitude: float) -> dict[str, Any] | None:
        try:
            with httpx.Client(timeout=self.http_timeout_seconds) as client:
                response = client.get(
                    "https://api.open-meteo.com/v1/forecast",
                    params={
                        "latitude": latitude,
                        "longitude": longitude,
                        "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,is_day",
                        "timezone": "auto",
                        "temperature_unit": "fahrenheit",
                        "wind_speed_unit": "mph",
                    },
                )
                response.raise_for_status()
                data = response.json()
            current = data.get("current") or {}
            code = current.get("weather_code")
            return {
                "temperature_f": current.get("temperature_2m"),
                "feels_like_f": current.get("apparent_temperature"),
                "humidity": current.get("relative_humidity_2m"),
                "wind_mph": current.get("wind_speed_10m"),
                "is_day": bool(current.get("is_day")),
                "code": code,
                "description": WMO_CODES.get(int(code), "Unknown") if code is not None else None,
                "timezone": data.get("timezone"),
                "utc_offset_seconds": data.get("utc_offset_seconds"),
                "observed_at": current.get("time"),
            }
        except Exception:  # noqa: BLE001
            return None

    def _local_time(self, utc_offset_seconds: Any, tz_name: str | None) -> dict[str, Any]:
        try:
            if utc_offset_seconds is not None:
                now = datetime.now(timezone(timedelta(seconds=int(utc_offset_seconds))))
            else:
                now = datetime.now().astimezone()
            return {
                "iso": now.isoformat(),
                "display": now.strftime("%A, %B %d, %Y, %I:%M %p").replace(" 0", " "),
                "timezone": tz_name,
            }
        except Exception:  # noqa: BLE001
            now = datetime.now(timezone.utc)
            return {"iso": now.isoformat(), "display": now.strftime("%Y-%m-%d %H:%M UTC"), "timezone": "UTC"}

    def _summary(self, location: dict[str, Any], weather: dict[str, Any] | None, local_time: dict[str, Any]) -> str:
        place = ", ".join(part for part in [location.get("city"), location.get("region")] if part) or "your area"
        head = f"Current local time is {local_time.get('display')}"
        if local_time.get("timezone"):
            head += f" ({local_time['timezone']})"
        if weather and weather.get("temperature_f") is not None:
            tail = (
                f"Weather in {place}: {weather.get('description')}, "
                f"{round(weather['temperature_f'])}°F"
            )
            if weather.get("feels_like_f") is not None:
                tail += f" (feels like {round(weather['feels_like_f'])}°F)"
            if weather.get("wind_mph") is not None:
                tail += f", wind {round(weather['wind_mph'])} mph"
            return f"{head}. {tail}."
        return f"{head}. Location: {place} (weather unavailable)."
