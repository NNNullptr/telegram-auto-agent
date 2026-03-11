import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Unified response from any LLM provider."""

    content: str
    tool_calls: list[dict] | None = None
    usage: dict = field(default_factory=dict)


class BaseLLM(ABC):
    """Abstract base class for LLM providers.

    Subclasses must implement `chat()`. The `chat_with_system()` convenience
    method builds a message list and delegates to `chat()`.
    """

    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 1024,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        ...

    async def chat_with_system(
        self,
        system_prompt: str,
        user_message: str,
        history: list[dict[str, str]] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        tools: list[dict] | None = None,
    ) -> LLMResponse:
        messages = [{"role": "system", "content": system_prompt}]
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        return await self.chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
        )
