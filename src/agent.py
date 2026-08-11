"""Claude orchestration layer.

Claude's job here is strictly: understand the natural-language question,
decide which deterministic tool(s) to call and with what airport codes,
and narrate the results. It never computes a score itself - all numbers
come from scoring.py via the tool results.
"""

import json

import anthropic

from . import airlabs_client, config, scoring
from .airports import KNOWN_AIRPORTS, NEW_ENGLAND_AIRPORTS

client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

SYSTEM_PROMPT = f"""You are an airport investment analyst assistant for a firm that funds \
airport modernization projects in the US.

You answer questions by calling the provided tools, which run deterministic scoring \
logic against live AirLabs flight-schedule data. You never compute scores yourself - \
always call a tool and report its numbers.

Reference data:
- "New England" airports (fixed list, use exactly these IATA codes when asked about the \
region): {", ".join(NEW_ENGLAND_AIRPORTS)}
- Known airport name -> IATA mappings you can use directly: {json.dumps(KNOWN_AIRPORTS)}
- For any other city/airport name, resolve it to its IATA code yourself.

Rules:
- For a single airport, use get_airport_metrics (and unmet_demand_analysis if the \
question is specifically about unmet/pent-up demand).
- For comparing or ranking 2+ airports, use compare_airports.
- Every AirLabs-derived number comes from a small, time-bounded sample (schedules: up to \
100 flights in a ~10h forward window; routes: first ~50 routes returned by the API, not \
the full network). Always state this scoping limitation when you report a number - do not \
present sampled figures as exhaustive daily/annual totals.
- The "Investment Priority Index" is a relative operational-pressure score (0-100), NOT \
a financial ROI forecast - no airport revenue/cost data is available from any public \
API used here. Say so explicitly whenever you report this index.
- Never state a number or claim as a general fact about an airport. Ground every claim \
in the specific data you just received, e.g. "Based on the 84 flights AirLabs returned \
for SFO, 0 were delayed" rather than "SFO has no delays". Tie each claim to the actual \
sample size and endpoint it came from - the reader should always be able to tell it was \
this specific API response, not general knowledge about the airport.
- Be concise. Lead with the answer/ranking, then the one or two numbers that justify it.
"""

TOOLS = [
    {
        "name": "get_airport_metrics",
        "description": (
            "Fetch deterministic congestion, activity, and connectivity metrics for a "
            "single airport (delay rate, cancellations, sampled traffic volume, unique "
            "destinations, long-haul percentage). Use for single-airport questions, "
            "including 'what % of flights out of X are long-haul'."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "airport_iata": {"type": "string", "description": "3-letter IATA code, e.g. SFO"},
            },
            "required": ["airport_iata"],
            "additionalProperties": False,
        },
    },
    {
        "name": "compare_airports",
        "description": (
            "Fetch metrics for 2+ airports and compute normalized (0-100) Congestion, "
            "Activity, and Connectivity scores plus the composite Investment Priority "
            "Index, ranked descending. Use for ranking or comparison questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "airport_iatas": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "3-letter IATA codes to compare, e.g. [\"LAX\", \"SNA\"]",
                },
            },
            "required": ["airport_iatas"],
            "additionalProperties": False,
        },
    },
    {
        "name": "unmet_demand_analysis",
        "description": (
            "Compute the unmet-demand proxy for a single airport - a heuristic combining "
            "congestion and sampled traffic volume. Use when the question is specifically "
            "about unmet, unserved, or pent-up flight demand."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "airport_iata": {"type": "string", "description": "3-letter IATA code, e.g. SFO"},
            },
            "required": ["airport_iata"],
            "additionalProperties": False,
        },
    },
]


def _fetch_airport_raw(airport_iata: str) -> dict:
    schedules = airlabs_client.get_schedules(airport_iata)
    routes = airlabs_client.get_routes(airport_iata)
    congestion = scoring.congestion_metrics(schedules)
    activity = scoring.activity_metrics(schedules)
    connectivity = scoring.connectivity_metrics(routes)
    return {"congestion": congestion, "activity": activity, "connectivity": connectivity}


def _tool_get_airport_metrics(airport_iata: str) -> dict:
    return _fetch_airport_raw(airport_iata)


def _tool_compare_airports(airport_iatas: list[str]) -> dict:
    raw = {code.upper(): _fetch_airport_raw(code) for code in airport_iatas}

    congestion_raw = {c: scoring.congestion_raw(r["congestion"]) for c, r in raw.items()}
    activity_raw = {c: scoring.activity_raw(r["activity"]) for c, r in raw.items()}
    connectivity_raw = {c: scoring.connectivity_raw(r["connectivity"]) for c, r in raw.items()}

    congestion_score = scoring.normalize_set(congestion_raw)
    activity_score = scoring.normalize_set(activity_raw)
    connectivity_score = scoring.normalize_set(connectivity_raw)

    results = []
    for code in raw:
        index = scoring.investment_priority_index(
            congestion_score[code], activity_score[code], connectivity_score[code]
        )
        results.append({
            "airport": code,
            "investment_priority_index": index,
            "congestion_score": congestion_score[code],
            "activity_score": activity_score[code],
            "connectivity_score": connectivity_score[code],
            "raw_metrics": raw[code],
        })
    results.sort(key=lambda r: r["investment_priority_index"], reverse=True)
    return {"comparison_set_size": len(raw), "ranked": results}


def _tool_unmet_demand_analysis(airport_iata: str) -> dict:
    raw = _fetch_airport_raw(airport_iata)
    proxy = scoring.unmet_demand_proxy(raw["congestion"], raw["activity"])
    return {"airport": airport_iata.upper(), "proxy": proxy, "raw_metrics": raw}


TOOL_IMPLS = {
    "get_airport_metrics": lambda i: _tool_get_airport_metrics(i["airport_iata"]),
    "compare_airports": lambda i: _tool_compare_airports(i["airport_iatas"]),
    "unmet_demand_analysis": lambda i: _tool_unmet_demand_analysis(i["airport_iata"]),
}


def run_turn(messages: list[dict]) -> tuple[list[dict], list[dict]]:
    """Run one full agent turn (may involve several tool round-trips).

    `messages` is the full conversation history including the new user
    message. Returns (updated_history, executed_tool_calls).

    executed_tool_calls is the ground truth for this turn: each entry is the
    exact {name, input, result} dict computed by scoring.py, independent of
    anything Claude writes in prose. The UI renders numbers from this list
    directly - Claude's text is the explanation layered on top, never the
    source of the numbers themselves.
    """
    executed_tool_calls = []

    while True:
        response = client.messages.create(
            model=config.CLAUDE_MODEL,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return messages, executed_tool_calls

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            try:
                result = TOOL_IMPLS[block.name](block.input)
                executed_tool_calls.append({"name": block.name, "input": block.input, "result": result})
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                })
            except (airlabs_client.AirLabsError, Exception) as exc:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": f"Error: {exc}",
                    "is_error": True,
                })

        messages.append({"role": "user", "content": tool_results})
