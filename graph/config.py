import os
import streamlit as st
from dotenv import load_dotenv

from graph.logger import get_logger

load_dotenv()
logger = get_logger("config")


def get_env_var(key: str, required: bool = True):
    """Fetch a config value from Streamlit secrets first, then the environment.

    Set required=False for optional integrations (news, web search, calendar, ...)
    so the app can still start and run with those features simply disabled,
    instead of crashing at import time.
    """
    # Streamlit Cloud / local .streamlit/secrets.toml
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass

    # Local .env file / plain environment variable (e.g. HF Spaces "Repository secrets")
    value = os.getenv(key)
    if value:
        return value

    if required:
        raise ValueError(f"Missing required environment variable: {key}")

    logger.warning(f"Optional environment variable '{key}' is not set — related feature(s) will be disabled.")
    return None


# Required — the app cannot function at all without a working LLM.
GEMINI_API_KEY = get_env_var("GEMINI_API_KEY", required=True)

# Existing optional integrations (previously required — now degrade gracefully instead
# of crashing the whole app if one key is missing).
OPENWEATHER_API_KEY = get_env_var("OPENWEATHER_API_KEY", required=False)
GMAIL_ADDRESS = get_env_var("GMAIL_ADDRESS", required=False)
GMAIL_APP_PASSWORD = get_env_var("GMAIL_APP_PASSWORD", required=False)

# New optional integrations.
NEWS_API_KEY = get_env_var("NEWS_API_KEY", required=False)
TAVILY_API_KEY = get_env_var("TAVILY_API_KEY", required=False)
GOOGLE_CALENDAR_CREDENTIALS_PATH = get_env_var("GOOGLE_CALENDAR_CREDENTIALS_PATH", required=False)
GOOGLE_CALENDAR_TOKEN_PATH = get_env_var("GOOGLE_CALENDAR_TOKEN_PATH", required=False) or "token.json"


def validate_config() -> dict:
    """Return a {feature_name: is_configured} map, and log a one-time startup summary.

    Used by the UI to show tool status in the sidebar, and by app startup to warn
    about disabled features without stopping the app.
    """
    status = {
        "Gemini LLM": bool(GEMINI_API_KEY),
        "Weather": bool(OPENWEATHER_API_KEY),
        "Gmail": bool(GMAIL_ADDRESS and GMAIL_APP_PASSWORD),
        "News Search": bool(NEWS_API_KEY),
        "Web Search": True,  # DuckDuckGo fallback needs no key; Tavily is used if TAVILY_API_KEY is set
        "Calendar": bool(GOOGLE_CALENDAR_CREDENTIALS_PATH),
    }
    for feature, ok in status.items():
        if not ok:
            logger.warning(f"Feature disabled (missing config): {feature}")
    return status
