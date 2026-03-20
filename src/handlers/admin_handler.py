"""Admin takeover handler — simplified Reply-based forwarding.

Flow:
  1. 订单确认后 → 用户自动进入 manual 模式
  2. manual 模式下用户消息以文本方式发给 admin（格式：💬 [用户 xxx]\n消息）
  3. admin 直接 Reply 这条消息 → bot 根据 forwarded_map 找到原用户并回传
  4. /takeover <chat_id> — 手动接管
  5. /release <chat_id> — 释放，切回 AI
  6. /reply <chat_id> <消息> — 手动回复（Reply 不可用时的备选）

[修复] release 时同步清空对话历史 + pending_orders + 持久化 manual mode，
       避免旧订单上下文污染后续 AI 对话（第二次交易幻觉的根因）。
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from config import settings
from src.graph.nodes import set_manual_mode

logger = logging.getLogger(__name__)


def _get_handler(context: ContextTypes.DEFAULT_TYPE):
    """从 bot_data 获取 MessageHandler 实例（可能为 None）。"""
    return context.application.bot_data.get("handler")


def _is_admin(user_id: int) -> bool:
    return user_id == settings.admin_id


async def handle_takeover(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/takeover <chat_id>"""
    if not _is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("用法：/takeover <chat_id>")
        return

    try:
        target = int(context.args[0])
    except ValueError:
        await update.message.reply_text("chat_id 无效")
        return

    set_manual_mode(target, True)
    # [修复] 持久化 manual mode 到数据库，防止 bot 重启后状态丢失
    handler = _get_handler(context)
    if handler:
        await handler.db.save_manual_mode(target, True)

    await update.message.reply_text(f"✅ 已接管用户 {target}，用户消息会转发给你。")

    try:
        await context.bot.send_message(chat_id=target, text="您好，人工客服已上线！")
    except Exception as e:
        logger.error(f"Failed to notify user {target}: {e}")


async def handle_release(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/release <chat_id>"""
    if not _is_admin(update.effective_user.id):
        return

    if not context.args:
        await update.message.reply_text("用法：/release <chat_id>")
        return

    try:
        target = int(context.args[0])
    except ValueError:
        await update.message.reply_text("chat_id 无效")
        return

    set_manual_mode(target, False)

    # ── [修复] 释放时清理所有残留状态，防止旧上下文污染 AI 新对话 ──
    handler = _get_handler(context)
    if handler:
        # 1. 清空对话历史：这是第二次交易幻觉的根因
        #    旧历史中包含第一次订单的完整对话（商品名、价格、确认、客户名等），
        #    LLM 在处理新消息时会混淆新旧订单数据
        handler.context.clear(target)
        # 2. 清除可能残留的待确认订单（内存 + DB）
        handler.context.clear_pending_order(target)
        await handler.db.delete_pending_order(target)
        # 3. 持久化 manual mode = False 到数据库
        #    原实现只改了内存，bot 重启后用户会被误恢复为 manual 模式
        await handler.db.save_manual_mode(target, False)

    await update.message.reply_text(f"✅ 已释放用户 {target}，切回 AI 模式。")

    try:
        await context.bot.send_message(chat_id=target, text="人工客服已结束，AI 助手继续为您服务！")
    except Exception as e:
        logger.error(f"Failed to notify user {target}: {e}")


async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin Reply 被转发的消息 → bot 发回给原用户。

    使用 MessageHandler.forwarded_map 查找 reply_to_message.message_id → user chat_id。
    """
    msg = update.message
    if not msg or not msg.reply_to_message or not msg.text:
        return
    if not _is_admin(update.effective_user.id):
        return

    replied_to = msg.reply_to_message
    replied_id = replied_to.message_id

    # 从 forwarded_map 查找原用户
    handler = _get_handler(context)
    if not handler:
        return

    target_chat_id = handler.forwarded_map.get(replied_id)

    # Fallback: 尝试从消息文本 "💬 [用户 xxx]" 中解析
    if not target_chat_id and replied_to.text:
        target_chat_id = _parse_chat_id_from_text(replied_to.text)

    if not target_chat_id:
        await msg.reply_text("⚠️ 无法识别原用户。请用 /reply <chat_id> <消息> 手动回复。")
        return

    try:
        await context.bot.send_message(chat_id=target_chat_id, text=msg.text)
        # [修复] admin 回复也写入上下文，保持对话历史对称
        handler.context.add_message(target_chat_id, "assistant", msg.text)
        await msg.reply_text(f"✅ 已发送给用户 {target_chat_id}")
    except Exception as e:
        logger.error(f"Failed to reply to user {target_chat_id}: {e}")
        await msg.reply_text(f"❌ 发送失败：{e}")


def _parse_chat_id_from_text(text: str) -> int | None:
    """从 '💬 [用户 123456]\nxxx' 格式中提取 chat_id。"""
    try:
        if "[用户 " in text:
            part = text.split("[用户 ")[1].split("]")[0]
            return int(part)
    except (IndexError, ValueError):
        pass
    return None


async def handle_manual_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/reply <chat_id> <message> — Reply 不可用时的手动备选。"""
    if not _is_admin(update.effective_user.id):
        return

    args = context.args
    if not args or len(args) < 2:
        await update.message.reply_text("用法：/reply <chat_id> <消息>")
        return

    try:
        target = int(args[0])
    except ValueError:
        await update.message.reply_text("chat_id 无效")
        return

    text = " ".join(args[1:])
    try:
        await context.bot.send_message(chat_id=target, text=text)
        # [修复] 手动回复也同步写入上下文，与 handle_admin_reply 保持一致
        handler = _get_handler(context)
        if handler:
            handler.context.add_message(target, "assistant", text)
        await update.message.reply_text(f"✅ 已发送给 {target}")
    except Exception as e:
        await update.message.reply_text(f"❌ 发送失败：{e}")
