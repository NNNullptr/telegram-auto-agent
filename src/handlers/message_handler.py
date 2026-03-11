import logging
from telegram import Update
from telegram.ext import ContextTypes

from config import settings
from src.agents.classifier import ClassifierAgent
from src.agents.consulting import ConsultingAgent
from src.agents.chatting import ChattingAgent
from src.agents.purchasing import PurchasingAgent
from src.llm import LLMFactory
from src.accounting.sqlite_accounting import SQLiteAccounting
from src.accounting.notion_accounting import NotionAccounting
from src.accounting.excel_accounting import ExcelAccounting
from src.accounting.composite import CompositeAccounting
from src.services.notion_client import NotionService
from src.services.excel_exporter import ExcelExporter
from src.storage.database import Database
from src.utils.context_manager import ContextManager
from src.graph.graph import build_graph
from src.graph.nodes import is_manual_mode

logger = logging.getLogger(__name__)


class MessageHandler:
    """Central message dispatcher: uses LangGraph state machine for routing."""

    def __init__(self):
        # LLM
        llm = LLMFactory.create()

        # Agents
        self.classifier = ClassifierAgent(llm)
        self.consulting = ConsultingAgent(llm)
        self.chatting = ChattingAgent(llm)
        self.purchasing = PurchasingAgent(llm)

        # Storage & services
        self.db = Database()
        self.notion = NotionService()
        self.excel_exporter = ExcelExporter()
        self.context = ContextManager()

        # Accounting (composite)
        self.accounting = self._build_accounting()

        # Graph
        self.graph = build_graph(
            classifier=self.classifier,
            consulting_agent=self.consulting,
            chatting_agent=self.chatting,
            purchasing_agent=self.purchasing,
            accounting=self.accounting,
            admin_chat_id=settings.admin_chat_id or None,
            confidence_threshold=settings.confidence_threshold,
        )

    def _build_accounting(self) -> CompositeAccounting:
        backends = []
        enabled = [b.strip() for b in settings.accounting_backends.split(",")]
        if "sqlite" in enabled:
            backends.append(SQLiteAccounting(self.db))
        if "notion" in enabled:
            backends.append(NotionAccounting(self.notion))
        if "excel" in enabled:
            backends.append(ExcelAccounting())
        if not backends:
            backends.append(SQLiteAccounting(self.db))
        return CompositeAccounting(backends)

    async def init(self) -> None:
        await self.db.init()
        # Restore manual modes from DB
        from src.graph.nodes import set_manual_mode
        modes = await self.db.load_manual_modes()
        for chat_id, enabled in modes.items():
            set_manual_mode(chat_id, enabled)
        if modes:
            logger.info(f"Restored {len(modes)} manual mode sessions")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.message.text:
            return

        chat_id = update.effective_chat.id
        user_message = update.message.text.strip()
        logger.info(f"[{chat_id}] Received: {user_message}")

        # If in manual mode, forward to admin
        if is_manual_mode(chat_id) and settings.admin_chat_id:
            try:
                await context.bot.send_message(
                    chat_id=settings.admin_chat_id,
                    text=f"[User {chat_id}] {user_message}",
                )
            except Exception as e:
                logger.error(f"Failed to forward to admin: {e}")
            await update.message.reply_text("已收到，正在等待人工客服回复...")
            self.context.add_message(chat_id, "user", user_message)
            return

        history = self.context.get_history(chat_id)

        # Invoke the LangGraph state machine
        state = {
            "chat_id": chat_id,
            "user_message": user_message,
            "history": history,
            "is_manual": False,
            "intent": None,
            "confidence": 0.0,
            "response": "",
            "extracted_order": None,
            "order_confirmed": False,
        }

        result = await self.graph.ainvoke(state)
        reply = result.get("response", "Sorry, something went wrong.")

        # If auto-escalated to manual, notify admin
        if result.get("intent") == "manual" and settings.admin_chat_id:
            try:
                await context.bot.send_message(
                    chat_id=settings.admin_chat_id,
                    text=(
                        f"🔔 User {chat_id} needs manual assistance.\n"
                        f"Message: {user_message}\n"
                        f"Use /takeover {chat_id} to begin."
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to notify admin: {e}")

        # Update context
        self.context.add_message(chat_id, "user", user_message)
        self.context.add_message(chat_id, "assistant", reply)

        await update.message.reply_text(reply)
        logger.info(f"[{chat_id}] Intent: {result.get('intent')} | Replied: {reply[:80]}...")

    async def handle_export(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /export command: export records as Excel file."""
        chat_id = update.effective_chat.id
        records = await self.db.get_records(chat_id)

        if not records:
            await update.message.reply_text("No records found.")
            return

        excel_file = self.excel_exporter.export(records)
        await update.message.reply_document(
            document=excel_file,
            filename=f"records_{chat_id}.xlsx",
            caption=f"Exported {len(records)} records.",
        )

    async def handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /start command."""
        await update.message.reply_text(
            "👋 Welcome to Telegram Auto Agent!\n\n"
            "I can help you with:\n"
            "• 💬 Product consulting - ask about products & pricing\n"
            "• 🛒 Quick purchasing - say 'I want to buy...'\n"
            "• 💬 Casual chat - just say hi!\n"
            "• 📊 Export records - use /export\n"
            "• 👨‍💼 Human agent - say '转人工'\n\n"
            "Try it now!"
        )
