"""Tests for Phase 3 deterministic activity tool."""
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
import sys

import pytest

# Set up PYTHONPATH
sys.path.insert(0, 'src')

from life_agent.tools import activity
from life_agent.events import queries


class TestActivityTool:
    """Tests for activity.get_activity() deterministic tool."""

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        """Set up test events, tear down after each test."""
        # Create events.jsonl if needed
        events_dir = Path("data")
        events_dir.mkdir(parents=True, exist_ok=True)
        self.events_file = events_dir / "events.jsonl"

        # Save existing events (if any)
        self.backup_file = None
        if self.events_file.exists():
            self.backup_file = self.events_file.read_bytes()

        yield

        # Restore events
        if self.backup_file:
            self.events_file.write_bytes(self.backup_file)
        elif self.events_file.exists():
            self.events_file.unlink()

    def write_test_events(self, events):
        """Write test events to events.jsonl."""
        with open(self.events_file, "w", encoding="utf-8") as f:
            for event in events:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def test_real_activity_returned_correctly(self):
        """T1: Real/fixture activity is returned correctly."""
        test_date = "2026-09-21"
        base_time = datetime(2026, 9, 21, 9, 0, 0, tzinfo=timezone.utc)

        events = [
            {
                "id": "t1-1-start",
                "ts": base_time.isoformat().replace("+00:00", "Z"),
                "kind": "focus_started",
                "date": test_date,
                "task": "Test Task 1",
                "intent_id": "pomodoro:t1-1",
                "source": "pomodoro_app",
                "dedupe_key": "focus_started:t1-1"
            },
            {
                "id": "t1-1-end",
                "ts": (base_time + timedelta(minutes=25)).isoformat().replace("+00:00", "Z"),
                "kind": "focus_completed",
                "date": test_date,
                "task": "Test Task 1",
                "duration_seconds": 1500,
                "intent_id": "pomodoro:t1-1",
                "source": "pomodoro_app",
                "dedupe_key": "focus_completed:t1-1"
            }
        ]

        self.write_test_events(events)

        result = activity.get_activity(test_date)

        assert len(result) == 1, "Expected 1 session"
        assert result[0]["task"] == "Test Task 1"
        assert result[0]["status"] == "completed"
        assert result[0]["duration_seconds"] == 1500

    def test_three_sessions_represented_correctly(self):
        """T2: Three sessions are represented correctly."""
        test_date = "2026-09-21"
        base_time = datetime(2026, 9, 21, 9, 0, 0, tzinfo=timezone.utc)

        events = []
        for i in range(1, 4):
            start_offset = (i - 1) * 40
            events.append({
                "id": f"t2-{i}-start",
                "ts": (base_time + timedelta(minutes=start_offset)).isoformat().replace("+00:00", "Z"),
                "kind": "focus_started",
                "date": test_date,
                "task": f"Session {i}",
                "intent_id": f"pomodoro:t2-{i}",
                "source": "pomodoro_app",
                "dedupe_key": f"focus_started:t2-{i}"
            })
            events.append({
                "id": f"t2-{i}-end",
                "ts": (base_time + timedelta(minutes=start_offset + 25)).isoformat().replace("+00:00", "Z"),
                "kind": "focus_completed",
                "date": test_date,
                "task": f"Session {i}",
                "duration_seconds": 1500,
                "intent_id": f"pomodoro:t2-{i}",
                "source": "pomodoro_app",
                "dedupe_key": f"focus_completed:t2-{i}"
            })

        self.write_test_events(events)

        result = activity.get_activity(test_date)

        assert len(result) == 3, f"Expected 3 sessions, got {len(result)}"
        for i in range(3):
            assert result[i]["task"] == f"Session {i+1}"

    def test_completed_and_abandoned_status_preserved(self):
        """T3: Completed and abandoned sessions preserve status."""
        test_date = "2026-09-21"
        base_time = datetime(2026, 9, 21, 9, 0, 0, tzinfo=timezone.utc)

        events = [
            {
                "id": "t3-c-start",
                "ts": base_time.isoformat().replace("+00:00", "Z"),
                "kind": "focus_started",
                "date": test_date,
                "task": "Completed Task",
                "intent_id": "pomodoro:t3-c",
                "source": "pomodoro_app",
                "dedupe_key": "focus_started:t3-c"
            },
            {
                "id": "t3-c-end",
                "ts": (base_time + timedelta(minutes=25)).isoformat().replace("+00:00", "Z"),
                "kind": "focus_completed",
                "date": test_date,
                "task": "Completed Task",
                "duration_seconds": 1500,
                "intent_id": "pomodoro:t3-c",
                "source": "pomodoro_app",
                "dedupe_key": "focus_completed:t3-c"
            },
            {
                "id": "t3-a-start",
                "ts": (base_time + timedelta(minutes=40)).isoformat().replace("+00:00", "Z"),
                "kind": "focus_started",
                "date": test_date,
                "task": "Abandoned Task",
                "intent_id": "pomodoro:t3-a",
                "source": "pomodoro_app",
                "dedupe_key": "focus_started:t3-a"
            },
            {
                "id": "t3-a-end",
                "ts": (base_time + timedelta(minutes=52)).isoformat().replace("+00:00", "Z"),
                "kind": "focus_abandoned",
                "date": test_date,
                "task": "Abandoned Task",
                "duration_seconds": 720,
                "intent_id": "pomodoro:t3-a",
                "source": "pomodoro_app",
                "dedupe_key": "focus_abandoned:t3-a"
            }
        ]

        self.write_test_events(events)

        result = activity.get_activity(test_date)

        assert len(result) == 2
        assert result[0]["status"] == "completed"
        assert result[1]["status"] == "abandoned"

    def test_duration_matches_queries_exactly(self):
        """T4: Duration matches queries.py exactly."""
        test_date = "2026-09-21"
        base_time = datetime(2026, 9, 21, 9, 0, 0, tzinfo=timezone.utc)

        test_duration = 2345
        events = [
            {
                "id": "t4-start",
                "ts": base_time.isoformat().replace("+00:00", "Z"),
                "kind": "focus_started",
                "date": test_date,
                "task": "Duration Test",
                "intent_id": "pomodoro:t4",
                "source": "pomodoro_app",
                "dedupe_key": "focus_started:t4"
            },
            {
                "id": "t4-end",
                "ts": (base_time + timedelta(seconds=test_duration)).isoformat().replace("+00:00", "Z"),
                "kind": "focus_completed",
                "date": test_date,
                "task": "Duration Test",
                "duration_seconds": test_duration,
                "intent_id": "pomodoro:t4",
                "source": "pomodoro_app",
                "dedupe_key": "focus_completed:t4"
            }
        ]

        self.write_test_events(events)

        # Compare with queries.py directly
        query_result = queries.get_focus_sessions(test_date)
        activity_result = activity.get_activity(test_date)

        assert query_result[0]["duration_seconds"] == test_duration
        assert activity_result[0]["duration_seconds"] == test_duration
        assert activity_result[0]["duration_seconds"] == query_result[0]["duration_seconds"]

    def test_start_end_match_queries_exactly(self):
        """T5: Start/end match queries.py exactly."""
        test_date = "2026-09-21"
        base_time = datetime(2026, 9, 21, 10, 30, 45, tzinfo=timezone.utc)
        start_ts = base_time.isoformat().replace("+00:00", "Z")
        end_ts = (base_time + timedelta(seconds=1800)).isoformat().replace("+00:00", "Z")

        events = [
            {
                "id": "t5-start",
                "ts": start_ts,
                "kind": "focus_started",
                "date": test_date,
                "task": "Timestamp Test",
                "intent_id": "pomodoro:t5",
                "source": "pomodoro_app",
                "dedupe_key": "focus_started:t5"
            },
            {
                "id": "t5-end",
                "ts": end_ts,
                "kind": "focus_completed",
                "date": test_date,
                "task": "Timestamp Test",
                "duration_seconds": 1800,
                "intent_id": "pomodoro:t5",
                "source": "pomodoro_app",
                "dedupe_key": "focus_completed:t5"
            }
        ]

        self.write_test_events(events)

        query_result = queries.get_focus_sessions(test_date)
        activity_result = activity.get_activity(test_date)

        assert query_result[0]["start"] == start_ts
        assert query_result[0]["end"] == end_ts
        assert activity_result[0]["start"] == start_ts
        assert activity_result[0]["end"] == end_ts

    def test_special_characters_survive(self):
        """T6: Special characters (Unicode, quotes, pipes, emojis) survive."""
        test_date = "2026-09-21"
        base_time = datetime(2026, 9, 21, 9, 0, 0, tzinfo=timezone.utc)

        special_task = 'Review "Code & Design" | Q3 → 2026-09-30 ☕'
        events = [
            {
                "id": "t6-start",
                "ts": base_time.isoformat().replace("+00:00", "Z"),
                "kind": "focus_started",
                "date": test_date,
                "task": special_task,
                "intent_id": "pomodoro:t6",
                "source": "pomodoro_app",
                "dedupe_key": "focus_started:t6"
            },
            {
                "id": "t6-end",
                "ts": (base_time + timedelta(minutes=20)).isoformat().replace("+00:00", "Z"),
                "kind": "focus_completed",
                "date": test_date,
                "task": special_task,
                "duration_seconds": 1200,
                "intent_id": "pomodoro:t6",
                "source": "pomodoro_app",
                "dedupe_key": "focus_completed:t6"
            }
        ]

        self.write_test_events(events)

        result = activity.get_activity(test_date)

        assert result[0]["task"] == special_task, f"Expected '{special_task}', got '{result[0]['task']}'"

    def test_empty_date_returns_empty_result(self):
        """T7: Empty date returns no fabricated activity."""
        # No events written
        self.events_file.touch()

        result = activity.get_activity("2026-09-15")

        assert result == [], f"Expected empty list, got {result}"

    def test_invalid_date_handled_safely(self):
        """T8: Invalid date is handled safely."""
        # Write some events (unrelated to our invalid date)
        test_date = "2026-09-21"
        base_time = datetime(2026, 9, 21, 9, 0, 0, tzinfo=timezone.utc)

        events = [
            {
                "id": "t8-start",
                "ts": base_time.isoformat().replace("+00:00", "Z"),
                "kind": "focus_started",
                "date": test_date,
                "task": "Valid Task",
                "intent_id": "pomodoro:t8",
                "source": "pomodoro_app",
                "dedupe_key": "focus_started:t8"
            }
        ]

        self.write_test_events(events)

        # Query with invalid dates
        invalid_dates = [
            "2026-13-01",  # Invalid month
            "2026-02-30",  # Invalid day
            "not-a-date",
            "2026/09/21",  # Wrong format
            None,
            123,
        ]

        for invalid_date in invalid_dates:
            try:
                result = activity.get_activity(invalid_date)
                assert result == [], f"Expected empty for invalid date {invalid_date}, got {result}"
            except Exception as e:
                pytest.fail(f"Should handle invalid date {invalid_date} safely, got exception: {e}")

    def test_tool_does_not_read_obsidian_markdown(self):
        """T9: Tool does not read Obsidian Markdown."""
        # Create Markdown file (should be ignored)
        md_file = Path("02_EXECUTION/Daily/2026-09-21.md")
        md_file.parent.mkdir(parents=True, exist_ok=True)
        md_file.write_text("# Daily Activity\n\n### Session 1: Fake Task\n- **Status:** completed\n")

        # Clear events.jsonl (tool should read this, not Markdown)
        if self.events_file.exists():
            self.events_file.unlink()
        self.events_file.touch()

        result = activity.get_activity("2026-09-21")

        # Should be empty (reading JSONL, not Markdown)
        assert result == [], "Tool should read JSONL, not Markdown"

        # Clean up
        md_file.unlink()
        md_file.parent.rmdir()

    def test_tool_does_not_access_sqlite(self):
        """T10: Tool does not access SQLite."""
        test_date = "2026-09-21"
        base_time = datetime(2026, 9, 21, 9, 0, 0, tzinfo=timezone.utc)

        events = [
            {
                "id": "t10-start",
                "ts": base_time.isoformat().replace("+00:00", "Z"),
                "kind": "focus_started",
                "date": test_date,
                "task": "SQLite Test",
                "intent_id": "pomodoro:t10",
                "source": "pomodoro_app",
                "dedupe_key": "focus_started:t10"
            },
            {
                "id": "t10-end",
                "ts": (base_time + timedelta(minutes=15)).isoformat().replace("+00:00", "Z"),
                "kind": "focus_completed",
                "date": test_date,
                "task": "SQLite Test",
                "duration_seconds": 900,
                "intent_id": "pomodoro:t10",
                "source": "pomodoro_app",
                "dedupe_key": "focus_completed:t10"
            }
        ]

        self.write_test_events(events)

        # Call tool
        result = activity.get_activity(test_date)

        # Should return JSONL data successfully (not SQLite)
        assert len(result) == 1
        assert result[0]["task"] == "SQLite Test"
