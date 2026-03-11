from src.agents.base_agent import BaseAgent
from src.services.llm_client import LLMClient


class CustomerServiceAgent(BaseAgent):
    """Handles general Q&A and customer service inquiries."""

    def __init__(self, llm_client: LLMClient):
        super().__init__(llm_client, "customer_service.txt")
