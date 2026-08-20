"""Unit tests for perfx/github/github.py helper functions."""
import json
import time
import pytest
from unittest.mock import patch, MagicMock
from perfx.github.github import (
    _allowed_repos, _assert_allowed, _headers,
    _cache_path, _load_disk_cache, _save_disk_cache,
    github_get_issue, github_list_issues, github_search_issues,
    github_create_issue,
)


class TestAllowedRepos:
    def test_empty_env_returns_empty(self, monkeypatch):
        monkeypatch.delenv("GIT_REPOS", raising=False)
        assert _allowed_repos() == []

    def test_single_url(self, monkeypatch):
        monkeypatch.setenv("GIT_REPOS", "https://github.com/redhat-performance/benchmark-runner")
        repos = _allowed_repos()
        assert repos == ["redhat-performance/benchmark-runner"]

    def test_multiple_urls(self, monkeypatch):
        monkeypatch.setenv("GIT_REPOS", "https://github.com/org/repo1 https://github.com/org/repo2")
        repos = _allowed_repos()
        assert "org/repo1" in repos
        assert "org/repo2" in repos

    def test_trailing_slash_stripped(self, monkeypatch):
        monkeypatch.setenv("GIT_REPOS", "https://github.com/org/repo/")
        repos = _allowed_repos()
        assert "org/repo" in repos

    def test_non_github_urls_ignored(self, monkeypatch):
        monkeypatch.setenv("GIT_REPOS", "https://gitlab.com/org/repo")
        assert _allowed_repos() == []


class TestAssertAllowed:
    def test_passes_when_no_repos_configured(self, monkeypatch):
        monkeypatch.delenv("GIT_REPOS", raising=False)
        _assert_allowed("any/repo")  # should not raise

    def test_passes_when_repo_in_list(self, monkeypatch):
        monkeypatch.setenv("GIT_REPOS", "https://github.com/org/repo")
        _assert_allowed("org/repo")  # should not raise

    def test_raises_when_repo_not_in_list(self, monkeypatch):
        monkeypatch.setenv("GIT_REPOS", "https://github.com/org/allowed-repo")
        with pytest.raises(PermissionError):
            _assert_allowed("other-org/other-repo")


class TestHeaders:
    def test_no_token_returns_accept_only(self, monkeypatch):
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        h = _headers()
        assert "Authorization" not in h
        assert "Accept" in h

    def test_with_token_includes_authorization(self, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "mytoken")
        h = _headers()
        assert "Authorization" in h
        assert "mytoken" in h["Authorization"]


class TestDiskCache:
    def test_cache_path_uses_safe_name(self, tmp_path):
        import perfx.github.github as gh
        original = gh._CACHE_DIR
        gh._CACHE_DIR = tmp_path
        p = _cache_path("org/repo")
        gh._CACHE_DIR = original
        assert "org__repo" in p.name

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        import perfx.github.github as gh
        monkeypatch.setattr(gh, "_CACHE_DIR", tmp_path)
        tree = [{"path": "file.txt", "type": "blob"}]
        _save_disk_cache("org/repo", tree)
        loaded = _load_disk_cache("org/repo")
        assert loaded == tree

    def test_load_returns_none_when_no_cache(self, tmp_path, monkeypatch):
        import perfx.github.github as gh
        monkeypatch.setattr(gh, "_CACHE_DIR", tmp_path)
        assert _load_disk_cache("org/nonexistent") is None

    def test_load_returns_none_when_cache_corrupt(self, tmp_path, monkeypatch):
        import perfx.github.github as gh
        monkeypatch.setattr(gh, "_CACHE_DIR", tmp_path)
        p = tmp_path / "tree_org__repo.json"
        p.write_text("not valid json{{{")
        assert _load_disk_cache("org/repo") is None

    def test_load_returns_none_when_expired(self, tmp_path, monkeypatch):
        import perfx.github.github as gh
        monkeypatch.setattr(gh, "_CACHE_DIR", tmp_path)
        # write cache with old timestamp
        p = tmp_path / "tree_org__repo.json"
        p.write_text(json.dumps({"ts": time.time() - 7200, "tree": []}))
        assert _load_disk_cache("org/repo") is None


class TestGithubGetIssue:
    def test_returns_issue_dict(self, monkeypatch):
        monkeypatch.delenv("GIT_REPOS", raising=False)
        fake = {
            "number": 42, "title": "Bug", "state": "open",
            "body": "desc", "html_url": "https://github.com/org/repo/issues/42",
            "user": {"login": "alice"}, "labels": [], "created_at": "2026-01-01",
        }
        with patch("perfx.github.github._get", return_value=fake):
            result = github_get_issue("org/repo", 42)
        assert result["number"] == 42
        assert result["title"] == "Bug"
        assert result["author"] == "alice"


