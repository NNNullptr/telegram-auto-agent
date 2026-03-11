import logging
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler as TGMessageHandler, filters

from config import settings
from src.handlers.message_handler import MessageHandler

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

    app = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .build()
    )
    app.bot_data["handler"] = handler

    # Register handlers
    app.add_handler(CommandHandler("start", handler.handle_start))
    app.add_handler(CommandHandler("export", handler.handle_export))
    app.add_handler(TGMessageHandler(filters.TEXT & ~filters.COMMAND, handler.handle_message))

    logger.info("Bot is starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
