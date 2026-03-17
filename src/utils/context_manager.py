import time
import logging
from config import settings

logger = logging.getLogger(__name__)


class ContextManager:
    """管理每个 chat_id 的多轮对话历史。

    同时维护每个用户的待确认订单状态（pending_orders），
    订单超过 PENDING_ORDER_TTL 秒后自动过期，避免临时订单堆积内存。
    """

    # 待确认订单的存活时长（秒），超时后 get_pending_order 返回 None 并自动清理
    PENDING_ORDER_TTL: int = 30 * 60  # 30 分钟

    def __init__(
        self,
        max_turns: int | None = None,
        expire_minutes: int | None = None,
    ):
        self.max_turns = max_turns or settings.max_context_turns
        self.expire_minutes = expire_minutes or settings.context_expire_minutes
        # {chat_id: {"messages": [...], "last_active": timestamp}}
        self._sessions: dict[int, dict] = {}
        # 待确认订单状态，内部结构为：
        # {chat_id: {"order": dict, "expires_at": float(unix timestamp)}}
        # 通过公开方法访问，外部仅感知 dict | None
        self._pending_orders: dict[int, dict] = {}

    def get_history(self, chat_id: int) -> list[dict[str, str]]:
        session = self._sessions.get(chat_id)
        if not session:
            return []
        if self._is_expired(session):
            self.clear(chat_id)
            return []
        return list(session["messages"])

    def add_message(self, chat_id: int, role: str, content: str) -> None:
        if chat_id not in self._sessions:
            self._sessions[chat_id] = {"messages": [], "last_active": time.time()}

        session = self._sessions[chat_id]
        session["messages"].append({"role": role, "content": content})
        session["last_active"] = time.time()

        # Keep only the last N turns (each turn = user + assistant = 2 messages)
        max_messages = self.max_turns * 2
        if len(session["messages"]) > max_messages:
            session["messages"] = session["messages"][-max_messages:]

    def clear(self, chat_id: int) -> None:
        self._sessions.pop(chat_id, None)

    def cleanup_expired(self) -> int:
        expired = [
            cid for cid, s in self._sessions.items() if self._is_expired(s)
        ]
        for cid in expired:
            del self._sessions[cid]
        if expired:
            logger.info(f"Cleaned up {len(expired)} expired sessions")
        return len(expired)

    def _is_expired(self, session: dict) -> bool:
        elapsed = time.time() - session["last_active"]
        return elapsed > self.expire_minutes * 60

    def set_pending_order(self, chat_id: int, order: dict) -> None:
        """存入待确认订单，并记录过期时间（当前时间 + PENDING_ORDER_TTL）。"""
        self._pending_orders[chat_id] = {
            "order": order,
            "expires_at": time.time() + self.PENDING_ORDER_TTL,
        }

    def get_pending_order(self, chat_id: int) -> dict | None:
        """获取待确认订单；若已过期则自动清除并返回 None。"""
        entry = self._pending_orders.get(chat_id)
        if not entry:
            return None
        if time.time() > entry["expires_at"]:
            # 订单超时，惰性清理（lazy cleanup），无需定时任务
            self._pending_orders.pop(chat_id, None)
            logger.info(f"[{chat_id}] Pending order expired and auto-cleared")
            return None
        return entry["order"]

    def clear_pending_order(self, chat_id: int) -> None:
        """订单确认或取消时主动清除。"""
        self._pending_orders.pop(chat_id, None)
