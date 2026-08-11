"""Static, deterministic airport reference data.

Kept separate from the LLM layer on purpose: which airports count as
"New England" is a factual/geographic decision, not something we want
an LLM guessing differently between runs.
"""

NEW_ENGLAND_AIRPORTS = {
    "BOS": "Boston Logan International",
    "BDL": "Bradley International (Hartford, CT)",
    "PVD": "Rhode Island T.F. Green International (Providence, RI)",
    "PWM": "Portland International Jetport (Portland, ME)",
    "MHT": "Manchester-Boston Regional (Manchester, NH)",
    "BTV": "Patrick Leahy Burlington International (Burlington, VT)",
    "BGR": "Bangor International (Bangor, ME)",
}

# A handful of other airports referenced in the assignment's demo questions,
# for readable labels in the UI. Not exhaustive — the AI layer resolves
# unlisted IATA codes from its own knowledge when the user names a city.
KNOWN_AIRPORTS = {
    **NEW_ENGLAND_AIRPORTS,
    "LAX": "Los Angeles International",
    "SNA": "John Wayne Airport (Santa Ana / Orange County)",
    "ANC": "Ted Stevens Anchorage International",
    "SFO": "San Francisco International",
}


def airport_label(iata: str) -> str:
    name = KNOWN_AIRPORTS.get(iata.upper())
    return f"{iata.upper()} ({name})" if name else iata.upper()
