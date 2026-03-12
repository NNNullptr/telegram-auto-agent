import json
import logging
from src.agents.base_agent import BaseAgent
from src.llm.base import BaseLLM

logger = logging.getLogger(__name__)


class ClassifierAgent(BaseAgent):
    """Classifies user intent into one of four categories with a confidence score."""

    VALID_INTENTS = {"consulting", "purchasing", "chatting", "manual"}

    def __init__(self, llm: BaseLLM):
        super().__init__(llm, "classifier.txt")

    async def classify(self, user_message: str) -> dict:
        """Classify a message. Returns {"intent": str, "confidence": float}."""
        response = await self.llm.chat_with_system(
            system_prompt=self.system_prompt,
            user_message=user_message,
            temperature=0.1,
        )
        try:
            result = json.loads(response.content)
            intent = result.get("intent", "chatting")
            confidence = float(result.get("confidence", 0.5))
        except (json.JSONDecodeError, AttributeError, ValueError):
            text = response.content.strip().lower()
            intent = "chatting"
            confidence = 0.3
            for valid in self.VALID_INTENTS:
                if valid in text:
                    intent = valid
                    confidence = 0.6
                    break

        if intent not in self.VALID_INTENTS:
            logger.warning(f"Unknown intent '{intent}', falling back to chatting")
            intent = "chatting"

        logger.info(f"Classified as: {intent} (confidence: {confidence:.2f})")
        return {"intent": intent, "confidence": confidence}
