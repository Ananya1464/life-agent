-- SQLite Canonical Schema for Focus Events

CREATE TABLE IF NOT EXISTS focus_started (
    id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    date TEXT NOT NULL,
    task TEXT NOT NULL,
    intent_id TEXT,
    source TEXT NOT NULL,
    dedupe_key TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS focus_completed (
    id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    date TEXT NOT NULL,
    task TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL,
    intent_id TEXT,
    source TEXT NOT NULL,
    dedupe_key TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS focus_abandoned (
    id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    date TEXT NOT NULL,
    task TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL,
    intent_id TEXT,
    source TEXT NOT NULL,
    dedupe_key TEXT NOT NULL
);
