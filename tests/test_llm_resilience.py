"""Tests for LLM retry + fallback behavior."""
from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ.setdefault("NOTION_TOKEN", "test-notion-token")

from life_agent.agent import llm


class LLMResilienceTests(unittest.TestCase):
    def test_normal_gemini_success(self) -> None:
        with mock.patch.object(llm, "PROVIDER", "gemini"), \
             mock.patch.object(llm, "_generate_with_provider", return_value="ok"):
            self.assertEqual(llm.generate("prompt"), "ok")

    def test_gemini_transient_failure_retries_then_succeeds(self) -> None:
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] < 2:
                raise RuntimeError("429 too many requests")
            return "ok"

        with mock.patch.object(llm, "MAX_RETRIES", 3), \
             mock.patch.object(llm.time, "sleep") as sleep_mock:
            self.assertEqual(llm._retry(flaky), "ok")
            self.assertEqual(calls["n"], 2)
            sleep_mock.assert_called_once_with(5)

    def test_gemini_quota_exhaustion_no_retry(self) -> None:
        calls = {"n": 0}

        def quota_fail():
            calls["n"] += 1
            raise RuntimeError(
                "429 RESOURCE_EXHAUSTED. Quota exceeded for metric: "
                "generativelanguage.googleapis.com/generate_content_free_tier_requests"
            )

        with mock.patch.object(llm, "MAX_RETRIES", 3), \
             mock.patch.object(llm.time, "sleep") as sleep_mock:
            with self.assertRaises(llm.LLMQuotaExceededError):
                llm._retry(quota_fail)
            self.assertEqual(calls["n"], 1)
            sleep_mock.assert_not_called()

    def test_fallback_provider_selection(self) -> None:
        provider_mock = mock.Mock(side_effect=[llm.LLMQuotaExceededError("quota"), "fallback ok"])
        with mock.patch.object(llm, "PROVIDER", "gemini"), \
             mock.patch.object(llm, "_generate_with_provider", provider_mock), \
             mock.patch.object(llm, "_configured_fallback_provider", return_value="claude"):
            self.assertEqual(llm.generate("prompt"), "fallback ok")
            self.assertEqual(provider_mock.call_args_list[0].args, ("gemini", "prompt", False, 0.7, True))
            self.assertEqual(provider_mock.call_args_list[1].args, ("claude", "prompt", False, 0.7, True))

    def test_fallback_failure_propagates(self) -> None:
        with mock.patch.object(llm, "PROVIDER", "gemini"), \
             mock.patch.object(llm, "_generate_with_provider", side_effect=[llm.LLMQuotaExceededError("quota"), RuntimeError("fallback failed")]), \
             mock.patch.object(llm, "_configured_fallback_provider", return_value="claude"):
            with self.assertRaisesRegex(RuntimeError, "fallback failed"):
                llm.generate("prompt")

    def test_quota_exhaustion_without_fallback_fails_gracefully(self) -> None:
        with mock.patch.object(llm, "PROVIDER", "gemini"), \
             mock.patch.object(llm, "_generate_with_provider", side_effect=llm.LLMQuotaExceededError("quota")), \
             mock.patch.object(llm, "_configured_fallback_provider", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "No fallback provider is configured"):
                llm.generate("prompt")

    def test_bounded_retry_behavior(self) -> None:
        calls = {"n": 0}

        def always_fail():
            calls["n"] += 1
            raise RuntimeError("503 overloaded")

        with mock.patch.object(llm, "MAX_RETRIES", 3), \
             mock.patch.object(llm.time, "sleep") as sleep_mock:
            with self.assertRaisesRegex(RuntimeError, "503 overloaded"):
                llm._retry(always_fail)
            self.assertEqual(calls["n"], 3)
            self.assertEqual([c.args[0] for c in sleep_mock.call_args_list], [5, 10])


if __name__ == "__main__":
    unittest.main()
