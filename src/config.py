import os

from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
AIRLABS_API_KEY = os.environ["AIRLABS_API_KEY"]

CLAUDE_MODEL = "claude-opus-5"
