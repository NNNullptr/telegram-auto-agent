import asyncio
import logging

from src.accounting.base import BaseAccounting
from src.storage.models import Transaction

logger = logging.getLogger(__name__)


class CompositeAccounting(BaseAccounting):
    """Writes to multiple accounting backends in parallel."""

    def __init__(self, backends: list[BaseAccounting]):
        self.backends = backends

    async def record_transaction(self, transaction: Transaction) -> str | None:
        results = await asyncio.gather(
            *[b.record_transaction(transaction) for b in self.backends],
            return_exceptions=True,
        )
        first_id = None
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"Accounting backend {i} failed: {result}")
            elif result and first_id is None:
                first_id = result
        return first_id

    async def get_transactions(self, chat_id: int, limit: int = 50) -> list[Transaction]:
        # Prefer the first backend that returns data (typically SQLite)
        for backend in self.backends:
            transactions = await backend.get_transactions(chat_id, limit)
            if transactions:
                return transactions
        return []
