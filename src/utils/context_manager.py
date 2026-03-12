import time
import logging
from config import settings

logger = logging.getLogger(__name__)


class ContextManager:
    """Manages multi-turn conversation history per chat_id."""

    def __init__(
        self,
        max_turns: int | None = None,
        expire_minutes: int | None = None,
    ):
        self.max_turns = max_turns or settings.max_context_turns
        self.expire_minutes = expire_minutes or settings.context_expire_minutes
        # {chat_id: {"messages": [...], "last_active": timestamp}}
        self._sessions: dict[int, dict] = {}

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
