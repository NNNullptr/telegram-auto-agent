"""Admin takeover handler — simplified Reply-based forwarding.

Flow:
  1. User messages in manual mode are forwarded to ADMIN_ID
  2. Admin replies (Reply) to the forwarded message → bot sends reply back to user
  3. /takeover <chat_id> — manually activate manual mode
  4. /release <chat_id> — deactivate manual mode, switch back to AI
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
    """Admin replies to a forwarded message → bot sends the reply to the original user.

    This works because in manual mode we use `forward_message` to forward the user's
    message to admin. When admin uses Telegram's Reply feature on that forwarded
    message, `reply_to_message.forward_origin` contains the original sender info.
    """
    msg = update.message
    if not msg or not msg.reply_to_message:
        return
    if not _is_admin(update.effective_user.id):
        return

    replied_to = msg.reply_to_message

    # Extract the original user's chat_id from the forwarded message
    target_chat_id = None

    # python-telegram-bot v20+: forward_origin (Bot API 7.0+)
    if hasattr(replied_to, "forward_origin") and replied_to.forward_origin:
        origin = replied_to.forward_origin
        # MessageOriginUser has a .sender_user
        if hasattr(origin, "sender_user") and origin.sender_user:
            target_chat_id = origin.sender_user.id
    # Fallback: legacy forward_from field
    elif replied_to.forward_from:
        target_chat_id = replied_to.forward_from.id

    if not target_chat_id:
        await msg.reply_text("⚠️ 无法识别原始用户，请用 /reply <chat_id> <消息> 手动回复。")
        return

    try:
        await context.bot.send_message(chat_id=target_chat_id, text=msg.text)
        await msg.reply_text(f"✅ 已发送给用户 {target_chat_id}")
    except Exception as e:
        logger.error(f"Failed to reply to user {target_chat_id}: {e}")
        await msg.reply_text(f"❌ 发送失败：{e}")


async def handle_manual_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/reply <chat_id> <message> — fallback when Reply doesn't work."""
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
