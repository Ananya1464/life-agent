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


def test_metrics_refresh_only_after_day_end_tasks_and_never_fails_the_task(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    calls = []
    monkeypatch.setattr(main.metrics, "update_metrics", lambda: calls.append("metrics"))
    monkeypatch.setattr(main.outbound, "send_task_start_notification", lambda t: "tok")
    for task in ("ai_edge", "evening_checkin"):
        fake = types.ModuleType(f"life_agent.agent.tasks.{task}")
        fake.run = lambda: None
        monkeypatch.setitem(sys.modules, f"life_agent.agent.tasks.{task}", fake)
    main.run("ai_edge")
    assert calls == []                                    # the morning briefing does not spend a minute on dashboard figures
    main.run("evening_checkin")
    assert calls == ["metrics"]
    monkeypatch.setattr(main.metrics, "update_metrics", lambda: (_ for _ in ()).throw(RuntimeError("notion 404")))
    main.run("evening_checkin")                           # a failing refresh is logged, not raised
