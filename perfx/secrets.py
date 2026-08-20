import subprocess
import os
from perfx.logger import get_logger

log = get_logger("secrets")


def _keychain_get(account: str) -> str | None:
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "perfx", "-a", account, "-w"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    return None


def load_secrets():
    keys = ["GEMINI_API_KEY", "JIRA_API_TOKEN", "GITHUB_TOKEN", "JIRA_URL", "JIRA_EMAIL"]
    missing = []
    for key in keys:
        if not os.environ.get(key):
            value = _keychain_get(key)
            if value:
                os.environ[key] = value
            else:
                missing.append(key)
    if missing:
        log.warning("Not found in Keychain or env: %s", ', '.join(missing))
