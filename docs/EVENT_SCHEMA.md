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

## Known limitation: repeated runs of the same task (deferred)

Two separate things can make a repeated run of one task look wrong. They have different causes and different status.

### 1. Query pairing (reading side) — fixed

`life_agent.events.queries.get_focus_sessions()` pairs `focus_started` with `focus_completed` /
`focus_abandoned` chronologically within each `intent_id` and date. Every end event produces its own
session, so START, STOP (abandoned), START, finish (completed) yields two sessions rather than losing
the completion. This is covered by `test_abandon_then_complete_same_intent`.

### 2. Events dropped while writing (writing side) — deferred, not fixed

`event_model.append_once()` silently skips any event whose `kind` and `dedupe_key` already exist.
The keys built in `event_model.py` carry no per-run discriminator:

| Kind | Dedupe key |
| :--- | :--- |
| `focus_started` | `focus_started:{date}:{intent_id or task-slug}:{source}` |
| `focus_completed` | `focus_completed:{date}:{intent_id or task-slug}` |
| `focus_abandoned` | `focus_abandoned:{date}:{intent_id or task-slug}` |

The desktop Focus tab passes the task's stable id as `intent_id` for every run, so on a given day each
task can store at most one start, one completion and one abandonment. Consequences:

- A retry's `focus_started` is dropped. The query layer derives that run's start as end minus
  `duration_seconds`, so the session is still reported, with a computed start time.
- A second abandonment of the same task on the same day is dropped, so abandoned attempts are undercounted.
- A second completed run of the same task on the same day is dropped, so completed sessions and focus
  time are undercounted.
- The query fix cannot recover these: the events were never persisted.

The Pomodoro app is not affected, because it uses a distinct `intent_id` per session
(`pomodoro:{session_id}`).

**Why deferred:** `append_once` also protects against double-fired writes (for example a retried CLI
call). Adding a per-run discriminator to the keys changes that idempotency contract, and callers such as
the Focus tab would need to supply a per-run id. Existing stored events keep their old keys. That is a
design decision, so `event_model.py` and its dedupe keys are intentionally unchanged.

**Consumers affected:** `get_recent_activity` (including the MCP tool of the same name), the Obsidian daily
note generator, and anything else built on `get_focus_sessions()`.
