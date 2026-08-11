import hashlib

import anthropic
import streamlit as st
import streamlit.components.v1 as components

from src import agent, voice

st.set_page_config(page_title="Airport Investment Intelligence Agent", page_icon="✈️")
st.title("✈️ Airport Investment Intelligence Agent")
st.caption(
    "Deterministic scoring over live AirLabs flight data, narrated by Claude. "
    "Scores are relative operational-pressure indices, not financial ROI forecasts."
)

with st.expander("Example questions"):
    st.markdown(
        "- Which airports in New England are strong candidates for terminal expansion?\n"
        "- Compare LA and Santa Ana airport congestion levels.\n"
        "- What is the percentage of long haul flights out of Anchorage airport?\n"
        "- What is the unmet flight demand in SFO airport and why?"
    )

if "messages" not in st.session_state:
    st.session_state.messages = []
if "tool_calls_by_index" not in st.session_state:
    st.session_state.tool_calls_by_index = {}  # message index -> executed_tool_calls
if "last_audio_hash" not in st.session_state:
    st.session_state.last_audio_hash = None


def render_tool_result(tool_call: dict) -> None:
    """Render a tool's output as a table straight from the JSON scoring.py
    produced - this never passes through Claude's text generation, so the
    numbers on screen cannot be a transcription error or a hallucination.
    """
    name, result = tool_call["name"], tool_call["result"]

    if name == "compare_airports":
        rows = [
            {
                "Airport": r["airport"],
                "Investment Priority Index": r["investment_priority_index"],
                "Congestion Score": r["congestion_score"],
                "Activity Score": r["activity_score"],
                "Connectivity Score": r["connectivity_score"],
            }
            for r in result["ranked"]
        ]
        st.caption(f"Deterministic scores (scoring.py) — comparison set of {result['comparison_set_size']}")
        st.dataframe(rows, hide_index=True, use_container_width=True)

    elif name == "get_airport_metrics":
        c, a, conn = result["congestion"], result["activity"], result["connectivity"]
        rows = [
            {"Metric": "Delay rate", "Value": _pct(c["delay_rate"])},
            {"Metric": "Cancel rate", "Value": _pct(c["cancel_rate"])},
            {"Metric": "Avg delay (min)", "Value": c["avg_delay_min"]},
            {"Metric": "Sampled flights", "Value": a["total_flights"]},
            {"Metric": "Unique destinations (sample)", "Value": conn["unique_destinations"]},
            {"Metric": "Long-haul %", "Value": conn["long_haul_pct"]},
        ]
        st.caption(f"Deterministic metrics (scoring.py) — {result['congestion']['total_flights']} flights sampled")
        st.dataframe(rows, hide_index=True, use_container_width=True)

    elif name == "unmet_demand_analysis":
        p = result["proxy"]
        rows = [
            {"Metric": "Unmet Demand Proxy (0-100)", "Value": p["unmet_demand_proxy"]},
            {"Metric": "Congestion component", "Value": p["congestion_component"]},
            {"Metric": "Activity component", "Value": p["activity_component"]},
        ]
        st.caption(f"Deterministic proxy (scoring.py) — {result['airport']}")
        st.dataframe(rows, hide_index=True, use_container_width=True)


def _pct(x):
    return f"{x:.1%}" if x is not None else "n/a"


def extract_text(content) -> str:
    blocks = content if isinstance(content, list) else [content]
    parts = []
    for b in blocks:
        if isinstance(b, str):
            parts.append(b)
        elif hasattr(b, "type") and b.type == "text":
            parts.append(b.text)
        elif isinstance(b, dict) and b.get("type") == "text":
            parts.append(b.get("text", ""))
    return "\n".join(t for t in parts if t)


for idx, msg in enumerate(st.session_state.messages):
    if msg["role"] not in ("user", "assistant"):
        continue
    text = extract_text(msg["content"])
    if not text:
        continue
    with st.chat_message(msg["role"]):
        for tool_call in st.session_state.tool_calls_by_index.get(idx, []):
            render_tool_result(tool_call)
        st.markdown(text)
        if msg["role"] == "assistant":
            components.html(voice.speak_button_html(text, key=f"hist-{idx}"), height=40)


def handle_prompt(prompt: str) -> None:
    with st.chat_message("user"):
        st.markdown(prompt)

    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("assistant"):
        with st.spinner("Pulling flight data and scoring..."):
            try:
                st.session_state.messages, executed_tool_calls = agent.run_turn(st.session_state.messages)
            except anthropic.APIStatusError as exc:
                st.session_state.messages.pop()  # drop the unanswered user turn
                st.error(f"Claude API error ({exc.status_code}): {exc.message}")
                st.stop()

        final_index = len(st.session_state.messages) - 1
        st.session_state.tool_calls_by_index[final_index] = executed_tool_calls

        for tool_call in executed_tool_calls:
            render_tool_result(tool_call)

        answer = extract_text(st.session_state.messages[-1]["content"])
        st.markdown(answer)
        components.html(voice.speak_button_html(answer, key=f"live-{final_index}"), height=40)


prompt = st.chat_input("Ask about an airport, e.g. \"Compare LAX and SNA congestion\"")

with st.expander("🎤 Or ask by voice"):
    audio_value = st.audio_input("Record your question")
    if audio_value is not None:
        audio_bytes = audio_value.getvalue()
        audio_hash = hashlib.md5(audio_bytes).hexdigest()
        if audio_hash != st.session_state.last_audio_hash:
            st.session_state.last_audio_hash = audio_hash
            try:
                transcribed = voice.transcribe(audio_bytes)
                st.success(f"Heard: \"{transcribed}\"")
                prompt = prompt or transcribed
            except voice.TranscriptionError as exc:
                st.warning(str(exc))

if prompt:
    handle_prompt(prompt)
