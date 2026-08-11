"""Deterministic scoring logic. No LLM calls anywhere in this file.

Every function here takes already-fetched AirLabs data and returns plain
numbers/dicts. The LLM layer (agent.py) decides *which* of these to call
and narrates the result - it never computes a score itself.
"""

from __future__ import annotations

LONG_HAUL_THRESHOLD_MIN = 360  # 6 hours - documented assumption, not an FAA definition
DELAY_THRESHOLD_MIN = 15  # matches BTS/DOT's own definition of "delayed"
SCHEDULES_PAGE_CAP = 100  # AirLabs free-tier /schedules page size - empirically verified:
# ATL/ORD/DFW each returned exactly 100 rows with has_more=true; BGR (a small airport
# with only 43 total flights) returned all 43 with has_more=false. Confirmed as a real
# API ceiling, not guessed from the /routes docs (which cap at 50, a different endpoint).


# ---- raw metric extraction (works for a single airport, no peer data needed) ----

def congestion_metrics(schedules: list[dict]) -> dict:
    total = len(schedules)
    if total == 0:
        return {
            "total_flights": 0,
            "delayed_flights": None,
            "delay_rate": None,
            "cancelled_flights": None,
            "cancel_rate": None,
            "avg_delay_min": None,
            "note": "No scheduled departures returned in the sampled window.",
        }

    delayed = [f for f in schedules if (f.get("dep_delayed") or 0) >= DELAY_THRESHOLD_MIN]
    cancelled = [f for f in schedules if f.get("status") == "cancelled"]
    delay_values = [f["dep_delayed"] for f in schedules if f.get("dep_delayed") is not None]

    return {
        "total_flights": total,
        "delayed_flights": len(delayed),
        "delay_rate": len(delayed) / total,
        "cancelled_flights": len(cancelled),
        "cancel_rate": len(cancelled) / total,
        "avg_delay_min": (sum(delay_values) / len(delay_values)) if delay_values else None,
        "note": (
            f"Based on {total} sampled scheduled departures within the API's "
            "~10-hour forward window (AirLabs free tier); not a full-day traffic count."
        ),
    }


def activity_metrics(schedules: list[dict]) -> dict:
    return {
        "total_flights": len(schedules),
        "note": (
            f"Snapshot of departures sampled at query time, capped at "
            f"{SCHEDULES_PAGE_CAP} by the API. Time-of-day sensitive: querying "
            "at 3am vs. 3pm for the same airport can give very different counts."
        ),
    }


def connectivity_metrics(routes: list[dict]) -> dict:
    total = len(routes)
    with_duration = [r for r in routes if r.get("duration") is not None]
    unique_destinations = {r["arr_iata"] for r in routes if r.get("arr_iata")}
    long_haul = [r for r in with_duration if r["duration"] >= LONG_HAUL_THRESHOLD_MIN]

    return {
        "routes_sampled": total,
        "routes_with_known_duration": len(with_duration),
        "unique_destinations": len(unique_destinations),
        "long_haul_count": len(long_haul),
        "long_haul_pct": (
            round(100 * len(long_haul) / len(with_duration), 1) if with_duration else None
        ),
        "note": (
            f"Based on the first {total} routes returned by the API (page-1 sample; "
            "airports can have 1000+ total routes, only page 1 is fetched to conserve "
            "the free-tier quota). Long-haul defined here as duration >= "
            f"{LONG_HAUL_THRESHOLD_MIN} min ({LONG_HAUL_THRESHOLD_MIN // 60}h) - a stated "
            "assumption, not an official FAA/IATA definition. "
            f"{total - len(with_duration)} of {total} sampled routes had no duration "
            "data (mostly smaller regional carriers) and were excluded from the "
            "long-haul percentage to avoid skewing it."
        ),
    }


# ---- raw scalars, for building a comparison set across multiple airports ----

def congestion_raw(metrics: dict) -> float:
    if not metrics["total_flights"]:
        return 0.0
    return 0.7 * metrics["delay_rate"] + 0.3 * metrics["cancel_rate"]


def activity_raw(metrics: dict) -> float:
    return metrics["total_flights"]


def connectivity_raw(metrics: dict) -> float:
    return metrics["unique_destinations"]


# ---- comparison-set normalization (Q1/Q2-style: ranking or pairwise compare) ----

def normalize_set(raw_by_airport: dict[str, float]) -> dict[str, float]:
    """Min-max normalize to 0-100 across the given comparison set.

    Only meaningful with >=2 airports being compared - this is a relative
    ranking tool, not an absolute scale. If every airport has the same raw
    value, everyone gets 50 (no signal to differentiate them).
    """
    values = list(raw_by_airport.values())
    lo, hi = min(values), max(values)
    if hi == lo:
        return {k: 50.0 for k in raw_by_airport}
    return {k: round(100 * (v - lo) / (hi - lo), 1) for k, v in raw_by_airport.items()}


def investment_priority_index(congestion_score: float, activity_score: float, connectivity_score: float) -> float:
    """Weighted composite, 0-100. NOT a financial ROI figure - see DESIGN.md.

    weights: 40% congestion, 30% activity, 30% connectivity.
    """
    return round(0.40 * congestion_score + 0.30 * activity_score + 0.30 * connectivity_score, 1)


# ---- single-airport proxy (Q4-style: no peer comparison available/desired) ----

def unmet_demand_proxy(congestion: dict, activity: dict) -> dict:
    """Only meaningful when BOTH congestion and traffic volume are elevated
    together - high delay with low traffic is more likely a weather/ops
    event than saturated demand. Uses the API's own page cap (real, not an
    invented peer benchmark) as the activity ceiling.
    """
    c_raw = congestion_raw(congestion)  # already in [0, 1]
    activity_fraction = min(activity["total_flights"], SCHEDULES_PAGE_CAP) / SCHEDULES_PAGE_CAP

    proxy_0_100 = round(100 * (c_raw * activity_fraction) ** 0.5, 1)

    return {
        "unmet_demand_proxy": proxy_0_100,
        "congestion_component": round(c_raw * 100, 1),
        "activity_component": round(activity_fraction * 100, 1),
        "explanation": (
            "Proxy = geometric mean of congestion rate and sampled traffic volume "
            f"(volume expressed as a fraction of the API's own {SCHEDULES_PAGE_CAP}-flight "
            "page cap, not compared against other airports). High only when delays/"
            "cancellations AND schedule volume are both elevated at once - the signature "
            "of demand pressing against limited capacity, as opposed to an isolated event. "
            "This is a heuristic proxy: no data source observes passengers who wanted "
            "to fly but could not, so this is not a measured 'unmet demand' figure."
        ),
    }
