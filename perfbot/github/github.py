import json
import os
import re
import base64
import time
from pathlib import Path
import requests
from perfbot.logger import get_logger

log = get_logger("github")

GITHUB_API = "https://api.github.com"
_tree_cache: dict[str, list] = {}

_CACHE_DIR = Path(__file__).parent.parent.parent / ".cache"
_CACHE_TTL = 3600  # seconds — 1 hour


def _cache_path(repo: str) -> Path:
    safe = repo.replace("/", "__")
    return _CACHE_DIR / f"tree_{safe}.json"


def _load_disk_cache(repo: str) -> list | None:
    p = _cache_path(repo)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        if time.time() - data["ts"] < _CACHE_TTL:
            return data["tree"]
    except Exception:
        pass
    return None


def _save_disk_cache(repo: str, tree: list):
    _CACHE_DIR.mkdir(exist_ok=True)
    _cache_path(repo).write_text(json.dumps({"ts": time.time(), "tree": tree}))


def _headers() -> dict:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    return {"Accept": "application/vnd.github+json"}


def _get(path: str, params: dict = None) -> dict | list:
    url = f"{GITHUB_API}{path}"
    log.debug("GET %s params=%s", url, params)
    resp = requests.get(url, headers=_headers(), params=params, timeout=15)
    if resp.status_code == 401:
        log.debug("401 received, retrying without auth")
        resp = requests.get(url, headers={"Accept": "application/vnd.github+json"}, params=params, timeout=15)
    log.debug("response status=%s", resp.status_code)
    resp.raise_for_status()
    return resp.json()


def _allowed_repos() -> list[str]:
    raw = os.environ.get("GIT_REPOS", "")
    if not raw:
        return []
    urls = re.findall(r'https?://[^\s\'">,\]]+', raw)
    repos = []
    for url in urls:
        match = re.search(r'github\.com/([^/]+/[^/]+)', url.rstrip("/"))
        if match:
            repos.append(match.group(1))
    return repos


def _assert_allowed(repo: str):
    allowed = _allowed_repos()
    if allowed and repo not in allowed:
        raise PermissionError(f"Repo '{repo}' is not in GIT_REPOS: {allowed}")


def github_get_issue(repo: str, number: int) -> dict:
    _assert_allowed(repo)
    i = _get(f"/repos/{repo}/issues/{number}")
    return {
        "number": i["number"],
        "title": i["title"],
        "state": i["state"],
        "body": i.get("body"),
        "url": i["html_url"],
        "author": i["user"]["login"],
        "labels": [l["name"] for l in i.get("labels", [])],
        "created_at": i["created_at"],
    }


def github_list_issues(repo: str, state: str = "open", limit: int = 20) -> list[dict]:
    _assert_allowed(repo)
    issues = _get(f"/repos/{repo}/issues", params={"state": state, "per_page": min(limit, 100)})
    return [
        {
            "number": i["number"],
            "title": i["title"],
            "state": i["state"],
            "url": i["html_url"],
            "labels": [l["name"] for l in i.get("labels", [])],
        }
        for i in issues[:limit]
    ]


def github_search_issues(query: str, limit: int = 20) -> list[dict]:
    allowed = _allowed_repos()
    if allowed and "repo:" not in query:
        query += " " + " ".join(f"repo:{r}" for r in allowed)
    data = _get("/search/issues", params={"q": query, "per_page": min(limit, 100)})
    return [
        {
            "number": i["number"],
            "title": i["title"],
            "state": i["state"],
            "repo": i["repository_url"].replace(f"{GITHUB_API}/repos/", ""),
            "url": i["html_url"],
        }
        for i in data.get("items", [])[:limit]
    ]


def github_create_issue(repo: str, title: str, body: str = "", labels: list[str] = None) -> dict:
    _assert_allowed(repo)
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise EnvironmentError("GITHUB_TOKEN is required to create issues")
    payload = {"title": title, "body": body}
    if labels:
        payload["labels"] = labels
    resp = requests.post(f"{GITHUB_API}/repos/{repo}/issues", headers=_headers(), json=payload, timeout=15)
    resp.raise_for_status()
    i = resp.json()
    return {"number": i["number"], "title": i["title"], "url": i["html_url"]}


def github_add_comment(repo: str, number: int, body: str) -> dict:
    _assert_allowed(repo)
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise EnvironmentError("GITHUB_TOKEN is required to add comments")
    resp = requests.post(
        f"{GITHUB_API}/repos/{repo}/issues/{number}/comments",
        headers=_headers(), json={"body": body}, timeout=15,
    )
    resp.raise_for_status()
    c = resp.json()
    return {"comment_id": c["id"], "url": c["html_url"]}


def github_search_code(query: str, limit: int = 10) -> dict:
    allowed = _allowed_repos()
    if not allowed:
        return {"error": "No repos configured in GIT_REPOS"}

    # strip GitHub search syntax tokens (extension:, repo:, filename:, path:, language:)
    raw_keywords = [
        k.lower() for k in query.split()
        if len(k) > 1 and not re.match(r'^(extension|repo|filename|path|language):', k, re.I)
    ]
    # also extract bare extension from extension:yaml → ".yaml"
    ext_filters = [
        "." + re.match(r'^extension:(.+)', k, re.I).group(1).lower()
        for k in query.split() if re.match(r'^extension:', k, re.I)
    ]

    scored = []
    for repo_name in allowed:
        if repo_name not in _tree_cache:
            cached = _load_disk_cache(repo_name)
            if cached is not None:
                _tree_cache[repo_name] = cached
            else:
                data = _get(f"/repos/{repo_name}/git/trees/HEAD", params={"recursive": "1"})
                _tree_cache[repo_name] = data.get("tree", [])
                _save_disk_cache(repo_name, _tree_cache[repo_name])
        tree = _tree_cache[repo_name]
        branch = "main"
        for item in tree:
            if item["type"] != "blob":
                continue
            path_lower = item["path"].lower()
            filename_lower = path_lower.split("/")[-1]

            # apply extension filter if present
            if ext_filters and not any(filename_lower.endswith(e) for e in ext_filters):
                continue

            matched = [k for k in raw_keywords if k in path_lower]
            if not matched:
                continue

            # score: keyword matches in filename worth more than in directory
            filename_hits = sum(1 for k in matched if k in filename_lower)
            score = filename_hits * 10 + len(matched)

            scored.append((score, {
                "name": item["path"].split("/")[-1],
                "path": item["path"],
                "repo": repo_name,
                "url": f"https://github.com/{repo_name}/blob/{branch}/{item['path']}",
            }))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = [e for _, e in scored][:limit]
    if not results:
        return {
            "message": f"No files found matching '{query}' in repos: {allowed}. Try broader keywords.",
            "results": [],
        }
    return {"results": results}


def github_get_file(repo: str, path: str) -> dict:
    _assert_allowed(repo)
    data = _get(f"/repos/{repo}/contents/{path}")
    content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    return {"path": data["path"], "url": data["html_url"], "content": content}
