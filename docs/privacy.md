# Privacy Threat Model

Life Agent is designed to handle personal, behavioral, and potentially sensitive productivity data. This document outlines the data boundaries and privacy considerations for the system.

## Data Boundaries

The project conceptually separates the **engineering architecture** (public) from the **personal dataset** (private).

### Data handled by the private deployment
When deployed personally, Life Agent processes:
* Calendar events and schedules
* Task history and completion rates
* Push notifications (via ntfy)
* Personal notes and reflections
* Behavioral event logs
* Notion database contents

### Data included in the public repository
To demonstrate the system architecture safely, this repository contains only:
* Source code and architecture diagrams
* Synthetic event logs (`data/example_events.jsonl`)
* Example prompts
* Anonymized screenshots
* Documentation

### Data NEVER committed to version control
The following are strictly excluded via `.gitignore` and must never be committed:
* API keys (`GEMINI_API_KEY`, etc.)
* Authentication tokens (`NOTION_TOKEN`)
* Personal calendar URLs (iCal links)
* Personal Notion Database IDs
* Email credentials (e.g., Gmail App Passwords)
* Personal event logs (`data/events.jsonl` or real `metrics.json`)

## Security Best Practices
- **Environment Variables:** All secrets are loaded via a local `.env` file or securely injected via GitHub Actions Secrets.
- **Log Sanitization:** Debug logging (especially SMTP payloads) must never be enabled in public continuous integration environments to prevent credential leakage in CI logs.
- **Access Control:** The GitHub Pages dashboard is static; if it contains personal data in a real deployment, the repository must be kept private, or authentication must be added to the Pages deployment.
