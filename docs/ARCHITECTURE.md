# Life Agent: Comprehensive Architecture & Function Reference

`life-agent` is an autonomous personal AI life management platform built in Python. It integrates LLMs (Google Gemini), Notion APIs, email/notification dispatchers, event logging engines, metric tracking analytics, and a Tkinter desktop GUI.

---

## 1. System Overview & Architecture Diagram

```
                              ┌──────────────────────────────────┐
                              │    GitHub Actions (agent.yml)    │
                              └────────────────┬─────────────────┘
                                               │ Cron Tasks
                                               ▼
┌──────────────────┐               ┌───────────────────────┐
│ Desktop GUI      │ ───Sync─────► │ agent/main.py         │ ───LLM───► ┌──────────────────┐
│ (Tkinter Desktop)│               │ (Task Dispatcher)     │            │ Google Gemini    │
└────────┬─────────┘               └───────────┬───────────┘            └──────────────────┘
         │                                     │
         ▼                                     ▼
┌──────────────────┐               ┌───────────────────────┐            ┌──────────────────┐
│ events/store.py  │               │ agent/tasks/*         │ ───HTTP──► │ Notion API v2025 │
│ (events.jsonl)   │               │ (meal_plan, etc.)     │            │ (Data Sources/DB)│
└──────────────────┘               └───────────┬───────────┘            └──────────────────┘
                                               │
                                               ▼
                                   ┌───────────────────────┐
                                   │ notifications/        │ ───SMTP──► User Email &
                                   │ (emailer, ntfy)       │            ntfy Push
                                   └───────────────────────┘
```

---

## 2. Component Breakdown & Function Reference

### 2.1 Configuration Layer (`src/life_agent/config.py`)
Centralized configuration manager loading environment variables from `.env`.

- **Key Configuration Fields**:
  - `NOTION_TOKEN`: Bearer token for Notion API authentication.
  - `GEMINI_API_KEY`: API key for Google Gemini LLM.
  - `GMAIL_ADDRESS` & `GMAIL_APP_PASSWORD`: SMTP/IMAP credentials for email notifications and reply ingestion.
  - `DAILY_LOG_DATA_SOURCE_ID`, `REPLIES_DB_ID`, `REMINDERS_DB_ID`, `EVENING_CHECKIN_DB_ID`, `DOPAMINE_MENU_DB_ID`, `BRAIN_DUMP_DB_ID`, `LIFE_AREAS_GOALS_DB_ID`, `EVENTS_SYNC_DATA_SOURCE_ID`: Target Notion database/data-source IDs.

---

### 2.2 Event Store & Audit Model (`src/life_agent/events/`)

#### `store.py`
Persistent append-only event logging system.
- `append(kind: str, payload: dict) -> dict`: Appends an event object with an ISO timestamp and unique ID to `data/events.jsonl`.
- `load_all() -> list[dict]`: Reads and parses all recorded events from `data/events.jsonl`.
- `find(kind: str) -> list[dict]`: Filters stored events matching the specified `kind`.

#### `event_model.py`
High-level event contracts and recorder functions.
- `record_task_started(task: str, date_iso: str)`: Records `task_started` event.
- `record_task_completed(task: str, date_iso: str)`: Records `task_completed` event.
- `record_reply_parsed(event: dict)`: Validates and logs parsed check-in email replies.
- `record_notion_synced(event_id: str, notion_page_id: str)`: Records Notion synchronization mapping to avoid double-syncing.

---

### 2.3 Notion Integration Layer (`src/life_agent/integrations/notion_api.py`)

Direct REST integration using Notion API version `2025-09-03` with custom block converters and pagination handlers.

- `_req(method: str, path: str, **kwargs) -> dict`: Executes low-level HTTP requests to `https://api.notion.com/v1`, raising `RuntimeError` on API errors.
- `md_to_blocks(md: str) -> list[dict]`: Converts Markdown strings into structured Notion block objects (`heading_2`, `heading_3`, `bulleted_list_item`, `numbered_list_item`, `quote`, `divider`, `paragraph`).
- `query_database(database_id: str, filter_dict: dict = None) -> list[dict]`: Executes paginated POST queries against `/databases/{database_id}/query`, automatically traversing `start_cursor` / `next_cursor` until all rows are returned.
- `query_data_source(data_source_id: str, filter_dict: dict = None) -> list[dict]`: Executes paginated POST queries against `/data_sources/{data_source_id}/query` for data source endpoints.
- `find_entry_by_date(date_iso: str) -> dict | None`: Queries the Daily Log data source for an entry matching a specific date.
- `create_daily_entry(day_label: str, date_iso: str, body_md: str) -> str`: Creates a new Daily Log page with markdown blocks.
- `replace_section(page_id: str, heading_contains: str, new_md: str)`: Atomically updates blocks under a specific `## Section` heading.
- `sync_event(event: dict) -> str`: Mirrors a structured check-in event into the Notion Replies database.

