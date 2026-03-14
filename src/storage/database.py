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
