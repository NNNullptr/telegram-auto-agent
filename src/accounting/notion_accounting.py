import logging

from src.accounting.base import BaseAccounting
from src.services.notion_client import NotionService
from src.storage.models import Transaction

logger = logging.getLogger(__name__)


class NotionAccounting(BaseAccounting):
    """Notion-backed accounting implementation."""

    def __init__(self, notion_service: NotionService):
        self.notion = notion_service

    async def record_transaction(self, transaction: Transaction) -> str | None:
        if not self.notion.enabled:
            return None
        try:
            response = await self.notion.client.pages.create(
                parent={"database_id": self.notion.database_id},
                properties={
                    "Product": {
                        "title": [{"text": {"content": transaction.product}}]
                    },
                    "Quantity": {"number": transaction.quantity},
                    "UnitPrice": {"number": transaction.unit_price},
                    "TotalAmount": {"number": transaction.total_amount},
                    "Description": {
                        "rich_text": [{"text": {"content": transaction.description}}]
                    },
                    "Date": {"date": {"start": transaction.created_at.isoformat()}},
                },
            )
            page_id = response["id"]
            logger.info(f"Notion: recorded transaction {page_id}")
            return page_id
        except Exception as e:
            logger.error(f"Notion accounting failed: {e}")
            return None

    async def get_transactions(self, chat_id: int, limit: int = 50) -> list[Transaction]:
        # Notion query by chat_id requires a filter property; not implemented yet
        logger.warning("NotionAccounting.get_transactions not implemented")
        return []
