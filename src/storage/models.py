from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Record:
    chat_id: int
    amount: float
    category: str
    description: str
    entry_type: str  # "expense" or "income"
    created_at: datetime = field(default_factory=datetime.now)
    id: int | None = None
