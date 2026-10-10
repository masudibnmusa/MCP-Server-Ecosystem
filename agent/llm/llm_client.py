"""Claude API with native tool use."""
from anthropic import AsyncAnthropic

from security.secrets_manager import get_secret


class LLMClient:
    def __init__(self, model: str, max_tokens: int = 4096):
        self.model = model
        self.max_tokens = max_tokens
        self.client = AsyncAnthropic(api_key=get_secret("ANTHROPIC_API_KEY", required=True))

    async def complete(self, system: str, messages: list[dict], tools: list[dict] | None = None):
        """One model turn, possibly containing tool_use blocks. Tools must stay defined whenever
        the history contains tool_use/tool_result blocks, so the agent always passes them."""
        kwargs = dict(model=self.model, max_tokens=self.max_tokens, system=system, messages=messages)
        if tools:
            kwargs["tools"] = tools
        return await self.client.messages.create(**kwargs)

    async def complete_text(self, system: str, prompt: str, max_tokens: int = 1500) -> str:
        """Plain text call with no tools (used by the planner)."""
        resp = await self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in resp.content if b.type == "text")