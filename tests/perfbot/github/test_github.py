"""Integration tests for agent/github/tools.py"""
import pytest
from perfbot.github.github import (
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

    def test_scoped_to_configured_repos(self):
        result = github_search_issues("benchmark", limit=5)
        for item in result:
            assert item["repo"] == REPO

    def test_result_fields(self):
        result = github_search_issues(f"repo:{REPO} is:issue", limit=1)
        if result:
            assert {"number", "title", "state", "repo", "url"}.issubset(result[0])


class TestGithubSearchCode:
    def test_returns_results(self):
        result = github_search_code("yaml", limit=5)
        assert "results" in result
        assert len(result["results"]) > 0

    def test_windows_template_found(self):
        result = github_search_code("windows vm yaml", limit=10)
        assert "results" in result
        paths = [r["path"] for r in result["results"]]
        assert any("windows" in p for p in paths)

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

    def test_blocked_repo_raises(self):
        with pytest.raises(PermissionError):
            github_get_file("some-other-org/other-repo", "README.md")
