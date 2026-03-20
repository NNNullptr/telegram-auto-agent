import logging

from src.accounting.base import BaseAccounting
from src.services.notion_client import NotionService
from src.storage.models import Transaction

logger = logging.getLogger(__name__)


class NotionAccounting(BaseAccounting):
    """Notion-backed accounting implementation.

    将交易记录同步到 Notion 数据库。要求 Notion 数据库包含以下属性：
    - Product (title): 商品名称
    - Quantity (number): 数量
    - UnitPrice (number): 单价
    - TotalAmount (number): 总金额
    - CustomerName (rich_text): 客户名称
    - ChatId (number): 用户会话 ID
    - Description (rich_text): 备注
    - Date (date): 订单日期

    [修复] 原实现缺少 CustomerName 和 ChatId，导致 Notion 中无法识别客户。
    """

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
                    # [修复] 新增客户名称和会话 ID，与 SQLite 存储字段对齐
                    "CustomerName": {
                        "rich_text": [{"text": {"content": transaction.customer_name or ""}}]
                    },
                    "ChatId": {"number": transaction.chat_id},
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
