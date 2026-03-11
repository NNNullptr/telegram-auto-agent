from dataclasses import dataclass, field
from datetime import datetime

from pydantic import BaseModel, Field as PydanticField


@dataclass
class Record:
    """Legacy bookkeeping record (kept for backward compatibility)."""

    chat_id: int
    amount: float
    category: str
    description: str
    entry_type: str  # "expense" or "income"
    created_at: datetime = field(default_factory=datetime.now)
    id: int | None = None


class Transaction(BaseModel):
    """Purchase transaction model for the new accounting system."""

    chat_id: int
    product: str
    quantity: int = 1
    unit_price: float = 0.0
    total_amount: float = 0.0
    description: str = ""
    created_at: datetime = PydanticField(default_factory=datetime.now)
    id: int | None = None
