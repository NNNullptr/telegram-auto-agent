"""Admin takeover handler — simplified Reply-based forwarding.

Flow:
  1. 订单确认后 → 用户自动进入 manual 模式
  2. manual 模式下用户消息以文本方式发给 admin（格式：💬 [用户 xxx]\n消息）
  3. admin 直接 Reply 这条消息 → bot 根据 forwarded_map 找到原用户并回传
  4. /takeover <chat_id> — 手动接管
  5. /release <chat_id> — 释放，切回 AI
  6. /reply <chat_id> <消息> — 手动回复（Reply 不可用时的备选）
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from config import settings
from src.graph.nodes import set_manual_mode

logger = logging.getLogger(__name__)


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
    handler = context.application.bot_data.get("handler")
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
        await update.message.reply_text(f"✅ 已发送给 {target}")
    except Exception as e:
        await update.message.reply_text(f"❌ 发送失败：{e}")
