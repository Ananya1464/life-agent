import pytest
from life_agent.tools import deterministic_tools

def test_safe_path_validation():
    assert deterministic_tools._is_safe_path("02_EXECUTION/Daily/2026-09-21.md") == True
    assert deterministic_tools._is_safe_path("../secret.txt") == False
    assert deterministic_tools._is_safe_path("/etc/passwd") == False

def test_get_today_sessions():
    sessions = deterministic_tools.get_today_sessions()
    assert isinstance(sessions, list)

def test_calculate_metrics():
    # Test today's metrics
    metrics = deterministic_tools.calculate_metrics("total_focus_time", "2026-09-22")
    assert "total_focus_seconds" in metrics
