"""Thin client for the AirLabs free-tier API.

No caching, by design: every tool call makes a real, visible request to
AirLabs. This keeps the data flow simple and demonstrable - each answer is
traceably backed by a live API call, not a stored copy.
"""

import requests

from . import config

BASE_URL = "https://airlabs.co/api/v9"


class AirLabsError(RuntimeError):
    pass


def _get(endpoint: str, params: dict) -> list:
    resp = requests.get(
        f"{BASE_URL}/{endpoint}",
        params={**params, "api_key": config.AIRLABS_API_KEY},
        timeout=15,
    )
    resp.raise_for_status()
    body = resp.json()

    if "error" in body:
        raise AirLabsError(body["error"].get("message", "unknown AirLabs error"))

    return body.get("response", [])


def get_schedules(dep_iata: str) -> list[dict]:
    """Up to 100 upcoming departures (~10h window) for an airport."""
    return _get("schedules", {"dep_iata": dep_iata.upper()})


def get_routes(dep_iata: str) -> list[dict]:
    """First page (up to 50) of scheduled routes out of an airport.

    This is a sample, not the full route network (some airports have
    1000+ routes and the free tier returns 50/page) - documented
    limitation, not a bug.
    """
    return _get("routes", {"dep_iata": dep_iata.upper()})
