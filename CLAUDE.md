# PerfBot — project rules

## Package structure

Source lives in `perfbot/`, tests mirror it under `tests/perfbot/`:
- `perfbot/github/github.py` → `tests/perfbot/github/test_github.py`
- `perfbot/jira/jira.py` → `tests/perfbot/jira/test_jira.py`

## Adding tests

Use the `/add-tests` skill. Key rules:
- pytest, class-based, integration tests (no mocks)
- Skip when credentials are missing, not fail
- Jira JQL must always be bounded (include `project is not EMPTY`)
- Run `pytest <file> -v` and fix failures before reporting done

## Credentials

All credentials via `export` or `.env` (never committed):
- `GEMINI_API_KEY` — Gemini model
- `GITHUB_TOKEN` — needed for >60 req/hour on public repos
- `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN` — Jira access
- `GIT_REPOS` — list of allowed GitHub repos

## Running the agent

```bash
cd ~/PycharmProjects/PerfBot/perfbot
source .venv/bin/activate
python run.py
```
