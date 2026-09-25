"""Tests for queries.py - Phase 1 query layer."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date, timedelta
from hashlib import sha256
from pathlib import Path


class TestQueries(unittest.TestCase):
    """Test the query layer for focus events."""

    @classmethod
    def setUpClass(cls):
        """Record hash of real data/events.jsonl if it exists."""
        cls.real_events_path = Path("D:/life-agent/data/events.jsonl")
        if cls.real_events_path.exists():
            with open(cls.real_events_path, "rb") as f:
                cls.real_events_hash_before = sha256(f.read()).hexdigest()
        else:
            cls.real_events_hash_before = None

    @classmethod
    def tearDownClass(cls):
        """Verify real data/events.jsonl is untouched."""
        if cls.real_events_hash_before:
            with open(cls.real_events_path, "rb") as f:
                hash_after = sha256(f.read()).hexdigest()
            assert hash_after == cls.real_events_hash_before, "Real events.jsonl was modified!"

    def setUp(self):
        """Create temp directory with events and change to it."""
        self.temp_dir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.temp_dir)
        self.data_dir = Path(self.temp_dir) / "data"
        self.data_dir.mkdir(exist_ok=True)

    def tearDown(self):
        """Restore working directory."""
        os.chdir(self.old_cwd)

    def write_event(self, kind, **kwargs):
        """Helper: write a single event to JSONL."""
        events_file = self.data_dir / "events.jsonl"
        event = {
            "id": f"test-{kind}",
            "ts": kwargs.get("ts", "2026-09-21T10:00:00Z"),
            "kind": kind,
            **kwargs
        }
        with open(events_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

    def run_query(self, date_arg, json_flag=False):
        """Helper: run queries CLI."""
        args = [sys.executable, "-m", "life_agent.events.queries", date_arg]
        if json_flag:
            args.append("--json")

        result = subprocess.run(
            args,
            capture_output=True,
            cwd=self.temp_dir,
            env={**os.environ, "PYTHONPATH": "D:\\life-agent\\src"}
        )
        return result

    def load_json_output(self, result):
        """Parse JSON output from query result."""
        if result.returncode != 0:
            return None
        return json.loads(result.stdout.decode("utf-8"))

    # Test: paired session
    def test_paired_session(self):
        """Test: started + completed events are paired."""
        self.write_event("focus_started", date="2026-09-21", task="Task A", intent_id="p:s1", source="pomodoro_app")
        self.write_event("focus_completed", date="2026-09-21", task="Task A", duration_seconds=1500, intent_id="p:s1", source="pomodoro_app", ts="2026-09-21T10:25:00Z")

        result = self.run_query("2026-09-21", json_flag=True)
        sessions = self.load_json_output(result)

        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["task"], "Task A")
        self.assertEqual(sessions[0]["duration_seconds"], 1500)
        self.assertEqual(sessions[0]["status"], "completed")

    # Test: two same-task sessions
    def test_two_same_task_sessions(self):
        """Test: two sessions with same task but different intent_ids both persist."""
        self.write_event("focus_started", date="2026-09-21", task="Task A", intent_id="p:s1", source="pomodoro_app", ts="2026-09-21T10:00:00Z")
        self.write_event("focus_completed", date="2026-09-21", task="Task A", duration_seconds=1500, intent_id="p:s1", source="pomodoro_app", ts="2026-09-21T10:25:00Z")

        self.write_event("focus_started", date="2026-09-21", task="Task A", intent_id="p:s2", source="pomodoro_app", ts="2026-09-21T11:00:00Z")
        self.write_event("focus_completed", date="2026-09-21", task="Task A", duration_seconds=1500, intent_id="p:s2", source="pomodoro_app", ts="2026-09-21T11:25:00Z")

        result = self.run_query("2026-09-21", json_flag=True)
        sessions = self.load_json_output(result)

        self.assertEqual(len(sessions), 2)

    # Test: unfinished session
    def test_unfinished_session(self):
        """Test: started event without end gets status 'unfinished'."""
        self.write_event("focus_started", date="2026-09-21", task="Task A", intent_id="p:s1", source="pomodoro_app")

        result = self.run_query("2026-09-21", json_flag=True)
        sessions = self.load_json_output(result)

        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["status"], "unfinished")
        self.assertIsNone(sessions[0]["end"])

    # Test: abandoned session
    def test_abandoned_session(self):
        """Test: abandoned event is paired and shows real duration."""
        self.write_event("focus_abandoned", date="2026-09-21", task="Task A", duration_seconds=742, intent_id="p:s1", source="pomodoro_app")

        result = self.run_query("2026-09-21", json_flag=True)
        sessions = self.load_json_output(result)

        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["status"], "abandoned")
        self.assertEqual(sessions[0]["duration_seconds"], 742)

    # Test: empty day returns empty
    def test_empty_day(self):
        """Test: querying a date with no sessions returns empty list."""
        result = self.run_query("2026-09-21", json_flag=True)
        sessions = self.load_json_output(result)

        self.assertEqual(sessions, [])
        self.assertEqual(result.returncode, 0)

    # Test: missing file
    def test_missing_events_file(self):
        """Test: no events file -> 'no event file' and empty result."""
        # Delete the events file if it exists
        events_file = self.data_dir / "events.jsonl"
        if events_file.exists():
            events_file.unlink()

        result = self.run_query("2026-09-21", json_flag=True)
        sessions = self.load_json_output(result)

        self.assertEqual(sessions, [])

    # Test: legacy focus_tab events
    def test_legacy_focus_tab_source(self):
        """Test: focus_tab source events are still listed."""
        self.write_event("focus_started", date="2026-09-21", task="Legacy task", intent_id="2026-09-21:morning:1:legacy-task", source="focus_tab")
        self.write_event("focus_completed", date="2026-09-21", task="Legacy task", duration_seconds=1500, intent_id="2026-09-21:morning:1:legacy-task", source="focus_tab", ts="2026-09-21T10:25:00Z")

        result = self.run_query("2026-09-21", json_flag=True)
        sessions = self.load_json_output(result)

        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["source"], "focus_tab")

    # Test: today/yesterday resolution
    def test_today_yesterday_resolution(self):
        """Test: 'today' and 'yesterday' resolve to correct dates."""
        today = date.today().isoformat()
        yesterday = (date.today() - timedelta(days=1)).isoformat()

        # Write event for today
        self.write_event("focus_started", date=today, task="Today task", intent_id="t:s1", source="pomodoro_app")

        # Write event for yesterday
        self.write_event("focus_started", date=yesterday, task="Yesterday task", intent_id="y:s1", source="pomodoro_app")

        # Query today
        result = self.run_query("today", json_flag=True)
        today_sessions = self.load_json_output(result)
        self.assertEqual(len(today_sessions), 1)
        self.assertEqual(today_sessions[0]["task"], "Today task")

        # Query yesterday
        result = self.run_query("yesterday", json_flag=True)
        yesterday_sessions = self.load_json_output(result)
        self.assertEqual(len(yesterday_sessions), 1)
        self.assertEqual(yesterday_sessions[0]["task"], "Yesterday task")


if __name__ == "__main__":
    unittest.main()
