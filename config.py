"""Central config — reads environment variables, auto-loading .env if present."""
import os
import pathlib


def _load_dotenv():
    env_file = pathlib.Path(__file__).parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


_load_dotenv()

# --- LLM brain ---
# Force "gemini" to avoid any Claude token spend. Set LLM_PROVIDER=claude
# in .env to switch back (requires ANTHROPIC_API_KEY).
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")

# --- Notion ---
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
# Daily Log data source (inside "🌱 Daily Life Tracker")
DAILY_LOG_DATA_SOURCE_ID = os.getenv(
    "DAILY_LOG_DATA_SOURCE_ID", "c4764f6a-59f1-466d-843f-eb798eb3b033"
)
# "Weight Loss Plan — 83 → 53 kg" page
WEIGHT_LOSS_PAGE_ID = os.getenv(
    "WEIGHT_LOSS_PAGE_ID", "37ade9d3d9b781a9bfcbecdf326bf6b9"
)
# "Evening Check-in" database
EVENING_CHECKIN_DB_ID = os.getenv(
    "EVENING_CHECKIN_DB_ID", "32758b21da4e420c9952aa3e1b130d4c"
)
# "Dopamine Menu" database
DOPAMINE_MENU_DB_ID = os.getenv("DOPAMINE_MENU_DB_ID", "")
# "Brain Dump" database
BRAIN_DUMP_DB_ID = os.getenv("BRAIN_DUMP_DB_ID", "")
# "Replies" database for mirrored parsed inbound replies
REPLIES_DB_ID = os.getenv("REPLIES_DB_ID", "")
# Life OS metrics database
LIFE_OS_METRICS_DB_ID = os.getenv(
    "LIFE_OS_METRICS_DB_ID", "35496a3a-c8ba-4fd6-81bd-66f66719f8f2"
)
# Life areas and goals database
LIFE_AREAS_GOALS_DB_ID = os.getenv(
    "LIFE_AREAS_GOALS_DB_ID", "8f4d05f9-dfa1-4cea-995c-d92ca00b540d"
)
# Main dashboard page
LIFE_OS_DASHBOARD_PAGE_ID = os.getenv(
    "LIFE_OS_DASHBOARD_PAGE_ID", "3b9de9d3-d9b7-81ba-b1b9-ef4a6d807cd8"
)

# --- Email (Gmail SMTP with an App Password) ---
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "ananyadubey1464@gmail.com")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")  # empty = skip email silently

# --- Google Calendar (optional, secret iCal URL — read-only, no OAuth) ---
ICAL_URL = os.getenv("ICAL_URL", "")

# Push Notifications (ntfy.sh)
NTFY_TOPIC = os.getenv("NTFY_TOPIC", "")

# --- Reminders (optional Notion database for time-blocked reminders) ---
REMINDERS_DB_ID = os.getenv("REMINDERS_DB_ID", "")

# --- Timezone ---
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")
