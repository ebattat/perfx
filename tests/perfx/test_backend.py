"""Unit tests for perfx/llm/backend.py — error paths and branching logic only."""
import pytest
from unittest.mock import patch, MagicMock


class TestGeminiBackend:
    def test_raises_without_api_key(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        from perfx.llm.backend import GeminiBackend
        with pytest.raises(EnvironmentError, match="GEMINI_API_KEY"):
            GeminiBackend()

    def test_init_with_mocked_sdk(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        mock_client = MagicMock()
        with patch("google.genai.Client", return_value=mock_client):
            from perfx.llm import backend
            import importlib; importlib.reload(backend)
            b = backend.GeminiBackend()
        assert b.client is mock_client


class TestClaudeBackend:
    def test_raises_without_api_key(self, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
        from perfx.llm.backend import ClaudeBackend
        with pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"):
            ClaudeBackend()

    def test_init_with_mocked_sdk(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
        mock_client = MagicMock()
        with patch("anthropic.Anthropic", return_value=mock_client):
            from perfx.llm import backend
            import importlib; importlib.reload(backend)
            b = backend.ClaudeBackend()
        assert b.client is mock_client


class TestClaudeBackendComplete:
    def test_complete_returns_text(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="Hello from Claude")]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_msg
        with patch("anthropic.Anthropic", return_value=mock_client):
            from perfx.llm import backend
            import importlib; importlib.reload(backend)
            b = backend.ClaudeBackend()
            result = b.complete("system prompt", "user message")
        assert result == "Hello from Claude"


class TestGeminiBackendComplete:
    def test_complete_returns_text(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        mock_response = MagicMock()
        mock_response.text = "Hello from Gemini"
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        with patch("google.genai.Client", return_value=mock_client):
            from perfx.llm import backend
            import importlib; importlib.reload(backend)
            b = backend.GeminiBackend()
            result = b.complete("system", "user")
        assert result == "Hello from Gemini"


class TestGetBackend:
    def test_gemini_model_returns_gemini_backend(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "fake")
        monkeypatch.setenv("PERFBOT_MODEL", "gemini")
        with patch("google.genai.Client"):
            from perfx.llm import backend
            import importlib; importlib.reload(backend)
            b = backend.get_backend("gemini")
        assert type(b).__name__ == "GeminiBackend"

    def test_claude_model_returns_claude_backend(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fake")
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
        with patch("anthropic.Anthropic"):
            from perfx.llm import backend
            import importlib; importlib.reload(backend)
            b = backend.get_backend("claude")
        assert type(b).__name__ == "ClaudeBackend"

    def test_default_is_gemini(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "fake")
        monkeypatch.delenv("PERFBOT_MODEL", raising=False)
        with patch("google.genai.Client"):
            from perfx.llm import backend
            import importlib; importlib.reload(backend)
            b = backend.get_backend()
        assert type(b).__name__ == "GeminiBackend"
