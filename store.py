"""Local storage engine — manages events via an append-only JSONL file and in-memory SQLite queries."""
from datetime import datetime, timezone
import json
import pathlib
import sqlite3
import uuid


def append(kind: str, payload: dict) -> str:
    ev_id = uuid.uuid4().hex
    ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    event = {"id": ev_id, "ts": ts, "kind": kind, **payload}

    file_path = pathlib.Path("data/events.jsonl")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

    return ev_id


def load_all() -> list[dict]:
    file_path = pathlib.Path("data/events.jsonl")
    if not file_path.exists():
        return []
    events = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def to_sqlite() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    events = load_all()
    if not events:
        return conn

    # Group events by kind
    by_kind = {}
    for ev in events:
        kind = ev.get("kind")
        if not kind:
            continue
        by_kind.setdefault(kind, []).append(ev)

    for kind, evs in by_kind.items():
        all_keys = set()
        for ev in evs:
            all_keys.update(ev.keys())

        # Determine column types based on values
        col_types = {}
        for key in all_keys:
            if key in ("id", "ts", "kind"):
                col_types[key] = "TEXT"
                continue

            val_types = set()
            for ev in evs:
                val = ev.get(key)
                if val is not None:
                    val_types.add(type(val))

            if not val_types:
                col_types[key] = "TEXT"
            elif val_types == {int}:
                col_types[key] = "INTEGER"
            elif val_types <= {int, float}:
                col_types[key] = "REAL"
            else:
                col_types[key] = "TEXT"

        sanitized_kind = "".join(c for c in kind if c.isalnum() or c == "_")

        col_defs = []
        ordered_keys = ["id", "ts"]
        if "kind" in all_keys:
            ordered_keys.append("kind")
        other_keys = sorted(list(all_keys - set(ordered_keys)))
        ordered_keys.extend(other_keys)

        for key in ordered_keys:
            col_type = col_types.get(key, "TEXT")
            if key == "id":
                col_defs.append("id TEXT PRIMARY KEY")
            else:
                col_defs.append(f"{key} {col_type}")

        conn.execute(f"CREATE TABLE {sanitized_kind} ({', '.join(col_defs)})")

        insert_sql = f"INSERT INTO {sanitized_kind} ({', '.join(ordered_keys)}) VALUES ({', '.join(['?'] * len(ordered_keys))})"

        for ev in evs:
            row = []
            for key in ordered_keys:
                val = ev.get(key)
                if isinstance(val, (dict, list)):
                    val = json.dumps(val, ensure_ascii=False)
                row.append(val)
            conn.execute(insert_sql, row)

    conn.commit()
    return conn
