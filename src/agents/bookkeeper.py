import json
import logging
from dataclasses import dataclass
from src.agents.base_agent import BaseAgent
from src.services.llm_client import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class BookEntry:
    amount: float
    category: str
    description: str
    entry_type: str = "expense"  # expense or income


class BookkeeperAgent(BaseAgent):
    """Extracts structured financial entries from natural language input."""

    def __init__(self, llm_client: LLMClient):
        super().__init__(llm_client, "bookkeeper.txt")

    async def parse_entry(self, user_message: str) -> BookEntry | None:
        response = await self.llm.chat_with_system(
            system_prompt=self.system_prompt,
            user_message=user_message,
            temperature=0.1,
        )
        try:
            data = json.loads(response)
            return BookEntry(
                amount=float(data["amount"]),
                category=data.get("category", "other"),
                description=data.get("description", user_message),
                entry_type=data.get("type", "expense"),
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.error(f"Failed to parse book entry: {e}, raw: {response}")
            return None

    async def handle(
        self,
        user_message: str,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        entry = await self.parse_entry(user_message)
        if entry is None:
            return "Sorry, I couldn't parse the financial entry. Please try again, e.g. '午饭 30 元'."

        # Store to database (will be called by message handler)
        # Return confirmation message
        type_label = "income" if entry.entry_type == "income" else "expense"
        return (
            f"Recorded {type_label}: {entry.description}\n"
            f"Amount: ¥{entry.amount:.2f}\n"
            f"Category: {entry.category}"
        )
