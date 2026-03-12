from abc import ABC, abstractmethod
from src.storage.models import Transaction


class BaseAccounting(ABC):
    """Abstract base class for accounting backends."""

    @abstractmethod
    async def record_transaction(self, transaction: Transaction) -> str | None:
        """Record a transaction. Returns an ID string or None on failure."""
        ...

    @abstractmethod
    async def get_transactions(self, chat_id: int, limit: int = 50) -> list[Transaction]:
        """Retrieve transactions for a given chat."""
        ...
