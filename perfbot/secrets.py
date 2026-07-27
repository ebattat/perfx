import subprocess
import os


def _keychain_get(account: str) -> str | None:
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", "perfbot", "-a", account, "-w"],
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
        print(f"[warn] Not found in Keychain or env: {', '.join(missing)}")
