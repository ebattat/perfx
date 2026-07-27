import logging
import os
import sys

_LEVEL_MAP = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}

def _resolve_level() -> int:
    # PERFBOT_DEBUG=1 is a shortcut for DEBUG level
    if os.environ.get("PERFBOT_DEBUG", "").lower() in {"1", "true", "yes"}:
        return logging.DEBUG
    raw = os.environ.get("PERFBOT_LOG_LEVEL", "warning").lower()
    return _LEVEL_MAP.get(raw, logging.WARNING)


def setup_logging():
    level = _resolve_level()
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S"))
    root = logging.getLogger("perfbot")
    root.setLevel(level)
    if not root.handlers:
        root.addHandler(handler)
    root.propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"perfbot.{name}")
