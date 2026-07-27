import json
import os
import re
import warnings
warnings.filterwarnings("ignore", message=".*quota project.*", category=UserWarning)
from perfbot.tool_registry import DISPATCH, TOOL_DECLARATIONS, ANTHROPIC_TOOLS
from perfbot.logger import get_logger

log = get_logger("client")


def _thinking(msg: str):
    print(f"\r\033[K  {msg}", end="", flush=True)


def _clear_thinking():
    print(f"\r\033[K", end="", flush=True)


def _parse_repos() -> list[str]:
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


def _build_system_instruction() -> str:
    repo_list = _parse_repos()
    base = (
        "You are a helpful assistant with access to GitHub and Jira. "
        "Use the provided tools to read, create, update, and search GitHub issues, pull requests, Jira tickets, and repository files. "
        "Always confirm the action you took and summarize the result clearly. "
        "Maintain context across the conversation — if the user refers to something from a previous message (e.g. 'fill the values', 'that file', 'same repo'), use the prior context to fulfill the request. "
        "When the user asks for the content of a file (e.g. 'give me the yaml file', 'show me the template'), "
        "first use github_search_code to find the best matching file, then IMMEDIATELY call github_get_file to fetch and return its full content — do not stop to ask the user which file they want unless the results are completely ambiguous. "
        "\n\nIMPORTANT — You do NOT have the following capabilities. If asked, clearly say so:\n"
        "- No terminal or shell access — cannot run commands\n"
        "- No access to any Kubernetes or OpenShift cluster\n"
        "- No ability to run Podman, Docker, or any container\n"
        "- No network access beyond GitHub and Jira APIs\n"
        "- No ability to execute benchmark-runner or any other program\n"
        "- No ability to deploy, apply, or create any resource on a cluster\n"
        "What you CAN do: read, search, and create content in GitHub and Jira."
    )
    if repo_list:
        formatted = ", ".join(repo_list)
        base += (
            f" When the user does not specify a repository, search only across these configured repos: {formatted}. "
            "Never search outside this list unless the user explicitly names a different repo."
        )
    return base


def _dispatch_tool(fn_name: str, fn_args: dict) -> dict:
    log.debug("tool call: %s(%s)", fn_name, fn_args)
    try:
        result = DISPATCH[fn_name](**fn_args)
        log.debug("tool result: %s", result)
        return result
    except Exception as exc:
        log.exception("tool %s raised an exception", fn_name)
        return {"error": str(exc)}


class GeminiAgent:
    def __init__(self):
        from google import genai
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY is not set")
        self.client = genai.Client(api_key=api_key)
        self.history = []

    def chat(self, user_message: str) -> str:
        from google.genai import types
        self.history.append(types.Content(role="user", parts=[types.Part(text=user_message)]))

        while True:
            _thinking("Thinking...")
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=self.history,
                config=types.GenerateContentConfig(
                    system_instruction=_build_system_instruction(),
                    tools=TOOL_DECLARATIONS,
                ),
            )
            candidate = response.candidates[0].content
            self.history.append(candidate)

            tool_calls = [p for p in candidate.parts if p.function_call]
            if not tool_calls:
                _clear_thinking()
                break

            tool_results = []
            for part in tool_calls:
                fn_name = part.function_call.name
                fn_args = dict(part.function_call.args)
                _thinking(f"Using tool: {fn_name}...")
                result = _dispatch_tool(fn_name, fn_args)
                tool_results.append(types.Part(
                    function_response=types.FunctionResponse(
                        name=fn_name,
                        response={"result": json.dumps(result, default=str)},
                    )
                ))
            self.history.append(types.Content(role="user", parts=tool_results))

        return response.text


class ClaudeAgent:
    def __init__(self):
        import anthropic
        use_vertex = os.environ.get("CLAUDE_CODE_USE_VERTEX", "").lower() in {"1", "true", "yes"}
        if use_vertex:
            project = os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID")
            region = os.environ.get("CLOUD_ML_REGION", "us-east5")
            if not project:
                raise EnvironmentError("ANTHROPIC_VERTEX_PROJECT_ID is not set")
            self.client = anthropic.AnthropicVertex(project_id=project, region=region)
            self.model = "claude-sonnet-4-5"
        else:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise EnvironmentError("ANTHROPIC_API_KEY is not set (or set CLAUDE_CODE_USE_VERTEX=1 for Vertex)")
            self.client = anthropic.Anthropic(api_key=api_key)
            self.model = "claude-sonnet-4-5"
        self.history = []

    def chat(self, user_message: str) -> str:
        self.history.append({"role": "user", "content": user_message})

        while True:
            _thinking("Thinking...")
            response = self.client.messages.create(
                model=self.model,
                max_tokens=8096,
                system=_build_system_instruction(),
                tools=ANTHROPIC_TOOLS,
                messages=self.history,
            )
            # add assistant turn to history
            self.history.append({"role": "assistant", "content": response.content})

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                _clear_thinking()
                break

            tool_results = []
            for block in tool_uses:
                _thinking(f"Using tool: {block.name}...")
                result = _dispatch_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str),
                })
            self.history.append({"role": "user", "content": tool_results})

        # extract final text
        text_blocks = [b.text for b in response.content if hasattr(b, "text")]
        return "\n".join(text_blocks)


def Agent():
    """Factory — returns GeminiAgent or ClaudeAgent based on PERFBOT_MODEL."""
    model = os.environ.get("PERFBOT_MODEL", "gemini").lower()
    if model == "claude":
        log.debug("Using Claude backend")
        return ClaudeAgent()
    log.debug("Using Gemini backend")
    return GeminiAgent()
