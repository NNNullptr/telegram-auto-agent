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
from src.storage.models import Transaction
from src.utils.context_manager import ContextManager
from src.graph.graph import build_graph
from src.graph.nodes import is_manual_mode, set_manual_mode

logger = logging.getLogger(__name__)

# 确认关键词（和 purchasing.py 保持一致）
_CONFIRM_KEYWORDS = {"确认", "是的", "对", "好的", "确定", "yes", "confirm", "ok", "sure", "y"}


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

        # message_id -> user_chat_id 映射，用于 admin Reply 时找到原用户
        self.forwarded_map: dict[int, int] = {}

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

        # ── Manual mode: 转发给 admin ──
        if is_manual_mode(chat_id) and settings.admin_id:
            await self._forward_to_admin(update, chat_id, user_message, context)
            return

        # ── 检查是否是待确认订单的确认消息（绕过 classifier） ──
        history = self.context.get_history(chat_id)
        pending_order = self._check_pending_order(user_message, history)
        if pending_order:
            await self._confirm_order(update, context, chat_id, pending_order)
            return

        # ── 正常流程：invoke LangGraph ──
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

        # 如果自动升级到 manual，通知 admin
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

        self.context.add_message(chat_id, "user", user_message)
        self.context.add_message(chat_id, "assistant", reply)

        await update.message.reply_text(reply)
        logger.info(f"[{chat_id}] Intent: {result.get('intent')} | Replied: {reply[:80]}...")

    def _check_pending_order(
        self, user_message: str, history: list[dict[str, str]]
    ) -> dict | None:
        """检查：上一条 assistant 消息是否包含「确认订单」，且用户回复了确认关键词。"""
        if not history:
            return None
        msg_lower = user_message.strip().lower()
        if not any(kw in msg_lower for kw in _CONFIRM_KEYWORDS):
            return None
        # 从历史中找最后一条包含「确认订单」的 assistant 消息
        for msg in reversed(history):
            if msg.get("role") == "assistant" and "确认订单" in msg.get("content", ""):
                return self._parse_order_from_confirmation(msg["content"])
        return None

    @staticmethod
    def _parse_order_from_confirmation(content: str) -> dict | None:
        """从确认消息文本中解析订单信息。"""
        try:
            order = {}
            for line in content.split("\n"):
                if "商品：" in line:
                    order["product"] = line.split("商品：")[1].strip()
                elif "数量：" in line:
                    order["quantity"] = int(line.split("数量：")[1].strip())
                elif "单价：¥" in line:
                    order["unit_price"] = float(line.split("单价：¥")[1].strip())
                elif "总计：¥" in line:
                    order["total_amount"] = float(line.split("总计：¥")[1].strip())
            if "product" in order and "total_amount" in order:
                order.setdefault("quantity", 1)
                order.setdefault("unit_price", order["total_amount"])
                return order
        except (ValueError, IndexError):
            pass
        return None

    async def _confirm_order(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        order: dict,
    ) -> None:
        """处理订单确认：记录交易 → 通知 admin → 进入 manual 模式。"""
        # 1. 记录交易到数据库
        transaction = Transaction(
            chat_id=chat_id,
            product=order.get("product", "unknown"),
            quantity=order.get("quantity", 1),
            unit_price=order.get("unit_price", 0),
            total_amount=order.get("total_amount", 0),
        )
        record_id = await self.accounting.record_transaction(transaction)
        logger.info(f"[{chat_id}] Transaction recorded: {record_id}")

        # 2. 回复用户
        reply = (
            f"✅ 订单已确认！\n"
            f"📦 {order['product']} x{order.get('quantity', 1)}\n"
            f"💰 总计 ¥{order['total_amount']:.2f}\n"
            f"正在为您转接人工客服确认详情..."
        )
        self.context.add_message(chat_id, "user", update.message.text)
        self.context.add_message(chat_id, "assistant", reply)
        await update.message.reply_text(reply)

        # 3. 通知 admin + 进入 manual 模式
        if settings.admin_id:
            order_text = (
                f"🛒 新订单！\n"
                f"👤 用户 ID：{chat_id}\n"
                f"📦 商品：{order.get('product', '?')}\n"
                f"🔢 数量：{order.get('quantity', '?')}\n"
                f"💰 单价：¥{order.get('unit_price', 0):.2f}\n"
                f"💵 总计：¥{order.get('total_amount', 0):.2f}\n\n"
                f"用户已自动进入人工模式。\n"
                f"用户后续消息会转发给您，直接 Reply 即可回复。\n"
                f"完成后发送 /release {chat_id} 切回 AI。"
            )
            try:
                await context.bot.send_message(
                    chat_id=settings.admin_id, text=order_text
                )
            except Exception as e:
                logger.error(f"Failed to send order to admin: {e}")

        set_manual_mode(chat_id, True)
        await self.db.save_manual_mode(chat_id, True)
        logger.info(f"[{chat_id}] Auto-entered manual mode after order")

    async def _forward_to_admin(
        self,
        update: Update,
        chat_id: int,
        user_message: str,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        """manual 模式下转发用户消息给 admin。

        不使用 forward_message（会被用户隐私设置阻断），
        而是发送纯文本 + 记录 message_id → chat_id 映射。
        """
        text = f"💬 [用户 {chat_id}]\n{user_message}"
        try:
            sent = await context.bot.send_message(
                chat_id=settings.admin_id, text=text
            )
            # 记录映射：admin 收到的消息 ID → 原用户 chat_id
            self.forwarded_map[sent.message_id] = chat_id
            # 保留最近 500 条映射，防止内存泄漏
            if len(self.forwarded_map) > 500:
                oldest_keys = list(self.forwarded_map.keys())[:-500]
                for k in oldest_keys:
                    del self.forwarded_map[k]
        except Exception as e:
            logger.error(f"Failed to forward to admin: {e}")

        self.context.add_message(chat_id, "user", user_message)
        await update.message.reply_text("已收到，正在等待人工回复...")

    async def handle_export(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle /export — 导出订单交易记录为 Excel 文件。"""
        chat_id = update.effective_chat.id

        # 从 transactions 表导出
        transactions = await self.accounting.get_transactions(chat_id)
        if not transactions:
            await update.message.reply_text("暂无交易记录。")
            return

        from io import BytesIO
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "Transactions"

        headers = ["日期", "商品", "数量", "单价", "总计", "备注"]
        for col, h in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=h)
            cell.font = cell.font.copy(bold=True)

        for i, t in enumerate(transactions, 2):
            ws.cell(row=i, column=1, value=t.created_at.strftime("%Y-%m-%d %H:%M"))
            ws.cell(row=i, column=2, value=t.product)
            ws.cell(row=i, column=3, value=t.quantity)
            ws.cell(row=i, column=4, value=t.unit_price)
            ws.cell(row=i, column=5, value=t.total_amount)
            ws.cell(row=i, column=6, value=t.description)

        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            ws.column_dimensions[col[0].column_letter].width = max_len + 2

        output = BytesIO()
        wb.save(output)
        output.seek(0)

        await update.message.reply_document(
            document=output,
            filename=f"transactions_{chat_id}.xlsx",
            caption=f"已导出 {len(transactions)} 条交易记录。",
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
