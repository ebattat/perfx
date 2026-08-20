"""Integration tests for agent/github/tools.py"""
import os
import pytest
from unittest.mock import MagicMock, patch
from perfx.github.github import (
    github_get_issue,
    github_list_issues,
    github_search_issues,
    github_search_code,
    github_get_file,
)

REPO = "redhat-performance/benchmark-runner"


@pytest.fixture(scope="session", autouse=True)
def require_github_access():
    import requests
    r = requests.get(f"https://api.github.com/repos/{REPO}", timeout=10)
    if r.status_code == 403:
        pytest.skip("GitHub rate limit exceeded — set GITHUB_TOKEN to increase quota")


@pytest.fixture(scope="session")
def first_open_issue():
    issues = github_list_issues(REPO, state="open", limit=1)
    if not issues:
        pytest.skip("No open issues found in repo")
    return issues[0]


class TestGithubListIssues:
    def test_returns_list(self):
        result = github_list_issues(REPO, state="open", limit=5)
        assert isinstance(result, list)

    def test_issue_fields(self):
        result = github_list_issues(REPO, state="open", limit=1)
        if result:
            assert {"number", "title", "state", "url"}.issubset(result[0])

    def test_closed_state(self):
        result = github_list_issues(REPO, state="closed", limit=3)
        assert isinstance(result, list)

    def test_limit_respected(self):
        result = github_list_issues(REPO, state="all", limit=3)
        assert len(result) <= 3


class TestGithubGetIssue:
    def test_get_by_number(self, first_open_issue):
        number = first_open_issue["number"]
        issue = github_get_issue(REPO, number)
        assert issue["number"] == number
        assert {"title", "state", "url", "author"}.issubset(issue)

    def test_nonexistent_issue_raises(self):
        with pytest.raises(Exception):
            github_get_issue(REPO, 9999999)


class TestGithubSearchIssues:
    def test_returns_list(self):
        result = github_search_issues(f"repo:{REPO} is:issue", limit=5)
        assert isinstance(result, list)

    @pytest.mark.skipif(not os.environ.get("GIT_REPOS"), reason="GIT_REPOS not configured")
    def test_scoped_to_configured_repos(self):
        result = github_search_issues("benchmark", limit=5)
        for item in result:
            assert item["repo"] == REPO

    def test_result_fields(self):
        result = github_search_issues(f"repo:{REPO} is:issue", limit=1)
        if result:
            assert {"number", "title", "state", "repo", "url"}.issubset(result[0])


class TestGithubSearchCode:
    @pytest.mark.skipif(not os.environ.get("GIT_REPOS"), reason="GIT_REPOS not configured")
    def test_returns_results(self):
        result = github_search_code("yaml", limit=5)
        assert "results" in result
        assert len(result["results"]) > 0

    @pytest.mark.skipif(not os.environ.get("GIT_REPOS"), reason="GIT_REPOS not configured")
    def test_windows_template_found(self):
        result = github_search_code("windows vm yaml", limit=10)
        assert "results" in result
        paths = [r["path"] for r in result["results"]]
        assert any("windows" in p for p in paths)

    @pytest.mark.skipif(not os.environ.get("GIT_REPOS"), reason="GIT_REPOS not configured")
    def test_no_match_returns_message(self):
        result = github_search_code("xyznonexistentfile123", limit=5)
        assert "results" in result or "message" in result

    def test_result_fields(self):
        result = github_search_code("yaml", limit=1)
        if result.get("results"):
            assert {"name", "path", "repo", "url"}.issubset(result["results"][0])

    def test_results_scoped_to_configured_repos(self):
        result = github_search_code("yaml", limit=10)
        for item in result.get("results", []):
            assert item["repo"] == REPO


class TestGithubGetFile:
    def test_get_readme(self):
        result = github_get_file(REPO, "README.md")
        assert {"path", "url", "content"}.issubset(result)
        assert len(result["content"]) > 0

    def test_get_windows_vm_template(self):
        result = github_get_file(
            REPO,
            "benchmark_runner/common/template_operations/templates/windows/internal_data/windows_vm_template.yaml",
        )
        assert "apiVersion" in result["content"]

    def test_nonexistent_path_raises(self):
        with pytest.raises(Exception):
            github_get_file(REPO, "nonexistent/path/file.yaml")

    def test_blocked_repo_raises(self, monkeypatch):
        monkeypatch.setenv("GIT_REPOS", f"https://github.com/{REPO}")
        with pytest.raises(PermissionError):
            github_get_file("some-other-org/other-repo", "README.md")


