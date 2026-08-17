# Life Agent Setup Guide

This guide explains how to set up the Life Agent system using synthetic demonstration data. If you intend to use this for personal tracking, ensure you read the [Privacy Threat Model](docs/privacy.md) first.

## 1. Prerequisites

You will need the following API keys/credentials:
- **LLM API Key**: Either an Anthropic API Key (`ANTHROPIC_API_KEY`) or Google AI Studio Key (`GEMINI_API_KEY`).
- **Notion Integration Token** (Optional, for Notion syncing):
  1. Create an integration at [Notion Integrations](https://www.notion.so/my-integrations).
  2. Grant the integration access to the Notion pages you want to track.
- **Gmail App Password** (Optional, for email notifications).
- **ntfy Topic URL** (Optional, for push notifications).

## 2. Local Setup

1. Clone the repository:
   ```bash
   git clone <your-repo-url>
   cd life-agent
   ```
2. Set up a virtual environment and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -e .
   ```
3. Copy the example environment file and configure it:
   ```bash
   cp .env.example .env
   # Edit .env with your keys
   ```

## 3. Running Locally

The system uses an event-driven architecture. You can execute individual tasks or the full sequence:

```bash
# Run a specific task (e.g., evening check-in)
python -m life_agent.agent.main evening_checkin

# Generate synthetic metrics for the dashboard
python -m life_agent.metrics.metrics
```

## 4. Automation

The system is designed to run automatically. See [Automation Guide](docs/automation.md) for configuring continuous execution via GitHub Actions or Windows Task Scheduler.
