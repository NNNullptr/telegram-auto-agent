import logging
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler as TGMessageHandler,
    filters,
)

from config import settings
from src.handlers.message_handler import MessageHandler
from src.handlers.admin_handler import AdminHandler

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=getattr(logging, settings.log_level, logging.INFO),
)
logger = logging.getLogger(__name__)


async def post_init(application) -> None:
    """Initialize services after bot starts."""
    handler = application.bot_data["handler"]
    await handler.init()
    logger.info("Bot initialized successfully")


def main() -> None:
    if not settings.telegram_bot_token:
        logger.error("TELEGRAM_BOT_TOKEN is not set. Please configure .env file.")
        return

    handler = MessageHandler()
    admin_handler = AdminHandler()

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
    app.add_handler(CommandHandler("reply", admin_handler.handle_reply))

    # User commands
    app.add_handler(CommandHandler("start", handler.handle_start))
    app.add_handler(CommandHandler("export", handler.handle_export))

    # Message handler (must be last)
    app.add_handler(TGMessageHandler(filters.TEXT & ~filters.COMMAND, handler.handle_message))

    # Admin group message forwarding (if admin_chat_id is configured)
    if settings.admin_chat_id:
        app.add_handler(TGMessageHandler(
            filters.Chat(settings.admin_chat_id) & filters.TEXT & ~filters.COMMAND,
            admin_handler.handle_admin_message,
        ))

    logger.info("Bot is starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