# ---------------------------------------------------------------------------
# Unit tests (no real network calls) for edge-case branches
# ---------------------------------------------------------------------------

class TestGetRetry401:
    def test_retries_without_auth_on_401(self, monkeypatch):
        """_get should retry without Authorization header on 401."""
        import requests as req
        from perfx.github import github as gh_module

        # First call → 401, second call → 200 with JSON body
        first = MagicMock()
        first.status_code = 401

        second = MagicMock()
        second.status_code = 200
        second.json.return_value = {"ok": True}
        second.raise_for_status = MagicMock()

        with patch("requests.get", side_effect=[first, second]) as mock_get:
            result = gh_module._get("/repos/org/repo/issues/1")

        assert result == {"ok": True}
        # Second call must NOT include Authorization
        second_call_headers = mock_get.call_args_list[1][1]["headers"]
        assert "Authorization" not in second_call_headers


class TestSearchIssuesRepoInjection:
    def test_injects_repo_filter_when_allowed_repos_set(self, monkeypatch):
        """github_search_issues appends repo: filters when GIT_REPOS is configured."""
        monkeypatch.setenv("GIT_REPOS", f"https://github.com/{REPO}")

        mock_data = {
            "items": [
                {
                    "number": 1,
                    "title": "T",
                    "state": "open",
                    "repository_url": f"https://api.github.com/repos/{REPO}",
                    "html_url": f"https://github.com/{REPO}/issues/1",
                }
            ]
        }

        with patch("perfx.github.github._get", return_value=mock_data) as mock_get:
            result = github_search_issues("some query without repo filter", limit=5)

        called_params = mock_get.call_args[1]["params"]
        assert f"repo:{REPO}" in called_params["q"]
        assert len(result) == 1


class TestCreateIssueWithLabels:
    def test_labels_included_in_payload(self, monkeypatch):
        """github_create_issue sends labels in the POST payload."""
        monkeypatch.setenv("GITHUB_TOKEN", "fake-token")
        monkeypatch.delenv("GIT_REPOS", raising=False)

        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {
            "number": 42,
            "title": "Test Issue",
            "html_url": f"https://github.com/{REPO}/issues/42",
        }

        with patch("requests.post", return_value=mock_resp) as mock_post:
            from perfx.github.github import github_create_issue
            result = github_create_issue(REPO, "Test Issue", body="body", labels=["bug", "enhancement"])

        posted_json = mock_post.call_args[1]["json"]
        assert posted_json["labels"] == ["bug", "enhancement"]
        assert result["number"] == 42


class TestSearchCodeExtensionFilter:
    def test_extension_filter_excludes_non_matching_files(self, monkeypatch):
        """github_search_code with extension:yaml should skip non-.yaml files."""
        monkeypatch.setenv("GIT_REPOS", f"https://github.com/{REPO}")

        fake_tree = [
            {"type": "blob", "path": "config/benchmark.yaml"},
            {"type": "blob", "path": "config/benchmark.json"},  # should be excluded
            {"type": "blob", "path": "scripts/benchmark.sh"},  # should be excluded
        ]

        import perfx.github.github as gh_module
        # Clear in-memory tree cache to force path through _load_disk_cache / _get
        gh_module._tree_cache.clear()

        with patch("perfx.github.github._get", return_value={"tree": fake_tree}):
            with patch("perfx.github.github._load_disk_cache", return_value=None):
                with patch("perfx.github.github._save_disk_cache"):
                    result = github_search_code("extension:yaml benchmark", limit=10)

        paths = [r["path"] for r in result.get("results", [])]
        assert "config/benchmark.yaml" in paths
        assert "config/benchmark.json" not in paths
        assert "scripts/benchmark.sh" not in paths


class TestSearchCodeSavesCache:
    def test_save_disk_cache_called_when_cache_miss(self, monkeypatch):
        """github_search_code should persist the tree to disk on cache miss."""
        monkeypatch.setenv("GIT_REPOS", f"https://github.com/{REPO}")

        fake_tree = [{"type": "blob", "path": "README.md"}]

        import perfx.github.github as gh_module
        gh_module._tree_cache.clear()

        with patch("perfx.github.github._get", return_value={"tree": fake_tree}):
            with patch("perfx.github.github._load_disk_cache", return_value=None):
                with patch("perfx.github.github._save_disk_cache") as mock_save:
                    github_search_code("README", limit=5)

        mock_save.assert_called_once()
