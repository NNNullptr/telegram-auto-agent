from src.agents.base_agent import BaseAgent
from src.llm.base import BaseLLM


class ConsultingAgent(BaseAgent):
    """Handles product inquiries, pricing questions, and general consulting."""

    def __init__(self, llm: BaseLLM):
        super().__init__(llm, "consulting.txt")
