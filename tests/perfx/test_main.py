"""Unit tests for perfx/main.py — CLI entrypoint."""
import os
import sys
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_main(argv, inputs, monkeypatch, mock_agent=None, agent_side_effect=None):
    """Run main() with patched argv and input() sequence.

    Returns the SystemExit exception raised when the loop terminates.
    ``inputs`` is a list of strings returned by successive input() calls.
    Raises after exhausting inputs if the loop hasn't exited yet.
    """
    input_iter = iter(inputs)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(input_iter))

    if mock_agent is None:
        mock_agent = MagicMock()
    if agent_side_effect is not None:
        mock_agent.chat.side_effect = agent_side_effect

    with patch("sys.argv", argv):
        with patch("perfx.main.Agent", return_value=mock_agent):
            with pytest.raises(SystemExit) as exc_info:
                # Re-import to pick up fresh module state each time
                import perfx.main as main_module
                main_module.main()
    return exc_info.value


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMainHelp:
    def test_help_exits_zero(self):
        """--help should print usage and exit 0."""
        with patch("sys.argv", ["perfx", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                import perfx.main as main_module
                main_module.main()
        assert exc_info.value.code == 0


class TestMainModelFlag:
    def test_model_flag_sets_env_var(self, monkeypatch):
        """--model gemini should set PERFBOT_MODEL in the environment."""
        monkeypatch.delenv("GIT_REPOS", raising=False)

        exc = _run_main(
            argv=["perfx", "--model", "gemini"],
            inputs=["exit"],
            monkeypatch=monkeypatch,
        )
        assert exc.code == 0
        assert os.environ.get("PERFBOT_MODEL") == "gemini"

    def test_model_flag_claude(self, monkeypatch):
        """--model claude should set PERFBOT_MODEL=claude."""
        monkeypatch.delenv("GIT_REPOS", raising=False)

        _run_main(
            argv=["perfx", "--model", "claude"],
            inputs=["exit"],
            monkeypatch=monkeypatch,
        )
        assert os.environ.get("PERFBOT_MODEL") == "claude"

    def test_no_model_flag_uses_default(self, monkeypatch):
        """Omitting --model should not set PERFBOT_MODEL (uses default inside main)."""
        monkeypatch.delenv("GIT_REPOS", raising=False)
        monkeypatch.delenv("PERFBOT_MODEL", raising=False)

        _run_main(
            argv=["perfx"],
            inputs=["exit"],
            monkeypatch=monkeypatch,
        )
        # env var is not set by main when flag is absent
        # (it was cleared by monkeypatch above and main didn't set it)


class TestMainExitQuit:
    def test_exit_input_terminates(self, monkeypatch):
        """Typing 'exit' should call sys.exit(0)."""
        monkeypatch.delenv("GIT_REPOS", raising=False)
        exc = _run_main(["perfx"], ["exit"], monkeypatch)
        assert exc.code == 0

    def test_quit_input_terminates(self, monkeypatch):
        """Typing 'quit' should call sys.exit(0)."""
        monkeypatch.delenv("GIT_REPOS", raising=False)
        exc = _run_main(["perfx"], ["quit"], monkeypatch)
        assert exc.code == 0

    def test_exit_case_insensitive(self, monkeypatch):
        """'EXIT' should also terminate the loop."""
        monkeypatch.delenv("GIT_REPOS", raising=False)
        exc = _run_main(["perfx"], ["EXIT"], monkeypatch)
        assert exc.code == 0


class TestMainKeyboardInterrupt:
    def test_keyboard_interrupt_prints_bye(self, monkeypatch, capsys):
        """KeyboardInterrupt from input() should print 'Bye!' and exit 0."""
        monkeypatch.delenv("GIT_REPOS", raising=False)
        monkeypatch.setattr("builtins.input", MagicMock(side_effect=KeyboardInterrupt))

        mock_agent = MagicMock()
        with patch("sys.argv", ["perfx"]):
            with patch("perfx.main.Agent", return_value=mock_agent):
                with pytest.raises(SystemExit) as exc_info:
                    import perfx.main as main_module
                    main_module.main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "Bye" in captured.out

    def test_eof_error_prints_bye(self, monkeypatch, capsys):
        """EOFError from input() should print 'Bye!' and exit 0."""
        monkeypatch.delenv("GIT_REPOS", raising=False)
        monkeypatch.setattr("builtins.input", MagicMock(side_effect=EOFError))

        mock_agent = MagicMock()
        with patch("sys.argv", ["perfx"]):
            with patch("perfx.main.Agent", return_value=mock_agent):
                with pytest.raises(SystemExit) as exc_info:
                    import perfx.main as main_module
                    main_module.main()

        assert exc_info.value.code == 0
        assert "Bye" in capsys.readouterr().out


class TestMainEmptyInput:
    def test_empty_input_skipped(self, monkeypatch):
        """Empty input should be skipped; next input is processed."""
        monkeypatch.delenv("GIT_REPOS", raising=False)

        mock_agent = MagicMock()
        mock_agent.chat.return_value = "pong"

        # Empty string -> skipped, "exit" -> terminates
        exc = _run_main(["perfx"], ["", "exit"], monkeypatch, mock_agent=mock_agent)
        assert exc.code == 0
        # chat should NOT have been called (empty input was skipped)
        mock_agent.chat.assert_not_called()


class TestMainAgentChat:
    def test_chat_response_printed(self, monkeypatch, capsys):
        """A normal agent response should be printed to stdout."""
        monkeypatch.delenv("GIT_REPOS", raising=False)

        mock_agent = MagicMock()
        mock_agent.chat.return_value = "The answer is 42."

        _run_main(["perfx"], ["hello", "exit"], monkeypatch, mock_agent=mock_agent)

        captured = capsys.readouterr()
        assert "The answer is 42." in captured.out

    def test_agent_exception_is_caught_and_printed(self, monkeypatch, capsys):
        """Exceptions from agent.chat() should be caught and printed, not crash the loop."""
        monkeypatch.delenv("GIT_REPOS", raising=False)

        mock_agent = MagicMock()
        # First call raises, second input causes exit
        mock_agent.chat.side_effect = RuntimeError("something went wrong")

        _run_main(["perfx"], ["hello", "exit"], monkeypatch, mock_agent=mock_agent)

        captured = capsys.readouterr()
        assert "something went wrong" in captured.out

    def test_repos_printed_when_configured(self, monkeypatch, capsys):
        """When GIT_REPOS is set, configured repos should be printed at startup."""
        monkeypatch.setenv("GIT_REPOS", "https://github.com/org/myrepo")

        _run_main(["perfx"], ["exit"], monkeypatch)

        captured = capsys.readouterr()
        assert "org/myrepo" in captured.out
