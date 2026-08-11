import os

from dotenv import load_dotenv

load_dotenv()

# Local dev reads from .env via load_dotenv() above. On Streamlit Community
# Cloud, secrets are set via the app's "Secrets" UI and surface through
# st.secrets - bridge them into os.environ so the rest of the app only ever
# has to deal with one source of truth.
try:
    import streamlit as st

    for _key in ("ANTHROPIC_API_KEY", "AIRLABS_API_KEY"):
        if _key in st.secrets:
            os.environ.setdefault(_key, st.secrets[_key])
except Exception:
    pass

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
AIRLABS_API_KEY = os.environ["AIRLABS_API_KEY"]

CLAUDE_MODEL = "claude-opus-5"
