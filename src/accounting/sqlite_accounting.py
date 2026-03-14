import logging
from datetime import datetime

import aiosqlite

from src.accounting.base import BaseAccounting
from src.storage.database import Database
from src.storage.models import Transaction

logger = logging.getLogger(__name__)


class SQLiteAccounting(BaseAccounting):
    """SQLite-backed accounting implementation."""

    def __init__(self, db: Database):
        self.db = db

    async def record_transaction(self, transaction: Transaction) -> str | None:
        try:
            async with aiosqlite.connect(self.db.db_path) as conn:
                # [修改] INSERT 新增 customer_name 列，记录下单客户名称
                cursor = await conn.execute(
                    """
                    INSERT INTO transactions
                        (chat_id, product, quantity, unit_price, total_amount,
                         customer_name, description, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        transaction.chat_id,
                        transaction.product,
                        transaction.quantity,
                        transaction.unit_price,
                        transaction.total_amount,
                        transaction.customer_name,
                        transaction.description,
                        transaction.created_at.isoformat(),
                    ),
                )
                await conn.commit()
                logger.info(f"SQLite: recorded transaction #{cursor.lastrowid}")
                return str(cursor.lastrowid)
        except Exception as e:
            logger.error(f"SQLite accounting failed: {e}")
            return None

    async def get_transactions(self, chat_id: int, limit: int = 50) -> list[Transaction]:
        try:
            async with aiosqlite.connect(self.db.db_path) as conn:
                conn.row_factory = aiosqlite.Row
                cursor = await conn.execute(
                    "SELECT * FROM transactions WHERE chat_id = ? ORDER BY created_at DESC LIMIT ?",
                    (chat_id, limit),
                )
                rows = await cursor.fetchall()
                return [self._row_to_transaction(row) for row in rows]
        except Exception as e:
            logger.error(f"SQLite get_transactions failed: {e}")
            return []

    # [新增] 导出全部客户的交易记录，供 /exportall 使用
    async def get_all_transactions(self, limit: int = 500) -> list[Transaction]:
        """获取所有客户的交易记录（不区分 chat_id）。"""
        try:
            async with aiosqlite.connect(self.db.db_path) as conn:
                conn.row_factory = aiosqlite.Row
                cursor = await conn.execute(
                    "SELECT * FROM transactions ORDER BY created_at DESC LIMIT ?",
                    (limit,),
                )
                rows = await cursor.fetchall()
                return [self._row_to_transaction(row) for row in rows]
        except Exception as e:
            logger.error(f"SQLite get_all_transactions failed: {e}")
            return []

    @staticmethod
    def _row_to_transaction(row) -> Transaction:
        """[新增] 统一的行转 Transaction 工具方法，含 customer_name 字段。"""
        return Transaction(
            id=row["id"],
            chat_id=row["chat_id"],
            product=row["product"],
            quantity=row["quantity"],
            unit_price=row["unit_price"],
            total_amount=row["total_amount"],
            # customer_name 列可能在旧数据库中不存在，兼容处理
            customer_name=row["customer_name"] if "customer_name" in row.keys() else "",
            description=row["description"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
