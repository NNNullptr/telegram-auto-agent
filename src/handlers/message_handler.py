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
from src.graph.nodes import is_manual_mode, set_manual_mode

logger = logging.getLogger(__name__)


class MessageHandler:
    """Central message dispatcher: uses LangGraph state machine for routing."""

    def __init__(self):
        llm = LLMFactory.create()

        self.classifier = ClassifierAgent(llm)
        self.consulting = ConsultingAgent(llm)
        self.chatting = ChattingAgent(llm)
        self.purchasing = PurchasingAgent(llm)

        self.db = Database()
        self.notion = NotionService()
        self.excel_exporter = ExcelExporter()
        self.context = ContextManager()
        self.accounting = self._build_accounting()

        self.graph = build_graph(
            classifier=self.classifier,
            consulting_agent=self.consulting,
            chatting_agent=self.chatting,
            purchasing_agent=self.purchasing,
            accounting=self.accounting,
            admin_chat_id=settings.admin_id or None,
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

        # ── Manual mode: forward original message to admin (so admin can Reply) ──
        if is_manual_mode(chat_id) and settings.admin_id:
            try:
                await update.message.forward(chat_id=settings.admin_id)
            except Exception as e:
                logger.error(f"Failed to forward to admin: {e}")
            await update.message.reply_text("已收到，正在等待人工回复...")
            self.context.add_message(chat_id, "user", user_message)
            return

        # ── Normal mode: invoke LangGraph ──
        history = self.context.get_history(chat_id)
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

        # ── If auto-escalated to manual, notify admin ──
        if result.get("intent") == "manual" and settings.admin_id:
            try:
                await context.bot.send_message(
                    chat_id=settings.admin_id,
                    text=(
                        f"🔔 用户 {chat_id} 请求人工帮助\n"
                        f"消息：{user_message}\n"
                        f"使用 /takeover {chat_id} 接管\n"
                        f"使用 /release {chat_id} 释放"
                    ),
                )
            except Exception as e:
                logger.error(f"Failed to notify admin: {e}")

        # ── Order confirmed → send details to admin + enter manual mode ──
        order = result.get("extracted_order")
        if order and result.get("order_confirmed"):
            await self._notify_order_and_enter_manual(chat_id, order, context)

        self.context.add_message(chat_id, "user", user_message)
        self.context.add_message(chat_id, "assistant", reply)

        await update.message.reply_text(reply)
        logger.info(f"[{chat_id}] Intent: {result.get('intent')} | Replied: {reply[:80]}...")

    async def _notify_order_and_enter_manual(
        self, chat_id: int, order: dict, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Send order details to admin and switch the user to manual mode."""
        if not settings.admin_id:
            return

        order_text = (
            f"🛒 新订单！\n"
            f"👤 用户：{chat_id}\n"
            f"📦 商品：{order.get('product', '?')}\n"
            f"🔢 数量：{order.get('quantity', '?')}\n"
            f"💰 单价：¥{order.get('unit_price', 0):.2f}\n"
            f"💵 总计：¥{order.get('total_amount', 0):.2f}\n\n"
            f"该用户已自动进入人工模式。\n"
            f"用户后续消息会转发给您，直接回复(Reply)即可。\n"
            f"完成后使用 /release {chat_id} 切回 AI。"
        )

        try:
            await context.bot.send_message(chat_id=settings.admin_id, text=order_text)
        except Exception as e:
            logger.error(f"Failed to send order to admin: {e}")

        # Auto-enter manual mode
        set_manual_mode(chat_id, True)
        await self.db.save_manual_mode(chat_id, True)
        logger.info(f"[{chat_id}] Auto-entered manual mode after order confirmation")

    async def handle_export(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        await update.message.reply_text(
            "👋 Welcome!\n\n"
            "• 💬 咨询商品 — 直接提问\n"
            "• 🛒 购买下单 — 说「我要买...」\n"
            "• 💬 闲聊 — 随便聊\n"
            "• 👨‍💼 转人工 — 说「转人工」\n"
            "• 📊 导出账单 — /export"
        )
