"""A failed task-start notice (no ntfy topic, email off) must not stop the scheduled task from running."""
import sys
import types

from life_agent.agent import main


def test_task_runs_even_when_start_notice_cannot_be_sent(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)                      # events ledger is a relative path: never touch the real one
    ran = []
    fake = types.ModuleType("life_agent.agent.tasks.meal_plan")
    fake.run = lambda: ran.append("meal_plan")
    monkeypatch.setitem(sys.modules, "life_agent.agent.tasks.meal_plan", fake)

    def no_channel(task):
        raise RuntimeError("notification delivery failed for slot task_start: NTFY_TOPIC not configured")

    monkeypatch.setattr(main.outbound, "send_task_start_notification", no_channel)
    monkeypatch.setattr(main.metrics, "update_metrics", lambda: None)
    main.run("meal_plan")
    assert ran == ["meal_plan"]
