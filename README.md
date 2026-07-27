# jira-github-agent

A standalone CLI agent powered by Gemini that can read, create, update, and search GitHub issues and PRs.

## Setup

```bash
cd ~/PycharmProjects/jira-github-agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and fill in GEMINI_API_KEY and GITHUB_TOKEN
```

## Run

```bash
python -m agent.main
```

## Example prompts

- `List open issues in owner/repo`
- `Get issue #42 in owner/repo`
- `Search for bug issues in owner/repo`
- `Create an issue in owner/repo titled "Fix login crash"`
- `Add a comment to issue #10 in owner/repo saying "Will fix in next sprint"`

## Getting credentials

| Credential | Where to get it |
|---|---|
| `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/app/apikey) |
| `GITHUB_TOKEN` | GitHub → Settings → Developer settings → Personal access tokens |

GitHub token needs `repo` scope (or `public_repo` for public repos only).
