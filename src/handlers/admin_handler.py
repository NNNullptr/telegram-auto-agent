"""Admin takeover handler — /takeover, /release, /reply commands."""

import logging
from telegram import Update
from telegram.ext import ContextTypes

from config import settings
from src.graph.nodes import is_manual_mode, set_manual_mode

logger = logging.getLogger(__name__)


class AdminHandler:
    """Handles admin commands for manual takeover of user conversations."""

    def _is_admin(self, user_id: int) -> bool:
        return user_id in settings.admin_user_ids

    async def handle_takeover(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Admin command: /takeover <chat_id>"""
        user_id = update.effective_user.id
        if not self._is_admin(user_id):
            await update.message.reply_text("Unauthorized.")
            return

        args = context.args
        if not args:
            await update.message.reply_text("Usage: /takeover <chat_id>")
            return

        try:
            target_chat_id = int(args[0])
        except ValueError:
            await update.message.reply_text("Invalid chat_id.")
            return

        set_manual_mode(target_chat_id, True)
        await update.message.reply_text(f"Takeover activated for chat {target_chat_id}.")

        # Notify the user
        try:
            await context.bot.send_message(
                chat_id=target_chat_id,
                text="您好！人工客服已上线，请继续描述您的问题。",
            )
        except Exception as e:
            logger.error(f"Failed to notify user {target_chat_id}: {e}")

    async def handle_release(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Admin command: /release <chat_id>"""
        user_id = update.effective_user.id
        if not self._is_admin(user_id):
            await update.message.reply_text("Unauthorized.")
            return

        args = context.args
        if not args:
            await update.message.reply_text("Usage: /release <chat_id>")
            return

        try:
            target_chat_id = int(args[0])
        except ValueError:
            await update.message.reply_text("Invalid chat_id.")
            return

        set_manual_mode(target_chat_id, False)
        await update.message.reply_text(f"Released chat {target_chat_id} back to AI mode.")

        try:
            await context.bot.send_message(
                chat_id=target_chat_id,
                text="人工客服已结束，AI 助手继续为您服务！",
            )
        except Exception as e:
            logger.error(f"Failed to notify user {target_chat_id}: {e}")

    async def handle_reply(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Admin command: /reply <chat_id> <message>"""
        user_id = update.effective_user.id
        if not self._is_admin(user_id):
            await update.message.reply_text("Unauthorized.")
            return

        args = context.args
        if not args or len(args) < 2:
            await update.message.reply_text("Usage: /reply <chat_id> <message>")
            return

        try:
            target_chat_id = int(args[0])
        except ValueError:
            await update.message.reply_text("Invalid chat_id.")
            return

        message_text = " ".join(args[1:])

        try:
            await context.bot.send_message(chat_id=target_chat_id, text=message_text)
            await update.message.reply_text(f"Message sent to {target_chat_id}.")
        except Exception as e:
            logger.error(f"Failed to send reply to {target_chat_id}: {e}")
            await update.message.reply_text(f"Failed to send: {e}")

    async def handle_admin_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle messages in the admin group — forward to manual-mode users.

        This is for messages sent directly in the admin chat (not via /reply).
        Only processes replies to forwarded user messages.
        """
        if not update.message or not update.message.reply_to_message:
            return

        user_id = update.effective_user.id
        if not self._is_admin(user_id):
            return

        # Try to extract the target chat_id from the replied-to message
        original = update.message.reply_to_message.text or ""
        if not original.startswith("[User "):
            return

        try:
            chat_id_str = original.split("]")[0].replace("[User ", "")
            target_chat_id = int(chat_id_str)
        except (ValueError, IndexError):
            return

        try:
            await context.bot.send_message(
                chat_id=target_chat_id,
                text=update.message.text,
            )
        except Exception as e:
            logger.error(f"Failed to forward admin reply to {target_chat_id}: {e}")
