import os


class GeminiBackend:
    def __init__(self):
        from google import genai
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY is not set")
        self.client = genai.Client(api_key=api_key)

    def complete(self, system: str, user: str) -> str:
        from google.genai import types
        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=user,
            config=types.GenerateContentConfig(system_instruction=system),
        )
        return response.text


class ClaudeBackend:
    def __init__(self):
        import anthropic
        use_vertex = os.environ.get("CLAUDE_CODE_USE_VERTEX", "").lower() in {"1", "true", "yes"}
        if use_vertex:
            project = os.environ.get("ANTHROPIC_VERTEX_PROJECT_ID")
            region = os.environ.get("CLOUD_ML_REGION", "us-east5")
            self.client = anthropic.AnthropicVertex(project_id=project, region=region)
        else:
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                raise EnvironmentError("ANTHROPIC_API_KEY is not set")
            self.client = anthropic.Anthropic(api_key=api_key)
        self.model = "claude-sonnet-4-5"

    def complete(self, system: str, user: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response.content[0].text


def get_backend(model: str = None):
    model = model or os.environ.get("PERFBOT_MODEL", "gemini").lower()
    if model == "claude":
        return ClaudeBackend()
    return GeminiBackend()
