from __future__ import annotations

from typing import Literal, TypedDict


class ChatState(TypedDict, total=False):
    """State schema for the conversation graph."""

    # Routing
    chat_id: int
    user_message: str
    history: list[dict[str, str]]

    # Classification
    intent: Literal["consulting", "purchasing", "chatting", "manual"] | None
    confidence: float

    # Manual mode
    is_manual: bool

    # Response
    response: str

    # Purchasing flow
    extracted_order: dict | None
    order_confirmed: bool
