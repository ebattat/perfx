"""Unit tests for perfx/secrets.py"""
import subprocess
import pytest
from unittest.mock import patch, MagicMock
from perfx.secrets import _keychain_get, load_secrets


class TestKeychainGet:
    def test_returns_password_on_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "mysecret\n"
        with patch("subprocess.run", return_value=mock_result):
            result = _keychain_get("GEMINI_API_KEY")
        assert result == "mysecret"

    def test_returns_none_on_nonzero_returncode(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("subprocess.run", return_value=mock_result):
            result = _keychain_get("GEMINI_API_KEY")
        assert result is None

    def test_returns_none_when_security_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = _keychain_get("GEMINI_API_KEY")
        assert result is None


class TestLoadSecrets:
    def test_skips_keychain_when_env_already_set(self, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "already-set")
        with patch("perfx.secrets._keychain_get", return_value=None) as mock_kc:
            load_secrets()
        # _keychain_get should NOT be called for GEMINI_API_KEY
        called_accounts = [call[0][0] for call in mock_kc.call_args_list]
        assert "GEMINI_API_KEY" not in called_accounts

    def test_sets_env_from_keychain(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with patch("perfx.secrets._keychain_get", return_value="token123"):
            load_secrets()
        import os
        assert os.environ.get("GITHUB_TOKEN") == "token123"

    def test_missing_key_not_set_when_keychain_empty(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with patch("perfx.secrets._keychain_get", return_value=None):
            load_secrets()
        import os
        assert os.environ.get("GITHUB_TOKEN") is None
