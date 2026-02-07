"""Telegram bot entry point for Prometheus Jarvis."""

from __future__ import annotations

import logging
import os
import sys

from dotenv import load_dotenv
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

from bot.bridge import close_client
from bot.handlers import (
    handle_text,
    handle_voice,
    help_command,
    skills_command,
    start_command,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Build the Application, register handlers, and start polling."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN environment variable is not set.")
        sys.exit(1)

    logger.info("Starting Jarvis Telegram bot...")

    application = ApplicationBuilder().token(token).build()

    # ── Command handlers ──────────────────────────────────
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("skills", skills_command))

    # ── Message handlers ──────────────────────────────────
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text)
    )
    application.add_handler(
        MessageHandler(filters.VOICE, handle_voice)
    )

    # ── Shutdown hook ─────────────────────────────────────
    async def post_shutdown(app) -> None:
        """Clean up the shared httpx client when the bot stops."""
        await close_client()

    application.post_shutdown = post_shutdown

    # ── Start polling ─────────────────────────────────────
    logger.info("Bot is polling for updates...")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