class TestGithubListIssues:
    def test_returns_list(self, monkeypatch):
        monkeypatch.delenv("GIT_REPOS", raising=False)
        fake = [
            {"number": 1, "title": "Issue 1", "state": "open",
             "html_url": "https://github.com/org/repo/issues/1", "labels": []},
        ]
        with patch("perfx.github.github._get", return_value=fake):
            result = github_list_issues("org/repo", state="open", limit=5)
        assert len(result) == 1
        assert result[0]["number"] == 1


class TestGithubSearchIssues:
    def test_returns_mapped_list(self, monkeypatch):
        monkeypatch.delenv("GIT_REPOS", raising=False)
        fake = {
            "items": [
                {"number": 10, "title": "Search result", "state": "open",
                 "repository_url": "https://api.github.com/repos/org/repo",
                 "html_url": "https://github.com/org/repo/issues/10"},
            ]
        }
        with patch("perfx.github.github._get", return_value=fake):
            result = github_search_issues("repo:org/repo bug", limit=5)
        assert result[0]["number"] == 10
        assert result[0]["repo"] == "org/repo"


class TestGithubCreateIssue:
    def test_raises_without_token(self, monkeypatch):
        monkeypatch.delenv("GIT_REPOS", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with pytest.raises(EnvironmentError, match="GITHUB_TOKEN"):
            github_create_issue("org/repo", "New issue")

    def test_creates_issue_with_token(self, monkeypatch):
        monkeypatch.delenv("GIT_REPOS", raising=False)
        monkeypatch.setenv("GITHUB_TOKEN", "mytoken")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"number": 5, "title": "New", "html_url": "https://github.com/org/repo/issues/5"}
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.post", return_value=mock_resp):
            result = github_create_issue("org/repo", "New issue", "body")
        assert result["number"] == 5


class TestGithubSearchCode:
    def test_no_repos_configured_returns_error(self, monkeypatch):
        from perfx.github.github import github_search_code
        monkeypatch.delenv("GIT_REPOS", raising=False)
        result = github_search_code("yaml")
        assert "error" in result

    def test_returns_matching_files(self, monkeypatch, tmp_path):
        from perfx.github.github import github_search_code
        import perfx.github.github as gh
        monkeypatch.setenv("GIT_REPOS", "https://github.com/org/repo")
        monkeypatch.setattr(gh, "_tree_cache", {})
        monkeypatch.setattr(gh, "_CACHE_DIR", tmp_path)
        fake_tree = [
            {"type": "blob", "path": "docs/windows_vm_template.yaml"},
            {"type": "blob", "path": "README.md"},
        ]
        with patch("perfx.github.github._get", return_value={"tree": fake_tree}):
            result = github_search_code("windows yaml", limit=5)
        assert "results" in result
        assert any("windows" in r["path"] for r in result["results"])

    def test_no_match_returns_message(self, monkeypatch, tmp_path):
        from perfx.github.github import github_search_code
        import perfx.github.github as gh
        monkeypatch.setenv("GIT_REPOS", "https://github.com/org/repo")
        monkeypatch.setattr(gh, "_tree_cache", {})
        monkeypatch.setattr(gh, "_CACHE_DIR", tmp_path)
        fake_tree = [{"type": "blob", "path": "README.md"}]
        with patch("perfx.github.github._get", return_value={"tree": fake_tree}):
            result = github_search_code("xyznonexistentfile123", limit=5)
        assert "message" in result

    def test_uses_disk_cache(self, monkeypatch, tmp_path):
        from perfx.github.github import github_search_code, _save_disk_cache
        import perfx.github.github as gh
        monkeypatch.setenv("GIT_REPOS", "https://github.com/org/repo")
        monkeypatch.setattr(gh, "_tree_cache", {})
        monkeypatch.setattr(gh, "_CACHE_DIR", tmp_path)
        cached_tree = [{"type": "blob", "path": "cached_file.yaml"}]
        _save_disk_cache("org/repo", cached_tree)
        # _get should NOT be called if cache hit
        with patch("perfx.github.github._get") as mock_get:
            github_search_code("cached yaml", limit=5)
        mock_get.assert_not_called()


class TestGithubAddComment:
    def test_raises_without_token(self, monkeypatch):
        from perfx.github.github import github_add_comment
        monkeypatch.delenv("GIT_REPOS", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with pytest.raises(EnvironmentError, match="GITHUB_TOKEN"):
            github_add_comment("org/repo", 1, "comment body")

    def test_adds_comment_with_token(self, monkeypatch):
        from perfx.github.github import github_add_comment
        monkeypatch.delenv("GIT_REPOS", raising=False)
        monkeypatch.setenv("GITHUB_TOKEN", "mytoken")
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"id": 999, "html_url": "https://github.com/org/repo/issues/42#comment-999"}
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.post", return_value=mock_resp):
            result = github_add_comment("org/repo", 42, "Great work!")
        assert result["comment_id"] == 999
        assert "url" in result
