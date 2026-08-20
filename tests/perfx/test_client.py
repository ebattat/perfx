"""Unit tests for perfx/client.py — pure logic functions."""
import pytest
from unittest.mock import patch, MagicMock
from perfx.client import _parse_repos, _build_system_instruction, _thinking, _clear_thinking, _dispatch_tool, Agent


class TestParseRepos:
    def test_empty_env_returns_empty(self, monkeypatch):
        monkeypatch.delenv("GIT_REPOS", raising=False)
        assert _parse_repos() == []

    def test_single_url_parsed(self, monkeypatch):
        monkeypatch.setenv("GIT_REPOS", "https://github.com/redhat-performance/benchmark-runner")
        repos = _parse_repos()
        assert repos == ["redhat-performance/benchmark-runner"]

    def test_multiple_urls_parsed(self, monkeypatch):
        monkeypatch.setenv("GIT_REPOS", "https://github.com/org/repo1 https://github.com/org/repo2")
        repos = _parse_repos()
        assert "org/repo1" in repos
        assert "org/repo2" in repos

    def test_trailing_slash_stripped(self, monkeypatch):
        monkeypatch.setenv("GIT_REPOS", "https://github.com/org/repo/")
        assert "org/repo" in _parse_repos()

    def test_non_github_url_ignored(self, monkeypatch):
        monkeypatch.setenv("GIT_REPOS", "https://gitlab.com/org/repo")
        assert _parse_repos() == []


class TestBuildSystemInstruction:
    def test_contains_base_instructions(self, monkeypatch):
        monkeypatch.delenv("GIT_REPOS", raising=False)
        instr = _build_system_instruction()
        assert "GitHub" in instr
        assert "Jira" in instr

    def test_includes_repo_list_when_configured(self, monkeypatch):
        monkeypatch.setenv("GIT_REPOS", "https://github.com/org/repo")
        instr = _build_system_instruction()
        assert "org/repo" in instr

    def test_no_repo_restriction_when_unconfigured(self, monkeypatch):
        monkeypatch.delenv("GIT_REPOS", raising=False)
        instr = _build_system_instruction()
        assert "configured repos" not in instr


class TestThinkingHelpers:
    def test_thinking_prints(self, capsys):
        _thinking("Testing...")
        captured = capsys.readouterr()
        assert "Testing..." in captured.out

    def test_clear_thinking_prints(self, capsys):
        _clear_thinking()
        captured = capsys.readouterr()
        assert captured.out is not None


class TestAgentFactory:
    def test_returns_gemini_by_default(self, monkeypatch):
        monkeypatch.setenv("PERFBOT_MODEL", "gemini")
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        with patch("google.genai.Client"):
            agent = Agent()
        assert type(agent).__name__ == "GeminiAgent"

    def test_returns_claude_when_set(self, monkeypatch):
        monkeypatch.setenv("PERFBOT_MODEL", "claude")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
        with patch("anthropic.Anthropic"):
            agent = Agent()
        assert type(agent).__name__ == "ClaudeAgent"


class TestClaudeAgentInit:
    def test_raises_without_api_key(self, monkeypatch):
        monkeypatch.setenv("PERFBOT_MODEL", "claude")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
        from perfx.client import ClaudeAgent
        with pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"):
            ClaudeAgent()

    def test_initializes_with_mock_sdk(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)
        with patch("anthropic.Anthropic") as mock_cls:
            from perfx.client import ClaudeAgent
            agent = ClaudeAgent()
        assert agent.history == []
        assert agent.model == "claude-sonnet-4-5"


class TestDispatchTool:
    def test_dispatches_known_tool(self):
        from perfx.client import _dispatch_tool
        with patch("perfx.client.DISPATCH", {"mytool": lambda x: {"result": x}}):
            result = _dispatch_tool("mytool", {"x": "hello"})
        assert result == {"result": "hello"}

    def test_returns_error_on_exception(self):
        from perfx.client import _dispatch_tool
        with patch("perfx.client.DISPATCH", {"badtool": MagicMock(side_effect=RuntimeError("oops"))}):
            result = _dispatch_tool("badtool", {})
        assert "error" in result
        assert "oops" in result["error"]


class TestClaudeAgentChat:
    def test_chat_no_tool_calls(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)

        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = "Hello from Claude"

        mock_response = MagicMock()
        mock_response.content = [mock_block]

        mock_anthropic_client = MagicMock()
        mock_anthropic_client.messages.create.return_value = mock_response

        with patch("anthropic.Anthropic", return_value=mock_anthropic_client):
            from perfx.client import ClaudeAgent
            agent = ClaudeAgent()
            reply = agent.chat("Say hello")

        assert reply == "Hello from Claude"
        assert len(agent.history) == 2  # user + assistant

    def test_chat_appends_history(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)

        mock_block = MagicMock()
        mock_block.type = "text"
        mock_block.text = "Response"

        mock_response = MagicMock()
        mock_response.content = [mock_block]

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response

        with patch("anthropic.Anthropic", return_value=mock_client):
            from perfx.client import ClaudeAgent
            agent = ClaudeAgent()
            agent.chat("First")
            agent.chat("Second")

        assert len(agent.history) == 4  # 2 user + 2 assistant


