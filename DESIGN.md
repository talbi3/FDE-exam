# Design Document — Airport Investment Intelligence Agent

**Goal**: Help analysts identify US airports worth investigating for
terminal expansion, by combining live AirLabs flight data with deterministic
scoring and an LLM for understanding/explanation. The output score is a
relative operational-pressure signal for screening — **not a financial ROI
forecast**.

## Architecture

```
User → Streamlit Chat/Voice → Claude Agent → picks deterministic tool
     → AirLabs API → scoring.py → Claude explains + UI renders results table
```

| File | Responsibility |
|---|---|
| `airlabs_client.py` | HTTP calls to AirLabs (no caching, by design) |
| `scoring.py` | All metric/ranking math — zero LLM involvement |
| `agent.py` | Claude system prompt, tool schemas, tool-use loop |
| `voice.py` | Speech-to-text / text-to-speech (English only) |
| `app.py` | Streamlit UI — renders results table directly from tool JSON, separately from Claude's text |

**Data**: AirLabs REST API (`/schedules`, `/routes`), chosen over BTS/FAA
government sources which turned out to be login-gated or legacy-form-only.
Free tier caps: 100 flights / 50 routes per call (empirically verified) —
all numbers are a time-bounded sample, not full daily/annual totals.

## Scoring Methodology (all in `scoring.py`, pure Python, no LLM)

```
delay_rate  = flights delayed >= 15min / total sampled
cancel_rate = cancelled / total sampled
raw_congestion   = 0.7 × delay_rate + 0.3 × cancel_rate
raw_activity     = sampled flight count
raw_connectivity = unique destinations sampled
long_haul_pct    = routes >= 360min duration / routes with known duration

# Comparing 2+ airports: min-max normalize each raw_* to 0-100
# within the comparison set, then:
Investment Priority Index = 0.40×Congestion + 0.30×Activity + 0.30×Connectivity

# Single airport, unmet-demand question:
activity_fraction = min(total_flights, 100) / 100   # 100 = AirLabs' own page cap
unmet_demand_proxy = 100 × sqrt(raw_congestion × activity_fraction)  # geometric mean:
                                                                       # high only if BOTH elevated
```

Congestion is weighted highest since the goal is spotting infrastructure
pressure. Scores are relative to whichever airports are being compared —
e.g. a Connectivity Score of 0 means "lowest in this set," not "no
destinations." Long-haul (≥360min) and delay (≥15min) are stated working
definitions (the 15min threshold matches BTS/DOT convention).

## Where/How AI Is Used

Claude does exactly three things: (1) parses the question into airport
codes + question type, (2) picks one of three tools —
`get_airport_metrics` / `compare_airports` / `unmet_demand_analysis`, (3)
narrates the already-computed result. **Claude never computes a score** —
enforced structurally, not just by prompt: the UI renders the results table
directly from the tool's JSON, independent of anything Claude writes. This
keeps all scoring deterministic and independently verifiable, while Claude
is responsible only for interpretation and explanation.

## Key Tradeoffs

| Decision | Choice | Tradeoff |
|---|---|---|
| Data source | AirLabs REST API | Fast to integrate; sample-based, not a full government dataset |
| Caching | None — every question hits the live API | Demonstrable/transparent; burns quota faster |
| Single-airport scoring | Raw metrics only, no fixed benchmark set | Avoids inventing a peer baseline; no 0-100 score without a real comparison set |
| Financial data | Not included | Keeps scope honest; the system cannot compute real ROI |

## Limitations

Time-of-day sensitive samples; partial route `duration` coverage skews
long-haul %; no revenue/cost/ROI data is included in the current data
source. **Single-source dependency**: the MVP relies on AirLabs as its only
aviation data provider, so gaps or inaccuracies in its coverage directly
affect the analysis. A production version should cross-validate key metrics
against additional authoritative sources. Output is for **initial
screening**, not a final investment decision.
