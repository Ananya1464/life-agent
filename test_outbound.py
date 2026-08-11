import unittest
from unittest.mock import patch, MagicMock
import outbound
import store
import dates

class TestOutbound(unittest.TestCase):
    @patch("emailer.send_email")
    @patch("store.append")
    def test_send_prompt_email_success(self, mock_append, mock_send_email):
        # Setup mock
        mock_send_email.return_value = "<mock-msg-id@localhost>"
        
        # Run
        token = outbound.send_prompt_email("morning", "Test Subject", "Test Body")
        
        # Verify Token
        today_str = dates.today().strftime('%Y%m%d')
        expected_token = f"LA-{today_str}-M"
        self.assertEqual(token, expected_token)
        
        # Verify Email was sent with correct format
        mock_send_email.assert_called_once()
        args, _ = mock_send_email.call_args
        subject, body = args
        self.assertEqual(subject, f"[{expected_token}] Test Subject")
        self.assertIn("Test Body", body)
        self.assertIn("Just reply to this email in your own words. No format needed.", body)
        
        # Verify event was recorded correctly
        mock_append.assert_called_once()
        args, _ = mock_append.call_args
        kind, payload = args
        self.assertEqual(kind, "email_sent")
        self.assertEqual(payload["slot"], "morning")
        self.assertEqual(payload["token"], expected_token)
        self.assertEqual(payload["subject"], subject)
        self.assertEqual(payload["message_id"], "<mock-msg-id@localhost>")

    @patch("emailer.send_email")
    @patch("store.append")
    def test_send_prompt_email_failure_propagates(self, mock_append, mock_send_email):
        # Setup mock to fail
        mock_send_email.side_effect = RuntimeError("SMTP failed")
        
        # Run and expect exception
        with self.assertRaises(RuntimeError):
            outbound.send_prompt_email("morning", "Test Subject", "Test Body")
            
        # Verify event was NOT recorded
        mock_append.assert_not_called()

if __name__ == "__main__":
    unittest.main()
