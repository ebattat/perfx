from google.genai import types as gtypes
from perfbot.github.github import (
    github_get_issue,
    github_list_issues,
    github_search_issues,
    github_create_issue,
    github_add_comment,
    github_search_code,
    github_get_file,
)
from perfbot.jira.jira import (
    jira_get_issue,
    jira_search_issues,
    jira_create_issue,
    jira_update_issue,
    jira_add_comment,
)

DISPATCH = {
    "github_get_issue": github_get_issue,
    "github_list_issues": github_list_issues,
    "github_search_issues": github_search_issues,
    "github_create_issue": github_create_issue,
    "github_add_comment": github_add_comment,
    "github_search_code": github_search_code,
    "github_get_file": github_get_file,
    "jira_get_issue": jira_get_issue,
    "jira_search_issues": jira_search_issues,
    "jira_create_issue": jira_create_issue,
    "jira_update_issue": jira_update_issue,
    "jira_add_comment": jira_add_comment,
}

TOOL_DECLARATIONS = [
    gtypes.Tool(
        function_declarations=[
            # ── GitHub ──────────────────────────────────────────────────────
            gtypes.FunctionDeclaration(
                name="github_get_issue",
                description="Fetch a single GitHub issue or PR by repository and issue number.",
                parameters=gtypes.Schema(
                    type=gtypes.Type.OBJECT,
                    properties={
                        "repo": gtypes.Schema(type=gtypes.Type.STRING, description="owner/repo, e.g. octocat/Hello-World"),
                        "number": gtypes.Schema(type=gtypes.Type.INTEGER, description="Issue or PR number"),
                    },
                    required=["repo", "number"],
                ),
            ),
            gtypes.FunctionDeclaration(
                name="github_list_issues",
                description="List issues for a GitHub repository.",
                parameters=gtypes.Schema(
                    type=gtypes.Type.OBJECT,
                    properties={
                        "repo": gtypes.Schema(type=gtypes.Type.STRING, description="owner/repo"),
                        "state": gtypes.Schema(type=gtypes.Type.STRING, description="open, closed, or all (default: open)"),
                        "limit": gtypes.Schema(type=gtypes.Type.INTEGER, description="Max results to return (default: 20)"),
                    },
                    required=["repo"],
                ),
            ),
            gtypes.FunctionDeclaration(
                name="github_search_issues",
                description="Search GitHub issues and PRs using a search query string.",
                parameters=gtypes.Schema(
                    type=gtypes.Type.OBJECT,
                    properties={
                        "query": gtypes.Schema(type=gtypes.Type.STRING, description="GitHub search query, e.g. 'label:bug repo:owner/repo'"),
                        "limit": gtypes.Schema(type=gtypes.Type.INTEGER, description="Max results (default: 20)"),
                    },
                    required=["query"],
                ),
            ),
            gtypes.FunctionDeclaration(
                name="github_create_issue",
                description="Create a new issue in a GitHub repository.",
                parameters=gtypes.Schema(
                    type=gtypes.Type.OBJECT,
                    properties={
                        "repo": gtypes.Schema(type=gtypes.Type.STRING, description="owner/repo"),
                        "title": gtypes.Schema(type=gtypes.Type.STRING, description="Issue title"),
                        "body": gtypes.Schema(type=gtypes.Type.STRING, description="Issue body/description"),
                    },
                    required=["repo", "title"],
                ),
            ),
            gtypes.FunctionDeclaration(
                name="github_add_comment",
                description="Add a comment to an existing GitHub issue or PR.",
                parameters=gtypes.Schema(
                    type=gtypes.Type.OBJECT,
                    properties={
                        "repo": gtypes.Schema(type=gtypes.Type.STRING, description="owner/repo"),
                        "number": gtypes.Schema(type=gtypes.Type.INTEGER, description="Issue or PR number"),
                        "body": gtypes.Schema(type=gtypes.Type.STRING, description="Comment text"),
                    },
                    required=["repo", "number", "body"],
                ),
            ),
            gtypes.FunctionDeclaration(
                name="github_search_code",
                description="Search for files or code content inside GitHub repositories. Use this to find YAML templates, config files, scripts, or any file by name or content.",
                parameters=gtypes.Schema(
                    type=gtypes.Type.OBJECT,
                    properties={
                        "query": gtypes.Schema(type=gtypes.Type.STRING, description="Search query, e.g. 'windows yaml', 'filename:windows.yaml', 'extension:yaml windows'"),
                        "limit": gtypes.Schema(type=gtypes.Type.INTEGER, description="Max results (default: 10)"),
                    },
                    required=["query"],
                ),
            ),
            gtypes.FunctionDeclaration(
                name="github_get_file",
                description="Get the full content of a file from a GitHub repository by its path.",
                parameters=gtypes.Schema(
                    type=gtypes.Type.OBJECT,
                    properties={
                        "repo": gtypes.Schema(type=gtypes.Type.STRING, description="owner/repo"),
                        "path": gtypes.Schema(type=gtypes.Type.STRING, description="File path in the repo, e.g. 'ci/windows.yaml'"),
                    },
                    required=["repo", "path"],
                ),
            ),
            # ── Jira ─────────────────────────────────────────────────────────
            gtypes.FunctionDeclaration(
                name="jira_get_issue",
                description="Fetch a single Jira issue by its key, e.g. PROJ-123.",
                parameters=gtypes.Schema(
                    type=gtypes.Type.OBJECT,
                    properties={
                        "issue_key": gtypes.Schema(type=gtypes.Type.STRING, description="Jira issue key, e.g. PROJ-123"),
                    },
                    required=["issue_key"],
                ),
            ),
            gtypes.FunctionDeclaration(
                name="jira_search_issues",
                description="Search Jira issues using a JQL query string.",
                parameters=gtypes.Schema(
                    type=gtypes.Type.OBJECT,
                    properties={
                        "jql": gtypes.Schema(type=gtypes.Type.STRING, description="JQL query, e.g. 'project=PROJ AND status=Open'"),
                        "limit": gtypes.Schema(type=gtypes.Type.INTEGER, description="Max results (default: 20)"),
                    },
                    required=["jql"],
                ),
            ),
            gtypes.FunctionDeclaration(
                name="jira_create_issue",
                description="Create a new Jira issue in a project.",
                parameters=gtypes.Schema(
                    type=gtypes.Type.OBJECT,
                    properties={
                        "project": gtypes.Schema(type=gtypes.Type.STRING, description="Jira project key, e.g. PROJ"),
                        "summary": gtypes.Schema(type=gtypes.Type.STRING, description="Issue summary/title"),
                        "description": gtypes.Schema(type=gtypes.Type.STRING, description="Issue description"),
                        "issue_type": gtypes.Schema(type=gtypes.Type.STRING, description="Issue type: Task, Bug, Story, etc. (default: Task)"),
                    },
                    required=["project", "summary"],
                ),
            ),
            gtypes.FunctionDeclaration(
                name="jira_update_issue",
                description="Update fields of an existing Jira issue.",
                parameters=gtypes.Schema(
                    type=gtypes.Type.OBJECT,
                    properties={
                        "issue_key": gtypes.Schema(type=gtypes.Type.STRING, description="Jira issue key, e.g. PROJ-123"),
                        "summary": gtypes.Schema(type=gtypes.Type.STRING, description="New summary"),
                        "description": gtypes.Schema(type=gtypes.Type.STRING, description="New description"),
                        "assignee": gtypes.Schema(type=gtypes.Type.STRING, description="Assignee username"),
                    },
                    required=["issue_key"],
                ),
            ),
            gtypes.FunctionDeclaration(
                name="jira_add_comment",
                description="Add a comment to an existing Jira issue.",
                parameters=gtypes.Schema(
                    type=gtypes.Type.OBJECT,
                    properties={
                        "issue_key": gtypes.Schema(type=gtypes.Type.STRING, description="Jira issue key, e.g. PROJ-123"),
                        "body": gtypes.Schema(type=gtypes.Type.STRING, description="Comment text"),
                    },
                    required=["issue_key", "body"],
                ),
            ),
        ]
    )
]

