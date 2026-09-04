import json
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
import pathlib
import tempfile

from life_agent.metrics import metrics
from life_agent.events import store


class TestDashboard(unittest.TestCase):
    def test_empty_state(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = pathlib.Path(tmp_dir)
            with patch("life_agent.events.store.load_all", return_value=[]), patch(
            "life_agent.integrations.calendar_feed.events_on", return_value=[]
        ), patch("life_agent.integrations.notion_api._req", return_value={}):
                data = metrics.generate_dashboard_data()

                self.assertEqual(data["state"]["today_message"], "Not enough data yet")
                self.assertFalse(data["state"]["history_available"])
                self.assertEqual(data["attention"]["items"], ["Not enough data yet."])
                self.assertEqual(data["weekly_win"]["text"], "Not enough data yet.")
                
                # Verify JSON serialization works (simulates write_dashboard_data)
                metrics.write_dashboard_data(output_dir=tmp_path)
                self.assertTrue((tmp_path / "metrics.json").exists())
                self.assertTrue((tmp_path / "goals.json").exists())

    def test_dashboard_with_data(self):
        # Setup some mock events
        mock_events = [
            {"kind": "task_planned", "intent_id": "1", "ts": datetime.now(timezone.utc).isoformat()},
            {"kind": "task_completed", "intent_id": "1", "ts": datetime.now(timezone.utc).isoformat()},
        ]
        with patch("life_agent.events.store.load_all", return_value=mock_events), patch(
            "life_agent.integrations.calendar_feed.events_on", return_value=[]
        ), patch("life_agent.integrations.notion_api._req", return_value={}):
            data = metrics.generate_dashboard_data()

            self.assertEqual(data["today"]["tasks_planned"], 1)
            self.assertEqual(data["today"]["tasks_done"], 1)
            self.assertEqual(data["today"]["completion_pct"], 100)
            self.assertEqual(data["state"]["today_message"], "100% completion")
            self.assertTrue(data["state"]["history_available"])

    def test_update_metrics_skips_placeholder_notion_ids(self):
        with patch("life_agent.events.store.load_all", return_value=[]), patch(
            "life_agent.integrations.calendar_feed.events_on", return_value=[]
        ), patch("life_agent.integrations.notion_api._req") as mock_req, patch(
            "life_agent.metrics.metrics.config.LIFE_OS_METRICS_DB_ID",
            "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        ), patch(
            "life_agent.metrics.metrics.config.LIFE_OS_DASHBOARD_PAGE_ID",
            "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        ), patch(
            "life_agent.metrics.metrics.config.LIFE_AREAS_GOALS_DB_ID",
            "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
        ):
            data = metrics.update_metrics()

            self.assertIn("daily", data)
            self.assertIn("weekly", data)
            self.assertIn("dashboard", data)
            mock_req.assert_not_called()

if __name__ == "__main__":
    unittest.main()
