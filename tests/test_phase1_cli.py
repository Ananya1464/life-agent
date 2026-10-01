"""Tests for record_focus_cli.py - Phase 1 CLI writer."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from hashlib import sha256
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestRecordFocusCLI(unittest.TestCase):
    """Test the CLI tool for recording focus events."""

    @classmethod
    def setUpClass(cls):
        """Record hash of real data/events.jsonl if it exists."""
        cls.real_events_path = REPO_ROOT / "data" / "events.jsonl"
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
        """Create temp directory and change to it."""
        self.temp_dir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.temp_dir)

    def tearDown(self):
        """Restore working directory."""
        os.chdir(self.old_cwd)

    def run_cli(self, phase, date_iso, task, duration_seconds=None, session_id="s1"):
        """Helper: run CLI with JSON input."""
        payload = {
            "phase": phase,
            "date_iso": date_iso,
            "task": task,
            "session_id": session_id
        }
        if duration_seconds is not None:
            payload["duration_seconds"] = duration_seconds

        json_str = json.dumps(payload)
        result = subprocess.run(
            [sys.executable, "-m", "life_agent.events.record_focus_cli"],
            input=json_str.encode("utf-8"),
            capture_output=True,
            cwd=self.temp_dir,
            env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
        )
        return result

    def load_events(self):
        """Load events from temp dir."""
        events_file = Path(self.temp_dir) / "data" / "events.jsonl"
        if not events_file.exists():
            return []
        events = []
        with open(events_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        return events

    # T1: started+completed persist with correct fields
    def test_t1_started_completed_persist(self):
        """T1: started and completed events persist."""
        result1 = self.run_cli("started", "2026-09-21", "Test task", session_id="s1")
        self.assertEqual(result1.returncode, 0, f"started failed: {result1.stderr.decode()}")

        result2 = self.run_cli("completed", "2026-09-21", "Test task", 1500, "s1")
        self.assertEqual(result2.returncode, 0, f"completed failed: {result2.stderr.decode()}")

        events = self.load_events()
        self.assertGreaterEqual(len(events), 2)

        started = [e for e in events if e.get("kind") == "focus_started"]
        completed = [e for e in events if e.get("kind") == "focus_completed"]

        self.assertEqual(len(started), 1)
        self.assertEqual(len(completed), 1)
        self.assertEqual(started[0]["task"], "Test task")
        self.assertEqual(completed[0]["duration_seconds"], 1500)
        self.assertEqual(started[0]["source"], "pomodoro_app")

    # T2: TWO sessions, same task/date/duration, different session_id -> both persist
    def test_t2_two_sessions_both_persist(self):
        """T2: Two sessions with different session_ids both persist."""
        # Session 1
        self.run_cli("started", "2026-09-21", "Task A", session_id="s1")
        self.run_cli("completed", "2026-09-21", "Task A", 1500, "s1")

        # Session 2 (same task/date/duration, different session_id)
        self.run_cli("started", "2026-09-21", "Task A", session_id="s2")
        self.run_cli("completed", "2026-09-21", "Task A", 1500, "s2")

        events = self.load_events()
        completed_events = [e for e in events if e.get("kind") == "focus_completed"]

        self.assertEqual(len(completed_events), 2)
        intent_ids = {e["intent_id"] for e in completed_events}
        self.assertEqual(intent_ids, {"pomodoro:s1", "pomodoro:s2"})

    # T3: abandoned session records real duration
    def test_t3_abandoned_real_duration(self):
        """T3: Abandoned session records actual elapsed seconds."""
        result = self.run_cli("abandoned", "2026-09-21", "Test task", 742, "s1")
        self.assertEqual(result.returncode, 0)

        events = self.load_events()
        abandoned = [e for e in events if e.get("kind") == "focus_abandoned"]
        self.assertEqual(len(abandoned), 1)
        self.assertEqual(abandoned[0]["duration_seconds"], 742)

    # T4: ts ends with "Z" and date equals payload date
    def test_t4_timestamp_and_date(self):
        """T4: Timestamps have Z suffix; date field matches input."""
        self.run_cli("started", "2026-09-21", "Test", session_id="s1")

        events = self.load_events()
        self.assertEqual(len(events), 1)

        event = events[0]
        self.assertTrue(event["ts"].endswith("Z"), f"ts doesn't end with Z: {event['ts']}")
        self.assertEqual(event["date"], "2026-09-21")

    # T5: empty task -> "(no task)"
    def test_t5_empty_task_default(self):
        """T5: Empty task becomes '(no task)'."""
        self.run_cli("started", "2026-09-21", "", session_id="s1")

        events = self.load_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["task"], "(no task)")

    # T6: same session_id+phase twice -> exactly one event
    def test_t6_idempotency(self):
        """T6: Same session_id+phase twice creates only one event (deduplication)."""
        self.run_cli("started", "2026-09-21", "Task", session_id="s1")
        self.run_cli("started", "2026-09-21", "Task", session_id="s1")

        events = self.load_events()
        started_events = [e for e in events if e.get("kind") == "focus_started"]
        self.assertEqual(len(started_events), 1)

    # T7: non-ASCII task round-trips intact
    def test_t7_non_ascii_task(self):
        """T7: Non-ASCII task text (café ☕) round-trips."""
        task = "café ☕"
        self.run_cli("started", "2026-09-21", task, session_id="s1")

        events = self.load_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["task"], task)

    # T8: invalid date/phase/duration -> exit 1, stderr does not contain task text
    def test_t8_invalid_inputs_no_task_in_error(self):
        """T8: Invalid inputs exit 1; task text never in stderr."""
        test_task = "secret task 🔒"

        # Invalid date
        result = self.run_cli("started", "not-a-date", test_task, session_id="s1")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(test_task, result.stderr.decode())

        # Invalid phase
        result = self.run_cli("invalid_phase", "2026-09-21", test_task, session_id="s1")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(test_task, result.stderr.decode())

        # Negative duration
        result = self.run_cli("completed", "2026-09-21", test_task, -100, "s1")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn(test_task, result.stderr.decode())


if __name__ == "__main__":
    unittest.main()
