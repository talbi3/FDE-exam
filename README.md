# Airport Investment Intelligence Agent

A chat agent that helps identify US airports worth investigating for
terminal/infrastructure expansion, by combining live flight data from
AirLabs with a deterministic scoring layer and Claude for natural-language
understanding and explanation.

See [DESIGN.md](DESIGN.md) for architecture, scoring methodology, and key
tradeoffs.

## Setup

**1. Install dependencies** (Python 3.11+):

```bash
pip install -r requirements.txt
```

**2. Add API keys.** Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=sk-ant-...
AIRLABS_API_KEY=...
```

- Anthropic key: [console.anthropic.com](https://console.anthropic.com) →
  API Keys. Needs available credit balance.
- AirLabs key: [airlabs.co](https://airlabs.co) → free-tier signup (self-service,
  no approval wait). Free tier is capped at **1,000 requests/month** — this
  app makes 2 live AirLabs calls per airport per question (no caching, by
  design — see DESIGN.md), so avoid repeatedly re-asking the same question
  during testing.

**3. Run:**

```bash
streamlit run app.py
```

Opens at `http://localhost:8501`.

## Try it

- "Which airports in New England are strong candidates for terminal expansion?"
- "Compare LA and Santa Ana airport congestion levels."
- "What is the percentage of long haul flights out of Anchorage airport?"
- "What is the unmet flight demand in SFO airport and why?"

Each answer shows two things: a table of numbers computed by `scoring.py`
directly, and Claude's explanation underneath it — see DESIGN.md §7 for why
they're kept separate.

## Voice (bonus)

- **Speak a question**: open "🎤 Or ask by voice", record, and it transcribes
  automatically (English only).
- **Hear an answer**: click "🔊 Read aloud" under any response; "⏹ Stop" cancels
  it mid-sentence.

Both run through free/built-in mechanisms (browser `speechSynthesis` for
output, `SpeechRecognition`'s free Google endpoint for input) — no extra API
key needed.

## Project structure

```
app.py                    Streamlit chat UI
src/
  config.py                API keys, model name
  airports.py                Fixed airport reference data (New England list, etc.)
  airlabs_client.py            AirLabs HTTP client
  scoring.py                     Deterministic scoring logic - no LLM calls
  agent.py                         Claude tool-use loop + system prompt
  voice.py                           Speech-to-text / text-to-speech
requirements.txt
DESIGN.md                  Architecture, scoring methodology, tradeoffs
```

## Notes

- No caching: every question makes live API calls. This is a deliberate
  choice for demonstrability over quota efficiency (see DESIGN.md §9) —
  budget your testing accordingly.
- Numbers are sampled snapshots (up to 100 flights / 50 routes per airport,
  ~10h forward window), not full daily or annual totals. The agent states
  this in every answer.
