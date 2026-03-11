import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

from src.agents.classifier import ClassifierAgent
from src.agents.customer_service import CustomerServiceAgent
from src.agents.bookkeeper import BookkeeperAgent
from src.services.llm_client import LLMClient
from src.services.notion_client import NotionService
from src.services.excel_exporter import ExcelExporter
from src.storage.database import Database
from src.storage.models import Record
from src.utils.context_manager import ContextManager

logger = logging.getLogger(__name__)


class MessageHandler:
    """Central message dispatcher: classify intent → route to agent → respond."""

    def __init__(self):
        self.llm = LLMClient()
        self.classifier = ClassifierAgent(self.llm)
        self.customer_service = CustomerServiceAgent(self.llm)
        self.bookkeeper = BookkeeperAgent(self.llm)
        self.context = ContextManager()
        self.db = Database()
        self.notion = NotionService()
        self.excel_exporter = ExcelExporter()

    async def init(self) -> None:
        await self.db.init()

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.message.text:
            return

        chat_id = update.effective_chat.id
        user_message = update.message.text.strip()
        logger.info(f"[{chat_id}] Received: {user_message}")

        # Classify intent
        intent = await self.classifier.classify(user_message)
        history = self.context.get_history(chat_id)

        if intent == ClassifierAgent.INTENT_BOOKKEEPING:
            reply = await self._handle_bookkeeping(chat_id, user_message)
        else:
            reply = await self.customer_service.handle(user_message, history)

        # Update context
        self.context.add_message(chat_id, "user", user_message)
        self.context.add_message(chat_id, "assistant", reply)

        await update.message.reply_text(reply)
        logger.info(f"[{chat_id}] Replied: {reply[:100]}...")

    async def _handle_bookkeeping(self, chat_id: int, user_message: str) -> str:
        entry = await self.bookkeeper.parse_entry(user_message)
        if entry is None:
            return "Sorry, I couldn't parse the entry. Try something like '午饭 30 元'."

        record = Record(
            chat_id=chat_id,
            amount=entry.amount,
            category=entry.category,
            description=entry.description,
            entry_type=entry.entry_type,
            created_at=datetime.now(),
        )

        # Save to SQLite
        record_id = await self.db.insert_record(record)
        logger.info(f"Saved record #{record_id} for chat {chat_id}")

        # Sync to Notion (non-blocking, log errors only)
        await self.notion.add_record(record)

        type_label = "收入" if entry.entry_type == "income" else "支出"
        return (
            f"✅ 已记录{type_label}\n"
            f"📝 {entry.description}\n"
            f"💰 ¥{entry.amount:.2f}\n"
            f"📂 {entry.category}"
        )

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
            "• 💬 General Q&A - just type your question\n"
            "• 📒 Quick bookkeeping - e.g. '午饭 30 元'\n"
            "• 📊 Export records - use /export\n\n"
            "Try it now!"
        )