# ── Anthropic tool schema (for Claude backend) ──────────────────────────────
ANTHROPIC_TOOLS = [
    {"name": "github_get_issue", "description": "Fetch a single GitHub issue or PR by repository and issue number.", "input_schema": {"type": "object", "properties": {"repo": {"type": "string", "description": "owner/repo"}, "number": {"type": "integer", "description": "Issue or PR number"}}, "required": ["repo", "number"]}},
    {"name": "github_list_issues", "description": "List issues for a GitHub repository.", "input_schema": {"type": "object", "properties": {"repo": {"type": "string", "description": "owner/repo"}, "state": {"type": "string", "description": "open, closed, or all (default: open)"}, "limit": {"type": "integer", "description": "Max results (default: 20)"}}, "required": ["repo"]}},
    {"name": "github_search_issues", "description": "Search GitHub issues and PRs using a search query string.", "input_schema": {"type": "object", "properties": {"query": {"type": "string", "description": "GitHub search query"}, "limit": {"type": "integer", "description": "Max results (default: 20)"}}, "required": ["query"]}},
    {"name": "github_create_issue", "description": "Create a new issue in a GitHub repository.", "input_schema": {"type": "object", "properties": {"repo": {"type": "string", "description": "owner/repo"}, "title": {"type": "string", "description": "Issue title"}, "body": {"type": "string", "description": "Issue body"}}, "required": ["repo", "title"]}},
    {"name": "github_add_comment", "description": "Add a comment to an existing GitHub issue or PR.", "input_schema": {"type": "object", "properties": {"repo": {"type": "string", "description": "owner/repo"}, "number": {"type": "integer", "description": "Issue or PR number"}, "body": {"type": "string", "description": "Comment text"}}, "required": ["repo", "number", "body"]}},
    {"name": "github_search_code", "description": "Search for files or code content inside GitHub repositories.", "input_schema": {"type": "object", "properties": {"query": {"type": "string", "description": "Search query, e.g. 'windows yaml'"}, "limit": {"type": "integer", "description": "Max results (default: 10)"}}, "required": ["query"]}},
    {"name": "github_get_file", "description": "Get the full content of a file from a GitHub repository by its path.", "input_schema": {"type": "object", "properties": {"repo": {"type": "string", "description": "owner/repo"}, "path": {"type": "string", "description": "File path in the repo"}}, "required": ["repo", "path"]}},
    {"name": "jira_get_issue", "description": "Fetch a single Jira issue by its key, e.g. PROJ-123.", "input_schema": {"type": "object", "properties": {"issue_key": {"type": "string", "description": "Jira issue key, e.g. PROJ-123"}}, "required": ["issue_key"]}},
    {"name": "jira_search_issues", "description": "Search Jira issues using a JQL query string.", "input_schema": {"type": "object", "properties": {"jql": {"type": "string", "description": "JQL query"}, "limit": {"type": "integer", "description": "Max results (default: 20)"}}, "required": ["jql"]}},
    {"name": "jira_create_issue", "description": "Create a new Jira issue in a project.", "input_schema": {"type": "object", "properties": {"project": {"type": "string", "description": "Jira project key"}, "summary": {"type": "string", "description": "Issue summary"}, "description": {"type": "string", "description": "Issue description"}, "issue_type": {"type": "string", "description": "Task, Bug, Story, etc."}}, "required": ["project", "summary"]}},
    {"name": "jira_update_issue", "description": "Update fields of an existing Jira issue.", "input_schema": {"type": "object", "properties": {"issue_key": {"type": "string", "description": "Jira issue key"}, "summary": {"type": "string"}, "description": {"type": "string"}, "assignee": {"type": "string"}}, "required": ["issue_key"]}},
    {"name": "jira_add_comment", "description": "Add a comment to an existing Jira issue.", "input_schema": {"type": "object", "properties": {"issue_key": {"type": "string", "description": "Jira issue key"}, "body": {"type": "string", "description": "Comment text"}}, "required": ["issue_key", "body"]}},
]
