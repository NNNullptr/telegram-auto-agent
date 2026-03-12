import logging
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler as TGMessageHandler,
    filters,
)

from config import settings
from src.handlers.message_handler import MessageHandler
from src.handlers import admin_handler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, settings.log_level, logging.INFO),
)
logger = logging.getLogger(__name__)


async def post_init(application) -> None:
    handler = application.bot_data["handler"]
    await handler.init()
    logger.info("Bot initialized successfully")


def main() -> None:
    if not settings.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN is not set.")
        return

    handler = MessageHandler()

    app = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .build()
    )
    app.bot_data["handler"] = handler

    # Admin commands
    app.add_handler(CommandHandler("takeover", admin_handler.handle_takeover))
    app.add_handler(CommandHandler("release", admin_handler.handle_release))
    app.add_handler(CommandHandler("reply", admin_handler.handle_manual_reply))

    # User commands
    app.add_handler(CommandHandler("start", handler.handle_start))
    app.add_handler(CommandHandler("export", handler.handle_export))

    # Admin reply handler: when admin replies to a forwarded message in private chat
    # This must be registered BEFORE the general text handler
    if settings.admin_id:
        app.add_handler(TGMessageHandler(
            filters.Chat(settings.admin_id) & filters.TEXT & ~filters.COMMAND & filters.REPLY,
            admin_handler.handle_admin_reply,
        ))

    # General user messages (must be last)
    app.add_handler(TGMessageHandler(filters.TEXT & ~filters.COMMAND, handler.handle_message))

    logger.info("Bot is starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