---

### 2.4 LLM & Agent Core (`src/life_agent/agent/`)

#### `llm.py`
Interface to Gemini and NVIDIA LLM APIs.
- `generate(prompt: str, web_search: bool = False, temperature: float = 0.7, think: bool = True, provider: str | None = None) -> str`: Generates text using the configured provider, with optional per-call provider override.
- `generate_json(prompt: str, schema: dict = None) -> dict`: Generates structured JSON responses with robust fallback parsing.

#### `main.py`
CLI entrypoint dispatched by schedule or manual invocation.
- `run(task: str)`: Dynamically loads and runs a task from `life_agent.agent.tasks.<task>`, managing task start notifications, execution, completion logs, and metric updates.
- `read_replies()`: Ingests email replies and updates system metrics.
- `--selftest`: Runs email connectivity self-tests.

#### Scheduled Task Runners (`src/life_agent/agent/tasks/`)
- `meal_plan.py`: Generates daily dietary/meal recommendations.
- `ai_edge.py`: Performs automated tech research and deep work summaries.
- `evening_checkin.py`: Generates evening reflection prompts.
- `goal_planner.py`: Tracks goal milestones and progress.
- `tomorrow_planner.py`: Plans upcoming tasks for the next calendar day.
- `set_reminders.py`: Generates timely reminders in Notion/Email.
- `weekly_review.py`: Compiles Sunday weekly review metrics.

---

### 2.5 Notification Dispatcher (`src/life_agent/notifications/`)

- `emailer.py`: `send_email(subject: str, body: str, debug: bool = False)` sends outbound emails over SMTP via Gmail.
- `inbound.py`: `fetch_replies() -> list[dict]` connects via IMAP, parses user reply emails, extracts energy/sleep/soreness/tasks/captures payload fields.
- `outbound.py`: `send_task_start_notification(task: str)` dispatches push notifications (via `ntfy` HTTP API or email) when tasks begin.

---

### 2.6 Metrics & Analytics (`src/life_agent/metrics/metrics.py`)

Computes health, consistency, and life domain metrics.
- `calculate_streaks() -> dict`: Calculates current and longest check-in streaks.
- `update_metrics() -> dict`: Aggregates check-in logs, calculates completion percentages, syncs metrics to Notion `LIFE_AREAS_GOALS_DB_ID`.

---

### 2.7 Desktop GUI (`src/life_agent/desktop/`)

Tkinter desktop application container.

- `app.py`: `LifeAgentDesktop(tk.Tk)` initializes 500×550 window with tabbed notebook (`PlanTab`, `FocusTab`, `TypewriterTab`).
- `plan_tab.py`: Plan management interface with manual "☁ Sync" button.
- `focus_tab.py`: Pomodoro timer component.
- `typewriter_tab.py`: Markdown checklist tracker component.
- `sync.py`:
  - `_event_exists_in_notion(event_id: str) -> bool`: Checks Notion for duplicate event records, re-raising API errors to prevent false duplicate creation (Bug 12 fix).
  - `push_to_cloud(events: list[dict])`: One-way push sync from local event log to Notion cloud databases.
  - `sync_events()`: Main sync orchestrator returning success/failure statistics.

---

## 3. Data Flow & Security Guarantees

1. **Local-First Auditing**: All events and replies are recorded to local append-only JSONL storage (`data/events.jsonl`) prior to cloud synchronization.
2. **Idempotent Notion Syncing**: Tracked via `.synced_event_ids.json` and explicit `event_id` verification queries.
3. **API Error Handling**: Notion API failures re-raise errors instead of returning false negative existence checks, preventing duplicate entries.
4. **Environment Security**: No hardcoded API keys or personal credentials; loaded strictly from environment or `.env` file via `life_agent.config`.
