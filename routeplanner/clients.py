"""Thin clients for the free routing (OSRM) and geocoding (Nominatim) APIs."""
import hashlib
import re

import requests
from django.conf import settings
from django.core.cache import cache

from .geo import METERS_PER_MILE, in_usa_bbox

LATLON_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


class RoutingError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


class ApiCallCounter:
    """Counts outbound HTTP calls so the response can prove how few were made."""

    def __init__(self):
        self.routing = 0
        self.geocoding = 0

    @property
    def total(self):
        return self.routing + self.geocoding


def _cfg():
    return settings.FUEL_PLANNER


def _session_get(url, **kw):
    cfg = _cfg()
    try:
        return requests.get(
            url, timeout=cfg["HTTP_TIMEOUT_SECONDS"], headers={"User-Agent": cfg["USER_AGENT"]}, **kw
        )
    except requests.RequestException as exc:
        raise RoutingError(f"Upstream service unreachable: {exc}") from exc


def resolve_location(text, counter):
    """'lat,lon' is used as-is (no API call). Anything else is geocoded (1 call, cached)."""
    m = LATLON_RE.match(text)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        label = f"{lat:.5f},{lon:.5f}"
    else:
        key = "geo:" + hashlib.sha1(text.strip().lower().encode()).hexdigest()
        hit = cache.get(key)
        if hit:
            return hit
        counter.geocoding += 1
        resp = _session_get(
            _cfg()["NOMINATIM_URL"],
            params={"q": text, "format": "jsonv2", "limit": 1, "countrycodes": "us"},
        )
        if resp.status_code != 200:
            raise RoutingError(f"Geocoder returned HTTP {resp.status_code}")
        results = resp.json()
        if not results:
            raise RoutingError(f"Could not find a USA location for '{text}'", status=400)
        lat, lon = float(results[0]["lat"]), float(results[0]["lon"])
        label = results[0].get("display_name", text)
        cache.set(key, (lat, lon, label), _cfg()["CACHE_SECONDS"])
        return lat, lon, label
    if not in_usa_bbox(lat, lon):
        raise RoutingError(f"Coordinates {lat},{lon} are outside the USA", status=400)
    return lat, lon, label


def fetch_route(start, finish, counter):
    """ONE routing call -> (coords[[lon,lat],...], distance_miles, duration_seconds)."""
    key = "route:%.4f,%.4f;%.4f,%.4f" % (start[0], start[1], finish[0], finish[1])
    hit = cache.get(key)
    if hit:
        return hit
    base = _cfg()["OSRM_BASE_URL"].rstrip("/")
    url = f"{base}/route/v1/driving/{start[1]},{start[0]};{finish[1]},{finish[0]}"
    counter.routing += 1
    resp = _session_get(url, params={"overview": "full", "geometries": "geojson", "steps": "false"})
    if resp.status_code != 200:
        raise RoutingError(f"Routing service returned HTTP {resp.status_code}")
    data = resp.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise RoutingError(f"No drivable route found ({data.get('code')})", status=422)
    r = data["routes"][0]
    result = (r["geometry"]["coordinates"], r["distance"] / METERS_PER_MILE, r["duration"])
    cache.set(key, result, _cfg()["CACHE_SECONDS"])
    return result
