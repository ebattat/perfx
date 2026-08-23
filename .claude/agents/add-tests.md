---
name: add-tests
description: Add pytest integration tests for a new or changed source file in the perfx package. Mirrors the source structure under tests/perfx/.
---

When adding tests for a source file in this project, follow these rules:

## Test location mirrors source location

| Source file | Test file |
|---|---|
| `perfx/github/github.py` | `tests/perfx/github/test_github.py` |
| `perfx/jira/jira.py` | `tests/perfx/jira/test_jira.py` |
| `perfx/foo/bar.py` | `tests/perfx/foo/test_bar.py` |

Always create `__init__.py` files for any new test directories.

## Test style rules

- Use **pytest** with class-based grouping: one `class Test<FunctionName>` per public function.
- Write **integration tests** — call the real function, do NOT mock external services.
- Skip gracefully when credentials or external services are unavailable (use `pytest.mark.skipif` or `pytest.skip()`).
- Use `scope="session"` fixtures for expensive setup (e.g. fetching a real issue to reuse across tests).
- Assert on structure AND values: check required keys exist and types are correct.
- Tests that create or modify data (Jira issues, GitHub comments) must be guarded by an env var (e.g. `JIRA_TEST_PROJECT`) so they don't run by default.

## Credential guards

GitHub tests:
```python
@pytest.fixture(scope="session", autouse=True)
def require_github_access():
    import requests
    r = requests.get(f"https://api.github.com/repos/{REPO}", timeout=10)
    if r.status_code == 403:
        pytest.skip("GitHub rate limit exceeded — set GITHUB_TOKEN to increase quota")
```

Jira tests:
```python
def jira_configured() -> bool:
    return all([os.environ.get("JIRA_URL"), os.environ.get("JIRA_EMAIL"), os.environ.get("JIRA_API_TOKEN")])

pytestmark = pytest.mark.skipif(not jira_configured(), reason="JIRA_* env vars must be set")
```

## JQL queries must be bounded

Jira Cloud rejects unbounded JQL. Always include a project filter:
```python
# BAD
jira_search_issues("order by created DESC")

# GOOD
jira_search_issues("project is not EMPTY order by created DESC")
```

## Run tests after writing

After creating or updating a test file, always run:
```bash
source .venv/bin/activate
pytest <test_file_path> -v
```

Fix any failures before reporting done.
