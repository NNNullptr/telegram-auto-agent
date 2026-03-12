import logging
from notion_client import AsyncClient
from config import settings
from src.storage.models import Record

logger = logging.getLogger(__name__)


class NotionService:
    """Syncs financial records to a Notion database."""

    def __init__(self):
        self.enabled = settings.notion_enabled
        if self.enabled:
            self.client = AsyncClient(auth=settings.notion_api_key)
            self.database_id = settings.notion_database_id

    async def add_record(self, record: Record) -> str | None:
        if not self.enabled:
            return None

        try:
            response = await self.client.pages.create(
                parent={"database_id": self.database_id},
                properties={
                    "Description": {
                        "title": [{"text": {"content": record.description}}]
                    },
                    "Amount": {"number": record.amount},
                    "Category": {"select": {"name": record.category}},
                    "Type": {"select": {"name": record.entry_type}},
                    "Date": {"date": {"start": record.created_at.isoformat()}},
                },
            )
            page_id = response["id"]
            logger.info(f"Synced record to Notion: {page_id}")
            return page_id
        except Exception as e:
            logger.error(f"Failed to sync to Notion: {e}")
            return None
