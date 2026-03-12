"""Build and compile the LangGraph conversation graph."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langgraph.graph import END, StateGraph

from src.graph.nodes import (
    make_check_manual,
    make_classify_intent,
    make_handle_chatting,
    make_handle_consulting,
    make_handle_manual,
    make_handle_purchasing,
    make_record_transaction,
)
from src.graph.state import ChatState

if TYPE_CHECKING:
    from src.accounting.base import BaseAccounting
    from src.agents.chatting import ChattingAgent
    from src.agents.classifier import ClassifierAgent
    from src.agents.consulting import ConsultingAgent
    from src.agents.purchasing import PurchasingAgent

logger = logging.getLogger(__name__)


def _route_after_manual_check(state: ChatState) -> str:
    if state.get("is_manual"):
        return "handle_manual"
    return "classify_intent"


def _route_by_intent(state: ChatState) -> str:
    intent = state.get("intent", "chatting")
    return {
        "consulting": "handle_consulting",
        "purchasing": "handle_purchasing",
        "chatting": "handle_chatting",
        "manual": "handle_manual",
    }.get(intent, "handle_chatting")


def _route_after_purchasing(state: ChatState) -> str:
    if state.get("extracted_order") and state.get("order_confirmed"):
        return "record_transaction"
    return END


def build_graph(
    classifier: ClassifierAgent,
    consulting_agent: ConsultingAgent,
    chatting_agent: ChattingAgent,
    purchasing_agent: PurchasingAgent,
    accounting: BaseAccounting,
    admin_chat_id: int | None = None,
    confidence_threshold: float = 0.6,
):
    """Build and compile the conversation state graph."""

    builder = StateGraph(ChatState)

    # Add nodes
    builder.add_node("check_manual", make_check_manual())
    builder.add_node("classify_intent", make_classify_intent(classifier, confidence_threshold))
    builder.add_node("handle_consulting", make_handle_consulting(consulting_agent))
    builder.add_node("handle_chatting", make_handle_chatting(chatting_agent))
    builder.add_node("handle_purchasing", make_handle_purchasing(purchasing_agent))
    builder.add_node("handle_manual", make_handle_manual(admin_chat_id))
    builder.add_node("record_transaction", make_record_transaction(accounting))

    # Entry point
    builder.set_entry_point("check_manual")

    # Edges
    builder.add_conditional_edges(
        "check_manual",
        _route_after_manual_check,
        {"handle_manual": "handle_manual", "classify_intent": "classify_intent"},
    )
    builder.add_conditional_edges(
        "classify_intent",
        _route_by_intent,
        {
            "handle_consulting": "handle_consulting",
            "handle_purchasing": "handle_purchasing",
            "handle_chatting": "handle_chatting",
            "handle_manual": "handle_manual",
        },
    )
    builder.add_edge("handle_consulting", END)
    builder.add_edge("handle_chatting", END)
    builder.add_edge("handle_manual", END)
    builder.add_conditional_edges(
        "handle_purchasing",
        _route_after_purchasing,
        {"record_transaction": "record_transaction", END: END},
    )
    builder.add_edge("record_transaction", END)

    graph = builder.compile()
    logger.info("Conversation graph compiled successfully")
    return graph
