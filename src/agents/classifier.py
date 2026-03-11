import json
import logging
from src.agents.base_agent import BaseAgent
from src.services.llm_client import LLMClient

logger = logging.getLogger(__name__)


class ClassifierAgent(BaseAgent):
    """Classifies user intent and routes to the appropriate expert agent."""

    INTENT_BOOKKEEPING = "bookkeeping"
    INTENT_CUSTOMER_SERVICE = "customer_service"
    INTENT_UNKNOWN = "unknown"

    VALID_INTENTS = {INTENT_BOOKKEEPING, INTENT_CUSTOMER_SERVICE, INTENT_UNKNOWN}

    def __init__(self, llm_client: LLMClient):
        super().__init__(llm_client, "classifier.txt")

    async def classify(self, user_message: str) -> str:
        response = await self.llm.chat_with_system(
            system_prompt=self.system_prompt,
            user_message=user_message,
            temperature=0.1,
        )
        try:
            result = json.loads(response)
            intent = result.get("intent", self.INTENT_UNKNOWN)
        except (json.JSONDecodeError, AttributeError):
            intent = response.strip().lower()

        if intent not in self.VALID_INTENTS:
            logger.warning(f"Unknown intent '{intent}', falling back to customer_service")
            intent = self.INTENT_CUSTOMER_SERVICE

        logger.info(f"Classified message as: {intent}")
        return intent
