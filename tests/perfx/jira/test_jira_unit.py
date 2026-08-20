"""Unit tests for perfx/jira/jira.py"""
import pytest
from unittest.mock import MagicMock, patch


def _set_jira_env(monkeypatch):
    monkeypatch.setenv("JIRA_URL", "https://jira.example.com")
    monkeypatch.setenv("JIRA_EMAIL", "user@example.com")
    monkeypatch.setenv("JIRA_API_TOKEN", "token")


def _mock_issue(key="PROJ-1", summary="Test issue", status="Open", assignee=None, priority=None):
    issue = MagicMock()
    issue.key = key
    issue.fields.summary = summary
    issue.fields.status.name = status
    issue.fields.assignee = MagicMock(displayName=assignee) if assignee else None
    issue.fields.reporter.displayName = "Reporter"
    issue.fields.priority = MagicMock(name=priority) if priority else None
    issue.fields.description = "desc"
    return issue


class TestJiraClient:
    def test_raises_when_env_vars_missing(self, monkeypatch):
        monkeypatch.delenv("JIRA_URL", raising=False)
        monkeypatch.delenv("JIRA_EMAIL", raising=False)
        monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
        from perfx.jira.jira import _client
        with pytest.raises(EnvironmentError, match="JIRA_URL"):
            _client()

    def test_raises_when_partial_env(self, monkeypatch):
        monkeypatch.setenv("JIRA_URL", "https://jira.example.com")
        monkeypatch.delenv("JIRA_EMAIL", raising=False)
        monkeypatch.delenv("JIRA_API_TOKEN", raising=False)
        from perfx.jira.jira import _client
        with pytest.raises(EnvironmentError):
            _client()


class TestJiraSearchIssues:
    def test_returns_list_of_dicts(self, monkeypatch):
        _set_jira_env(monkeypatch)
        mock_client = MagicMock()
        mock_client.search_issues.return_value = [_mock_issue()]
        with patch("perfx.jira.jira._client", return_value=mock_client):
            from perfx.jira.jira import jira_search_issues
            result = jira_search_issues("project is not EMPTY", limit=5)
        assert isinstance(result, list)
        assert result[0]["key"] == "PROJ-1"
        assert result[0]["summary"] == "Test issue"
        assert result[0]["status"] == "Open"

    def test_none_assignee_handled(self, monkeypatch):
        _set_jira_env(monkeypatch)
        mock_client = MagicMock()
        mock_client.search_issues.return_value = [_mock_issue(assignee=None)]
        with patch("perfx.jira.jira._client", return_value=mock_client):
            from perfx.jira.jira import jira_search_issues
            result = jira_search_issues("project is not EMPTY")
        assert result[0]["assignee"] is None


class TestJiraGetIssue:
    def test_returns_correct_fields(self, monkeypatch):
        _set_jira_env(monkeypatch)
        mock_issue = _mock_issue(key="PROJ-42", summary="Fix the bug", status="In Progress")
        mock_client = MagicMock()
        mock_client.issue.return_value = mock_issue
        with patch("perfx.jira.jira._client", return_value=mock_client):
            from perfx.jira.jira import jira_get_issue
            result = jira_get_issue("PROJ-42")
        assert result["key"] == "PROJ-42"
        assert result["summary"] == "Fix the bug"
        assert result["status"] == "In Progress"
        assert "url" in result
        assert "PROJ-42" in result["url"]


class TestJiraCreateIssue:
    def test_creates_issue(self, monkeypatch):
        _set_jira_env(monkeypatch)
        mock_issue = MagicMock()
        mock_issue.key = "PROJ-99"
        mock_issue.fields.summary = "New issue"
        mock_client = MagicMock()
        mock_client.create_issue.return_value = mock_issue
        with patch("perfx.jira.jira._client", return_value=mock_client):
            from perfx.jira.jira import jira_create_issue
            result = jira_create_issue("PROJ", "New issue", "desc", "Bug")
        assert result["key"] == "PROJ-99"
        assert "url" in result


class TestJiraAddComment:
    def test_adds_comment(self, monkeypatch):
        _set_jira_env(monkeypatch)
        mock_comment = MagicMock()
        mock_comment.id = "123"
        mock_client = MagicMock()
        mock_client.add_comment.return_value = mock_comment
        with patch("perfx.jira.jira._client", return_value=mock_client):
            from perfx.jira.jira import jira_add_comment
            result = jira_add_comment("PROJ-1", "This is a comment")
        assert result["comment_id"] == "123"
        assert result["issue_key"] == "PROJ-1"


class TestJiraUpdateIssue:
    def test_updates_summary_only(self, monkeypatch):
        _set_jira_env(monkeypatch)
        mock_issue = MagicMock()
        mock_client = MagicMock()
        mock_client.issue.return_value = mock_issue
        with patch("perfx.jira.jira._client", return_value=mock_client):
            from perfx.jira.jira import jira_update_issue
            result = jira_update_issue("PROJ-1", summary="New title")
        assert "summary" in result["updated_fields"]
        assert "description" not in result["updated_fields"]
        mock_issue.update.assert_called_once_with(fields={"summary": "New title"})

    def test_no_fields_skips_update(self, monkeypatch):
        _set_jira_env(monkeypatch)
        mock_issue = MagicMock()
        mock_client = MagicMock()
        mock_client.issue.return_value = mock_issue
        with patch("perfx.jira.jira._client", return_value=mock_client):
            from perfx.jira.jira import jira_update_issue
            result = jira_update_issue("PROJ-1")
        mock_issue.update.assert_not_called()
        assert result["updated_fields"] == []
