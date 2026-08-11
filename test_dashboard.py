import json
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
import pathlib
import tempfile

import metrics
import store


class TestDashboard(unittest.TestCase):
    def test_empty_state(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = pathlib.Path(tmp_dir)
            with patch("store.load_all", return_value=[]), patch(
                "calendar_feed.events_on", return_value=[]
            ), patch("notion_api._req", return_value={}):
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
        with patch("store.load_all", return_value=mock_events), patch(
            "calendar_feed.events_on", return_value=[]
        ), patch("notion_api._req", return_value={}):
            data = metrics.generate_dashboard_data()

            self.assertEqual(data["today"]["tasks_planned"], 1)
            self.assertEqual(data["today"]["tasks_done"], 1)
            self.assertEqual(data["today"]["completion_pct"], 100)
            self.assertEqual(data["state"]["today_message"], "100% completion")
            self.assertTrue(data["state"]["history_available"])

if __name__ == "__main__":
    unittest.main()
