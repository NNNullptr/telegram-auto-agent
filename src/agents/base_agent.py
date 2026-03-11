import logging
from pathlib import Path
from src.services.llm_client import LLMClient

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


class BaseAgent:
    """Base class for all agents. Loads a prompt template and delegates to LLM."""

    def __init__(self, llm_client: LLMClient, prompt_file: str):
        self.llm = llm_client
        self.system_prompt = self._load_prompt(prompt_file)

    def _load_prompt(self, filename: str) -> str:
        path = PROMPTS_DIR / filename
        try:
            return path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            logger.warning(f"Prompt file not found: {path}, using empty prompt")
            return ""

    async def handle(
        self,
        user_message: str,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        return await self.llm.chat_with_system(
            system_prompt=self.system_prompt,
            user_message=user_message,
            history=history,
        )
