import os
from jira import JIRA, JIRAError
from perfbot.logger import get_logger

log = get_logger("jira")


def _client() -> JIRA:
    url = os.environ.get("JIRA_URL")
    email = os.environ.get("JIRA_EMAIL")
    token = os.environ.get("JIRA_API_TOKEN")
    if not all([url, email, token]):
        raise EnvironmentError("JIRA_URL, JIRA_EMAIL, and JIRA_API_TOKEN must all be set")
    return JIRA(server=url, basic_auth=(email, token))


def jira_get_issue(issue_key: str) -> dict:
    issue = _client().issue(issue_key)
    return {
        "key": issue.key,
        "summary": issue.fields.summary,
        "status": issue.fields.status.name,
        "assignee": issue.fields.assignee.displayName if issue.fields.assignee else None,
        "reporter": issue.fields.reporter.displayName if issue.fields.reporter else None,
        "priority": issue.fields.priority.name if issue.fields.priority else None,
        "description": issue.fields.description,
        "url": f"{os.environ.get('JIRA_URL')}/browse/{issue.key}",
    }


def jira_search_issues(jql: str, limit: int = 20) -> list[dict]:
    issues = _client().search_issues(jql, maxResults=limit)
    return [
        {
            "key": i.key,
            "summary": i.fields.summary,
            "status": i.fields.status.name,
            "assignee": i.fields.assignee.displayName if i.fields.assignee else None,
            "priority": i.fields.priority.name if i.fields.priority else None,
        }
        for i in issues
    ]


def jira_create_issue(project: str, summary: str, description: str = "", issue_type: str = "Task") -> dict:
    issue = _client().create_issue(fields={
        "project": {"key": project},
        "summary": summary,
        "description": description,
        "issuetype": {"name": issue_type},
    })
    return {
        "key": issue.key,
        "summary": issue.fields.summary,
        "url": f"{os.environ.get('JIRA_URL')}/browse/{issue.key}",
    }


def jira_update_issue(issue_key: str, summary: str = None, description: str = None, assignee: str = None) -> dict:
    client = _client()
    issue = client.issue(issue_key)
    fields = {}
    if summary:
        fields["summary"] = summary
    if description:
        fields["description"] = description
    if assignee:
        fields["assignee"] = {"name": assignee}
    if fields:
        issue.update(fields=fields)
    return {"key": issue_key, "updated_fields": list(fields.keys())}


def jira_add_comment(issue_key: str, body: str) -> dict:
    comment = _client().add_comment(issue_key, body)
    return {"comment_id": comment.id, "issue_key": issue_key}
