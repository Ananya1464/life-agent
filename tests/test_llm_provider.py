"""Tests for LLM provider fallback behavior."""
import unittest
from unittest.mock import patch, MagicMock
from life_agent.agent import llm


class LLMQuotaExceededError(Exception):
    """Raised when LLM quota is exceeded."""
    pass


class TestLLMProvider(unittest.TestCase):
    """Tests for LLM provider fallback chain."""

    def test_gemini_success(self):
        """Test successful Gemini generation."""
        with patch("life_agent.agent.llm._generate_gemini", return_value="Hello") as mock:
            with patch("life_agent.agent.llm.PROVIDER", "gemini"):
                with patch("life_agent.agent.llm.config.GEMINI_API_KEY", "test-key"):
                    result = llm.generate("Test prompt")
                    self.assertEqual(result, "Hello")
                    mock.assert_called_once()

    def test_gemini_quota_fallback_to_nvidia(self):
        """Test Gemini quota failure falls back to NVIDIA."""
        with patch("life_agent.agent.llm._generate_gemini", side_effect=Exception("429 RESOURCE_EXHAUSTED")):
            with patch("life_agent.agent.llm._generate_nvidia", return_value="Fallback response") as mock_nvidia:
                with patch("life_agent.agent.llm.PROVIDER", "gemini"):
                    with patch("life_agent.agent.llm.FALLBACK_PROVIDER", "nvidia"):
                        with patch("life_agent.agent.llm.config.GEMINI_API_KEY", "test-key"):
                            with patch("life_agent.agent.llm.config.NVIDIA_API_KEY", "test-nvidia-key"):
                                result = llm.generate("Test prompt")
                                self.assertEqual(result, "Fallback response")
                                mock_nvidia.assert_called_once()

    def test_quota_exhaustion_is_not_retried(self):
        """Test Gemini quota exhaustion raises immediately for provider fallback."""
        call = MagicMock(
            side_effect=Exception(
                "429 RESOURCE_EXHAUSTED: free-tier daily request quota exhausted"
            )
        )
        with patch("life_agent.agent.llm.MAX_RETRIES", 3):
            with patch("life_agent.agent.llm.time.sleep") as mock_sleep:
                with self.assertRaises(Exception) as cm:
                    llm._retry(call)
                self.assertIn("RESOURCE_EXHAUSTED", str(cm.exception))
                call.assert_called_once()
                mock_sleep.assert_not_called()

    def test_nvidia_success(self):
        """Test successful NVIDIA generation as primary provider."""
        with patch("life_agent.agent.llm._generate_nvidia", return_value="NVIDIA response") as mock:
            with patch("life_agent.agent.llm.PROVIDER", "nvidia"):
                with patch("life_agent.agent.llm.config.NVIDIA_API_KEY", "test-nvidia-key"):
                    result = llm.generate("Test prompt")
                    self.assertEqual(result, "NVIDIA response")
                    mock.assert_called_once()

    def test_nvidia_failure_raises_error(self):
        """Test NVIDIA failure raises clear error (no silent fallback)."""
        with patch("life_agent.agent.llm._generate_nvidia", side_effect=Exception("NVIDIA API error")):
            with patch("life_agent.agent.llm.PROVIDER", "nvidia"):
                with patch("life_agent.agent.llm.config.NVIDIA_API_KEY", "test-nvidia-key"):
                    with self.assertRaises(Exception) as cm:
                        llm.generate("Test prompt")
                    self.assertIn("NVIDIA API error", str(cm.exception))

    def test_no_claude_fallback(self):
        """Verify Claude is never used as fallback."""
        # Ensure no claude-related code paths exist in generate()
        import inspect
        source = inspect.getsource(llm.generate)
        self.assertNotIn("claude", source.lower())
        self.assertNotIn("anthropic", source.lower())

    def test_direct_nvidia_provider_bypasses_configured_gemini(self):
        """Test explicit provider='nvidia' routes directly to NVIDIA."""
        with patch("life_agent.agent.llm._generate_gemini") as mock_gemini:
            with patch("life_agent.agent.llm._generate_nvidia", return_value="Direct NVIDIA") as mock_nvidia:
                with patch("life_agent.agent.llm.PROVIDER", "gemini"):
                    with patch("life_agent.agent.llm.config.NVIDIA_API_KEY", "test-key"):
                        result = llm.generate("Test prompt", provider="nvidia")
                        self.assertEqual(result, "Direct NVIDIA")
                        mock_nvidia.assert_called_once()
                        mock_gemini.assert_not_called()

    def test_direct_gemini_provider_bypasses_configured_nvidia(self):
        """Test explicit provider='gemini' routes directly to Gemini."""
        with patch("life_agent.agent.llm._generate_gemini", return_value="Direct Gemini") as mock_gemini:
            with patch("life_agent.agent.llm._generate_nvidia") as mock_nvidia:
                with patch("life_agent.agent.llm.PROVIDER", "nvidia"):
                    with patch("life_agent.agent.llm.config.NVIDIA_API_KEY", "test-key"):
                        result = llm.generate("Test prompt", provider="gemini")
                        self.assertEqual(result, "Direct Gemini")
                        mock_gemini.assert_called_once()
                        mock_nvidia.assert_not_called()

    def test_direct_gemini_provider_does_not_fallback_to_nvidia(self):
        """Test explicit provider='gemini' does not silently switch providers."""
        with patch("life_agent.agent.llm._generate_gemini", side_effect=Exception("Gemini error")):
            with patch("life_agent.agent.llm._generate_nvidia") as mock_nvidia:
                with patch("life_agent.agent.llm.PROVIDER", "nvidia"):
                    with patch("life_agent.agent.llm.FALLBACK_PROVIDER", "nvidia"):
                        with patch("life_agent.agent.llm.config.NVIDIA_API_KEY", "test-key"):
                            with self.assertRaises(Exception) as cm:
                                llm.generate("Test prompt", provider="gemini")
                            self.assertIn("Gemini error", str(cm.exception))
                            mock_nvidia.assert_not_called()

    def test_gemini_no_fallback_when_nvidia_key_missing(self):
        """Test Gemini failure raises error when NVIDIA key not configured."""
        with patch("life_agent.agent.llm._generate_gemini", side_effect=Exception("429 RESOURCE_EXHAUSTED")):
            with patch("life_agent.agent.llm.PROVIDER", "gemini"):
                with patch("life_agent.agent.llm.config.GEMINI_API_KEY", "test-key"):
                    with patch("life_agent.agent.llm.config.NVIDIA_API_KEY", ""):
                        with self.assertRaises(Exception) as cm:
                            llm.generate("Test prompt")
                        self.assertIn("RESOURCE_EXHAUSTED", str(cm.exception))

    def test_nvidia_no_key_raises_error(self):
        """Test NVIDIA provider raises clear error when key missing."""
        with patch("life_agent.agent.llm.PROVIDER", "nvidia"):
            with patch("life_agent.agent.llm.config.NVIDIA_API_KEY", ""):
                with self.assertRaises(RuntimeError) as cm:
                    llm.generate("Test prompt")
                self.assertIn("NVIDIA_API_KEY not configured", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
