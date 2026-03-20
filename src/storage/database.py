import json
import logging
from datetime import datetime
from pathlib import Path

import aiosqlite

from src.storage.models import Record

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "records.db"


class Database:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DB_PATH

    async def init(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            # Legacy records table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    amount REAL NOT NULL,
                    category TEXT NOT NULL,
                    description TEXT NOT NULL,
                    entry_type TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            # New transactions table for purchase flow
            # [修改] 新增 customer_name 列：存储下单客户的名称
            await db.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    product TEXT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 1,
                    unit_price REAL NOT NULL DEFAULT 0,
                    total_amount REAL NOT NULL DEFAULT 0,
                    customer_name TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
            """)
            # Chat states for manual mode persistence
            await db.execute("""
                CREATE TABLE IF NOT EXISTS chat_states (
                    chat_id INTEGER PRIMARY KEY,
                    is_manual INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                )
            """)
            # [新增] pending_orders 表：持久化用户待确认订单，bot 重启后可恢复
            # chat_id: 用户会话 ID（主键，每用户最多一条待确认订单）
            # order_json: 订单字典序列化为 JSON 字符串
            # created_at: 订单创建时间，用于过期清理
            await db.execute("""
                CREATE TABLE IF NOT EXISTS pending_orders (
                    chat_id INTEGER PRIMARY KEY,
                    order_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
            # [新增] 兼容旧数据库：如果 transactions 表已存在但缺少 customer_name 列，自动添加
            try:
                await db.execute(
                    "ALTER TABLE transactions ADD COLUMN customer_name TEXT NOT NULL DEFAULT ''"
                )
            except Exception:
                pass  # 列已存在则忽略

            await db.commit()
        logger.info(f"Database initialized at {self.db_path}")

    async def insert_record(self, record: Record) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO records (chat_id, amount, category, description, entry_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    record.chat_id,
                    record.amount,
                    record.category,
                    record.description,
                    record.entry_type,
                    record.created_at.isoformat(),
                ),
            )
            await db.commit()
            return cursor.lastrowid

    async def get_records(
        self,
        chat_id: int,
        limit: int = 50,
    ) -> list[Record]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM records WHERE chat_id = ? ORDER BY created_at DESC LIMIT ?",
                (chat_id, limit),
            )
            rows = await cursor.fetchall()
            return [
                Record(
                    id=row["id"],
                    chat_id=row["chat_id"],
                    amount=row["amount"],
                    category=row["category"],
                    description=row["description"],
                    entry_type=row["entry_type"],
                    created_at=datetime.fromisoformat(row["created_at"]),
                )
                for row in rows
            ]

    # --- Manual mode persistence ---

    async def load_manual_modes(self) -> dict[int, bool]:
        """Load manual mode states from DB (called on startup)."""
        result = {}
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    "SELECT chat_id, is_manual FROM chat_states WHERE is_manual = 1"
                )
                rows = await cursor.fetchall()
                for row in rows:
                    result[row["chat_id"]] = True
        except Exception as e:
            logger.error(f"Failed to load manual modes: {e}")
        return result

    # --- Pending order persistence ---

    async def save_pending_order(self, chat_id: int, order: dict) -> None:
        """将待确认订单序列化后写入数据库，bot 重启后可恢复。

        使用 INSERT OR REPLACE（ON CONFLICT）保证每个用户只保留最新一条待确认订单。
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    INSERT INTO pending_orders (chat_id, order_json, created_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(chat_id) DO UPDATE SET
                        order_json = excluded.order_json,
                        created_at = excluded.created_at
                    """,
                    (chat_id, json.dumps(order, ensure_ascii=False), datetime.now().isoformat()),
                )
                await db.commit()
        except Exception as e:
            logger.error(f"Failed to save pending order for {chat_id}: {e}")

    async def load_pending_orders(self) -> dict[int, tuple[dict, str]]:
        """启动时从数据库恢复所有待确认订单。

        返回 {chat_id: (order_dict, created_at_iso)}，
        调用方需根据 created_at 计算剩余 TTL，避免过期订单被错误复活。
        """
        result: dict[int, tuple[dict, str]] = {}
        try:
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    "SELECT chat_id, order_json, created_at FROM pending_orders"
                )
                rows = await cursor.fetchall()
                for row in rows:
                    try:
                        result[row["chat_id"]] = (
                            json.loads(row["order_json"]),
                            row["created_at"],
                        )
                    except json.JSONDecodeError as e:
                        logger.warning(f"Skipping corrupt pending order for {row['chat_id']}: {e}")
        except Exception as e:
            logger.error(f"Failed to load pending orders: {e}")
        return result

    async def delete_pending_order(self, chat_id: int) -> None:
        """订单确认或取消后，从数据库删除对应待确认记录。"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("DELETE FROM pending_orders WHERE chat_id = ?", (chat_id,))
                await db.commit()
        except Exception as e:
            logger.error(f"Failed to delete pending order for {chat_id}: {e}")

    async def save_manual_mode(self, chat_id: int, is_manual: bool) -> None:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    INSERT INTO chat_states (chat_id, is_manual, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(chat_id) DO UPDATE SET
                        is_manual = excluded.is_manual,
                        updated_at = excluded.updated_at
                    """,
                    (chat_id, int(is_manual), datetime.now().isoformat()),
                )
                await db.commit()
        except Exception as e:
            logger.error(f"Failed to save manual mode for {chat_id}: {e}")
