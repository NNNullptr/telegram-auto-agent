from src.agents.base_agent import BaseAgent
from src.llm.base import BaseLLM


class ChattingAgent(BaseAgent):
    """Handles casual conversation and greetings."""

    def __init__(self, llm: BaseLLM):
        super().__init__(llm, "chatting.txt")
