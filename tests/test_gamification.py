"""Tests for the diamond/level/streak rules."""
from datetime import date

import pytest

from life_agent import gamification as g

TODAY = date(2026, 10, 1)


def run(day, minutes, kind="focus_completed", intent=None, hour=10):
    intent = intent or f"{day}-{minutes}-{kind}-{hour}"
    return [
        {"id": f"s-{intent}", "ts": f"{day}T{hour:02d}:00:00Z", "kind": "focus_started", "date": day,
         "task": "T", "intent_id": intent, "source": "lifebot"},
        {"id": f"e-{intent}", "ts": f"{day}T{hour:02d}:30:00Z", "kind": kind, "date": day, "task": "T",
         "intent_id": intent, "source": "lifebot", "duration_seconds": minutes * 60},
    ]


def task_done(day, task="Write", intent=None):
    return {"id": f"t-{day}-{task}", "ts": f"{day}T12:00:00Z", "kind": "task_completed", "date": day,
            "task": task, "intent_id": intent or f"{day}:{task}"}


@pytest.mark.parametrize("minutes, status, expected", [
    (25, "completed", 5), (50, "completed", 10), (1, "completed", 1),   # at least one diamond
    (9, "abandoned", 0), (10, "abandoned", 1), (24, "abandoned", 2),      # effort counts after 10 min
    (30, "unfinished", 0),
])
def test_session_diamonds(minutes, status, expected):
    assert g.session_diamonds({"status": status, "duration_seconds": minutes * 60}) == expected


def test_levels_follow_the_published_thresholds():
    assert [g.level_for(n) for n in (0, 19, 20, 79, 80, 179, 180, 320)] == [1, 1, 2, 2, 3, 3, 4, 5]
    assert g.title_for(1) == "Rookie Explorer" and g.title_for(500) == g.TITLES[-1]


def test_empty_history():
    s = g.compute([], TODAY)
    assert (s["total"], s["level"], s["streak"], s["xp_pct"]) == (0, 1, 0, 0)
    assert s["xp_needed"] == 20


def test_totals_chests_and_today():
    events = run("2026-10-01", 25) + [task_done("2026-10-01")] + run("2026-09-30", 25, intent="y")
    s = g.compute(events, TODAY)
    assert s["total"] == 5 + 3 + 5
    assert s["today"] == 8 and s["sessions_today"] == 1 and s["chests_today"] == 1


def test_duplicate_task_completions_count_once():
    events = [task_done("2026-10-01"), task_done("2026-10-01")]
    assert g.compute(events, TODAY)["total"] == 3


def test_abandon_then_complete_same_intent_earns_for_both():
    events = run("2026-10-01", 12, kind="focus_abandoned", intent="same", hour=9) + [
        {"id": "e2", "ts": "2026-10-01T11:00:00Z", "kind": "focus_completed", "date": "2026-10-01", "task": "T",
         "intent_id": "same", "source": "lifebot", "duration_seconds": 1500}]
    assert g.compute(events, TODAY)["total"] == 1 + 5


def test_streak_counts_back_and_survives_an_empty_today():
    days = ["2026-09-28", "2026-09-29", "2026-09-30"]
    events = [e for d in days for e in run(d, 25, intent=d)]
    assert g.compute(events, TODAY)["streak"] == 3                  # today not started yet: not broken
    assert g.compute(events + run("2026-10-01", 25, intent="t"), TODAY)["streak"] == 4
    gap = run("2026-09-27", 25, intent="a") + run("2026-09-30", 25, intent="b")
    assert g.compute(gap, TODAY)["streak"] == 1


def test_abandoned_only_day_does_not_extend_streak():
    events = run("2026-09-30", 20, kind="focus_abandoned", intent="x")
    s = g.compute(events, TODAY)
    assert s["streak"] == 0 and s["total"] == 2


def test_level_progress_and_reward_delta():
    before = g.compute(run("2026-09-30", 25, intent="a") * 1 + [task_done("2026-09-30")] * 1, TODAY)
    events = [e for i in range(4) for e in run("2026-09-29", 25, intent=f"b{i}", hour=8 + i)]
    big = g.compute(events, TODAY)                                   # 4 x 5 = 20 diamonds -> level 2
    assert big["total"] == 20 and big["level"] == 2 and big["xp"] == 0
    r = g.reward(g.compute(events[:-2], TODAY), big)
    assert r["diamonds"] == 5 and r["level_up"] is True
    assert "per_day" not in r["stats"] and r["stats"]["level"] == 2
    assert g.reward(big, big) == {"diamonds": 0, "level_up": False, "stats": r["stats"]}
    assert before["level"] == 1
