# Focus Event Schema

This document defines the canonical schema for focus events used within the Ananya OS Life Agent.

## Overview

Events are stored in append-only JSONL format (`data/events.jsonl`).

## Schema Definition

Each event record is a JSON object with the following fields:

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `id` | string (UUID) | Yes | Unique identifier for the event. |
| `ts` | string (ISO8601) | Yes | Timestamp in UTC format (e.g., `YYYY-MM-DDTHH:MM:SS.ffffffZ`). |
| `kind` | string | Yes | Event type (`focus_started`, `focus_completed`, `focus_abandoned`). |
| `date` | string (YYYY-MM-DD) | Yes | Date of the event. |
| `task` | string | Yes | Task description. |
| `duration_seconds` | integer | No | Duration in seconds (required for `focus_completed` and `focus_abandoned`). |
| `intent_id` | string | No | Intent identifier, if applicable. |
| `source` | string | Yes | Source of the event (e.g., `pomodoro_app`). |
| `dedupe_key` | string | Yes | Derived key to ensure idempotency. |

## Examples

### focus_started
```json
{
  "id": "uuid-1234",
  "ts": "2026-09-22T08:00:00Z",
  "kind": "focus_started",
  "date": "2026-09-22",
  "task": "Learning Python",
  "intent_id": null,
  "source": "pomodoro_app",
  "dedupe_key": "focus_started:2026-09-22:uuid-1234"
}
```

### focus_completed
```json
{
  "id": "uuid-5678",
  "ts": "2026-09-22T08:25:00Z",
  "kind": "focus_completed",
  "date": "2026-09-22",
  "task": "Learning Python",
  "duration_seconds": 1500,
  "intent_id": null,
  "source": "pomodoro_app",
  "dedupe_key": "focus_completed:2026-09-22:uuid-5678"
}
```
