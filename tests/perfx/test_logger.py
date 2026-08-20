"""Unit tests for perfx/logger.py"""
import logging
import pytest
from perfx.logger import get_logger, setup_logging


class TestGetLogger:
    def test_returns_logger(self):
        log = get_logger("test")
        assert isinstance(log, logging.Logger)

    def test_logger_name_prefixed(self):
        log = get_logger("mymodule")
        assert "mymodule" in log.name

    def test_different_names_return_different_loggers(self):
        a = get_logger("aaa")
        b = get_logger("bbb")
        assert a is not b


class TestSetupLogging:
    def test_setup_does_not_raise(self):
        setup_logging()

    def test_debug_env_sets_debug_level(self, monkeypatch):
        monkeypatch.setenv("PERFX_DEBUG", "1")
        from perfx.logger import _resolve_level
        assert _resolve_level() == logging.DEBUG

    def test_log_level_env_sets_level(self, monkeypatch):
        monkeypatch.setenv("PERFX_LOG_LEVEL", "error")
        monkeypatch.delenv("PERFX_DEBUG", raising=False)
        from perfx.logger import _resolve_level
        assert _resolve_level() == logging.ERROR

    def test_unknown_level_defaults_to_warning(self, monkeypatch):
        monkeypatch.setenv("PERFX_LOG_LEVEL", "unknown")
        monkeypatch.delenv("PERFX_DEBUG", raising=False)
        from perfx.logger import _resolve_level
        assert _resolve_level() == logging.WARNING

    def test_root_logger_configured(self):
        setup_logging()
        root = logging.getLogger("perfx")
        assert root.level in (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR)
