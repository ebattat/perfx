"""Integration tests for agent/jira/tools.py"""
import os
import pytest
from perfbot.jira.jira import (
    jira_get_issue,
    jira_search_issues,
)


def jira_configured() -> bool:
    return all([
        os.environ.get("JIRA_URL"),
        os.environ.get("JIRA_EMAIL"),
        os.environ.get("JIRA_API_TOKEN"),
    ])


pytestmark = pytest.mark.skipif(
    not jira_configured(),
    reason="JIRA_URL, JIRA_EMAIL, JIRA_API_TOKEN must all be set",
)


BOUNDED_JQL = "project is not EMPTY order by created DESC"


@pytest.fixture(scope="session")
def first_issue():
    results = jira_search_issues(BOUNDED_JQL, limit=1)
    if not results:
        pytest.skip("No Jira issues found")
    return results[0]


class TestJiraSearchIssues:
    def test_returns_list(self):
        result = jira_search_issues(BOUNDED_JQL, limit=5)
        assert isinstance(result, list)

    def test_result_fields(self):
        result = jira_search_issues(BOUNDED_JQL, limit=1)
        if result:
            assert {"key", "summary", "status"}.issubset(result[0])

    def test_limit_respected(self):
        result = jira_search_issues(BOUNDED_JQL, limit=3)
        assert len(result) <= 3

    def test_project_filter(self):
        result = jira_search_issues("project is not EMPTY order by created DESC", limit=3)
        assert isinstance(result, list)


class TestJiraGetIssue:
    def test_get_by_key(self, first_issue):
        key = first_issue["key"]
        issue = jira_get_issue(key)
        assert issue["key"] == key
        assert {"summary", "status", "url"}.issubset(issue)

    def test_invalid_key_raises(self):
        with pytest.raises(Exception):
            jira_get_issue("INVALID-00000")


