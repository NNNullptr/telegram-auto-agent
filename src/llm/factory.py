import logging
from config import settings
from src.llm.base import BaseLLM

logger = logging.getLogger(__name__)


class LLMFactory:
    """Factory for creating LLM instances based on configuration."""

    @staticmethod
    def create(provider: str | None = None) -> BaseLLM:
        provider = provider or settings.llm_provider

        match provider:
            case "openai":
                from src.llm.openai_llm import OpenAILLM
                return OpenAILLM(
                    api_key=settings.llm_api_key,
                    base_url=settings.llm_base_url,
                    model=settings.llm_model_name,
                )
            case "claude":
                from src.llm.claude_llm import ClaudeLLM
                return ClaudeLLM(
                    api_key=settings.llm_api_key,
                    model=settings.llm_model_name,
                )
            case "deepseek":
                from src.llm.deepseek_llm import DeepSeekLLM
                return DeepSeekLLM(
                    api_key=settings.llm_api_key,
                    base_url=settings.llm_base_url,
                    model=settings.llm_model_name,
                )
            case _:
                logger.warning(f"Unknown LLM provider '{provider}', falling back to openai")
                from src.llm.openai_llm import OpenAILLM
                return OpenAILLM(
                    api_key=settings.llm_api_key,
                    base_url=settings.llm_base_url,
                    model=settings.llm_model_name,
                )
