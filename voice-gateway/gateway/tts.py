"""
Text-to-Speech module using Piper TTS.

Lazy-loads the piper model on first use. Falls back gracefully if piper
is not installed, returning a helpful error message.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import struct
import wave
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEFAULT_VOICE: str = os.getenv("PIPER_VOICE", "en_US-lessac-medium")
PIPER_DATA_DIR: str = os.getenv("PIPER_DATA_DIR", "/app/piper-data")

# ---------------------------------------------------------------------------
# Lazy model singleton
# ---------------------------------------------------------------------------
_piper_voice = None
_piper_available: Optional[bool] = None


def is_available() -> bool:
    """Check whether piper-tts is importable."""
    global _piper_available
    if _piper_available is None:
        try:
            import piper  # noqa: F401
            _piper_available = True
        except ImportError:
            _piper_available = False
    return _piper_available


def _load_piper(voice: str = DEFAULT_VOICE):
    """Load the piper voice model. Called once on first synthesis request."""
    global _piper_voice

    if _piper_voice is not None:
        return _piper_voice

    if not is_available():
        raise RuntimeError("piper-tts is not installed")

    from piper import PiperVoice

    model_path = os.path.join(PIPER_DATA_DIR, f"{voice}.onnx")
    config_path = f"{model_path}.json"

    if os.path.isfile(model_path):
        logger.info("Loading Piper voice from %s", model_path)
        _piper_voice = PiperVoice.load(model_path, config_path=config_path)
    else:
        # Attempt to let piper download the model automatically
        logger.info("Loading Piper voice by name: %s (may download)", voice)
        _piper_voice = PiperVoice.load(voice)

    logger.info("Piper voice loaded successfully")
    return _piper_voice


def _generate_unavailable_wav(message: str = "TTS not available") -> bytes:
    """
    Generate a minimal valid WAV file containing silence.
    This is returned when piper is not installed so callers still get
    a valid audio response they can handle.
    """
    sample_rate = 22050
    duration_s = 0.5
    num_samples = int(sample_rate * duration_s)

    # Silent PCM samples (16-bit signed, little-endian)
    silence = struct.pack(f"<{num_samples}h", *([0] * num_samples))

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(silence)

    return buf.getvalue()


def _synthesize_with_piper(text: str, voice: str) -> bytes:
    """Synthesize text to WAV bytes using the Piper engine."""
    piper_voice = _load_piper(voice)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(piper_voice.config.sample_rate)

        piper_voice.synthesize(text, wf)

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------
async def synthesize(text: str, voice: str = DEFAULT_VOICE) -> bytes:
    """
    Synthesize text into WAV audio bytes.

    Args:
        text:  The text to speak.
        voice: Piper voice name (e.g. "en_US-lessac-medium").

    Returns:
        bytes containing a complete WAV file.

    If piper-tts is not installed, returns a short silent WAV and logs a
    warning instead of raising an exception.
    """
    if not text or not text.strip():
        logger.warning("Empty text passed to synthesize, returning silence")
        return _generate_unavailable_wav()

    if not is_available():
        logger.warning(
            "piper-tts is not installed — returning silent WAV placeholder. "
            "Install it with: pip install piper-tts"
        )
        return _generate_unavailable_wav("TTS not available")

    loop = asyncio.get_event_loop()
    try:
        wav_bytes = await loop.run_in_executor(
            None, _synthesize_with_piper, text, voice
        )
        return wav_bytes
    except Exception:
        logger.exception("TTS synthesis failed, returning silent WAV")
        return _generate_unavailable_wav()
