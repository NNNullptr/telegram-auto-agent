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
