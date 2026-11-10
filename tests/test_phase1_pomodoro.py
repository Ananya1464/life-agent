import sys
import os
from pathlib import Path
from datetime import date
import pytest

# Add repository root to PYTHONPATH
sys.path.insert(0, str(Path(os.getcwd()) / "src"))

from life_agent.events import event_model, queries

def test_pomodoro_session_recovery(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # the ledger path is relative: never write to the real data/events.jsonl
    """
    One real session becomes one deterministically recoverable event.
    """
    today = date.today().isoformat()
    task = "Test Pomodoro Session"
    duration_seconds = 1500
    
    # 1. Record events
    # Simulate a focus session
    # Using existing functions from event_model (imported directly)
    # Note: Need to verify if store.append is wrapped in record_focus_started/etc
    
    # Actually, based on previous reconnaissance, event_model has these functions
    # and they use store.append internally.
    
    # Reset/ensure data file doesn't interfere? (Phase 0 check)
    # The tests should ideally work on a clean slate if possible, 
    # but the implementation depends on data/events.jsonl.
    
    event_model.record_focus_started(
        date_iso=today,
        task=task,
        intent_id="test-e2e-id",
        source="pomodoro_app"
    )
    event_model.record_focus_completed(
        date_iso=today,
        task=task,
        duration_seconds=duration_seconds,
        intent_id="test-e2e-id",
        source="pomodoro_app"
    )
    
    # 2. Query it back
    sessions = queries.get_focus_sessions(today)
    
    # 3. Assertions
    assert len(sessions) >= 1
    completed = [s for s in sessions if s["status"] == "completed"]
    assert len(completed) >= 1
    assert completed[0]["task"] == task
    assert completed[0]["duration_seconds"] == duration_seconds

if __name__ == "__main__":
    # If running directly, execute the test function
    try:
        test_pomodoro_session_recovery()
        print("Phase 1 acceptance test passed")
    except Exception as e:
        print(f"Phase 1 acceptance test failed: {e}")
        sys.exit(1)
