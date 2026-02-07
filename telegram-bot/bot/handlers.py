"""Telegram command and message handlers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from bot.bridge import fetch_skills, send_message, transcribe_voice

logger = logging.getLogger(__name__)


# ── Command handlers ─────────────────────────────────────────


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start — greet the user."""
    await update.message.reply_text(
        "Hello! I'm Jarvis, your AI assistant.\n\n"
        "Send me a text or voice message and I'll do my best to help.\n"
        "Type /help to see available commands."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help — list available commands."""
    text = (
        "Available commands:\n\n"
        "/start  — Start a conversation with Jarvis\n"
        "/help   — Show this help message\n"
        "/skills — List available AI skills\n\n"
        "You can also send me:\n"
        "  - Text messages — I'll respond as your AI assistant\n"
        "  - Voice messages — I'll transcribe and respond"
    )
    await update.message.reply_text(text)


async def skills_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /skills — fetch and display registered skills from OpenClaw."""
    skills = await fetch_skills()

    if not skills:
        await update.message.reply_text(
            "Could not retrieve skills from the backend. Please try again later."
        )
        return

    lines = ["Available skills:\n"]
    for skill in skills:
        name = skill.get("name", "unknown")
        description = skill.get("description", "No description")
        tier = skill.get("min_tier", 0)
        examples = skill.get("examples", [])

        lines.append(f"  {name} (tier {tier})")
        lines.append(f"    {description}")
        if examples:
            examples_str = ", ".join(f'"{e}"' for e in examples[:3])
            lines.append(f"    Examples: {examples_str}")
        lines.append("")

    await update.message.reply_text("\n".join(lines))


# ── Message handlers ─────────────────────────────────────────


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming text messages — forward to OpenClaw and reply."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    text = update.message.text

    if not text or not text.strip():
        return

    logger.info("Text from %s (chat %s): %s", user.id, chat_id, text[:80])

    reply = await send_message(
        sender_id=str(user.id),
        chat_id=chat_id,
        content=text,
        message_type="text",
    )

    await update.message.reply_text(reply)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle incoming voice messages — transcribe then forward to OpenClaw."""
    user = update.effective_user
    chat_id = update.effective_chat.id

    logger.info("Voice from %s (chat %s)", user.id, chat_id)

    # Download the voice file from Telegram servers
    voice = update.message.voice
    voice_file = await context.bot.get_file(voice.file_id)
    voice_bytes = await voice_file.download_as_bytearray()

    # Transcribe via voice-gateway
    transcribed = await transcribe_voice(bytes(voice_bytes), filename="voice.ogg")

    if not transcribed or not transcribed.strip():
        await update.message.reply_text(
            "Sorry, I could not transcribe that voice message. Please try again."
        )
        return

    logger.info("Transcribed (%s): %s", user.id, transcribed[:80])

    # Forward the transcribed text to OpenClaw
    reply = await send_message(
        sender_id=str(user.id),
        chat_id=chat_id,
        content=transcribed,
        message_type="voice",
    )

    # Prefix the reply with the transcription so the user knows what was heard
    full_reply = f'[Transcription] "{transcribed}"\n\n{reply}'
    await update.message.reply_text(full_reply)