class TestGeminiAgentChat:
    def test_chat_no_tool_calls(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

        mock_part = MagicMock()
        mock_part.function_call = None
        mock_part.text = "Hello from Gemini"

        mock_candidate = MagicMock()
        mock_candidate.parts = [mock_part]

        mock_response = MagicMock()
        mock_response.candidates = [MagicMock(content=mock_candidate)]
        mock_response.text = "Hello from Gemini"

        mock_genai_client = MagicMock()
        mock_genai_client.models.generate_content.return_value = mock_response

        with patch("google.genai.Client", return_value=mock_genai_client):
            from perfx.client import GeminiAgent
            agent = GeminiAgent()
            reply = agent.chat("Say hello")

        assert reply == "Hello from Gemini"
        assert len(agent.history) == 2  # user content + candidate content


class TestClaudeAgentVertex:
    def test_vertex_init_with_project(self, monkeypatch):
        monkeypatch.setenv("CLAUDE_CODE_USE_VERTEX", "1")
        monkeypatch.setenv("ANTHROPIC_VERTEX_PROJECT_ID", "my-project")
        monkeypatch.setenv("CLOUD_ML_REGION", "us-east5")
        with patch("anthropic.AnthropicVertex") as mock_vertex:
            from perfx.client import ClaudeAgent
            agent = ClaudeAgent()
        mock_vertex.assert_called_once_with(project_id="my-project", region="us-east5")
        assert agent.history == []


class TestGeminiAgentInit:
    def test_raises_without_api_key(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        from perfx.client import GeminiAgent
        with pytest.raises(EnvironmentError, match="GEMINI_API_KEY"):
            GeminiAgent()

    def test_initializes_with_mock_sdk(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")
        with patch("google.genai.Client"):
            from perfx.client import GeminiAgent
            agent = GeminiAgent()
        assert agent.history == []


class TestClaudeAgentVertexMissingProject:
    def test_raises_when_project_id_missing(self, monkeypatch):
        """EnvironmentError raised when CLAUDE_CODE_USE_VERTEX=1 but project ID absent."""
        monkeypatch.setenv("CLAUDE_CODE_USE_VERTEX", "1")
        monkeypatch.delenv("ANTHROPIC_VERTEX_PROJECT_ID", raising=False)
        from perfx.client import ClaudeAgent
        with pytest.raises(EnvironmentError, match="ANTHROPIC_VERTEX_PROJECT_ID"):
            ClaudeAgent()


class TestGeminiAgentChatWithToolCalls:
    def test_tool_call_loop(self, monkeypatch):
        """GeminiAgent should dispatch tool calls and continue until no more tool calls."""
        monkeypatch.setenv("GEMINI_API_KEY", "fake-key")

        from unittest.mock import MagicMock
        from google.genai import types

        # First response: has a function_call part
        fn_call_part = MagicMock()
        fn_call_part.function_call = MagicMock()
        fn_call_part.function_call.name = "mytool"
        fn_call_part.function_call.args = {"key": "val"}

        first_candidate_content = MagicMock()
        first_candidate_content.parts = [fn_call_part]

        first_response = MagicMock()
        first_response.candidates = [MagicMock(content=first_candidate_content)]
        first_response.text = None

        # Second response: no function_call parts → final text
        text_part = MagicMock()
        text_part.function_call = None
        text_part.text = "Tool done"

        second_candidate_content = MagicMock()
        second_candidate_content.parts = [text_part]

        second_response = MagicMock()
        second_response.candidates = [MagicMock(content=second_candidate_content)]
        second_response.text = "Tool done"

        mock_genai_client = MagicMock()
        mock_genai_client.models.generate_content.side_effect = [first_response, second_response]

        with patch("google.genai.Client", return_value=mock_genai_client):
            with patch("perfx.client.DISPATCH", {"mytool": lambda key: {"answer": key}}):
                from perfx.client import GeminiAgent
                agent = GeminiAgent()
                reply = agent.chat("Call the tool")

        assert reply == "Tool done"
        # history: user content, first candidate, tool results content, second candidate
        assert len(agent.history) == 4


class TestClaudeAgentChatWithToolCalls:
    def test_tool_call_loop(self, monkeypatch):
        """ClaudeAgent should dispatch tool_use blocks and loop until stop_turn."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-key")
        monkeypatch.delenv("CLAUDE_CODE_USE_VERTEX", raising=False)

        # First response: contains a tool_use block
        tool_use_block = MagicMock()
        tool_use_block.type = "tool_use"
        tool_use_block.name = "mytool"
        tool_use_block.input = {"key": "val"}
        tool_use_block.id = "tu_123"

        first_response = MagicMock()
        first_response.content = [tool_use_block]

        # Second response: text only, no tool_use
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Done!"

        second_response = MagicMock()
        second_response.content = [text_block]

        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [first_response, second_response]

        with patch("anthropic.Anthropic", return_value=mock_client):
            with patch("perfx.client.DISPATCH", {"mytool": lambda key: {"result": key}}):
                from perfx.client import ClaudeAgent
                agent = ClaudeAgent()
                reply = agent.chat("Use the tool")

        assert reply == "Done!"
        # history: user, assistant(tool_use), user(tool_result), assistant(text)
        assert len(agent.history) == 4
