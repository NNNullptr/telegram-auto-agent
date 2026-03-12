"""Graph node functions — each takes ChatState and returns partial updates."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from src.graph.state import ChatState

if TYPE_CHECKING:
    from src.agents.chatting import ChattingAgent
    from src.agents.classifier import ClassifierAgent
    from src.agents.consulting import ConsultingAgent
    from src.agents.purchasing import PurchasingAgent
    from src.accounting.base import BaseAccounting

logger = logging.getLogger(__name__)

# In-memory manual-mode registry: chat_id -> True
_manual_mode: dict[int, bool] = {}

MANUAL_KEYWORDS = {"转人工", "人工客服", "人工服务", "找人工", "real person", "human agent"}


def set_manual_mode(chat_id: int, enabled: bool) -> None:
    _manual_mode[chat_id] = enabled


def is_manual_mode(chat_id: int) -> bool:
    return _manual_mode.get(chat_id, False)


# ---------- Node factories ----------
# Each factory returns an async callable(state) -> dict so we can inject dependencies.


def make_check_manual():
    async def check_manual(state: ChatState) -> dict[str, Any]:
        chat_id = state["chat_id"]
        return {"is_manual": is_manual_mode(chat_id)}

    return check_manual


def make_classify_intent(classifier: ClassifierAgent, confidence_threshold: float = 0.6):
    async def classify_intent(state: ChatState) -> dict[str, Any]:
        user_message = state["user_message"]

        # Keyword-based escalation
        msg_lower = user_message.lower()
        for kw in MANUAL_KEYWORDS:
            if kw in msg_lower:
                logger.info(f"Manual keyword detected: '{kw}'")
                return {"intent": "manual", "confidence": 1.0}

        result = await classifier.classify(user_message)
        intent = result.get("intent", "chatting")
        confidence = result.get("confidence", 0.5)

        if confidence < confidence_threshold:
            logger.info(f"Low confidence {confidence:.2f}, escalating to manual")
            return {"intent": "manual", "confidence": confidence}

        return {"intent": intent, "confidence": confidence}

    return classify_intent


def make_handle_consulting(agent: ConsultingAgent):
    async def handle_consulting(state: ChatState) -> dict[str, Any]:
        reply = await agent.handle(state["user_message"], state.get("history"))
        return {"response": reply}

    return handle_consulting


def make_handle_chatting(agent: ChattingAgent):
    async def handle_chatting(state: ChatState) -> dict[str, Any]:
        reply = await agent.handle(state["user_message"], state.get("history"))
        return {"response": reply}

    return handle_chatting


def make_handle_purchasing(agent: PurchasingAgent):
    async def handle_purchasing(state: ChatState) -> dict[str, Any]:
        result = await agent.handle_purchase(state["user_message"], state.get("history"))
        return {
            "response": result["response"],
            "extracted_order": result.get("order"),
            "order_confirmed": result.get("confirmed", False),
        }

    return handle_purchasing


def make_handle_manual(admin_chat_id: int | None = None):
    async def handle_manual(state: ChatState) -> dict[str, Any]:
        chat_id = state["chat_id"]
        set_manual_mode(chat_id, True)
        return {
            "response": (
                "已为您转接人工客服，请稍候...\n"
                "An agent will assist you shortly."
            ),
        }

    return handle_manual


def make_record_transaction(accounting: BaseAccounting):
    from src.storage.models import Transaction

    async def record_transaction(state: ChatState) -> dict[str, Any]:
        order = state.get("extracted_order")
        if not order:
            return {}

        transaction = Transaction(
            chat_id=state["chat_id"],
            product=order.get("product", "unknown"),
            quantity=order.get("quantity", 1),
            unit_price=order.get("unit_price", 0),
            total_amount=order.get("total_amount", 0),
            description=order.get("description", ""),
        )

        record_id = await accounting.record_transaction(transaction)
        if record_id:
            logger.info(f"Transaction recorded: {record_id}")
        return {}

    return record_transaction
