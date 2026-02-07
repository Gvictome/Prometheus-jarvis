"""
Speech-to-Text module using faster-whisper (CTranslate2) with fallback to openai-whisper.

Lazy-loads the whisper model on first use. Supports .ogg, .wav, .mp3, .m4a input
formats by converting to 16 kHz mono float32 via ffmpeg subprocess.
"""

from __future__ import annotations

import asyncio
import logging
import os
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "base")
WHISPER_DEVICE: str = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE: str = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

SUPPORTED_FORMATS = {".ogg", ".wav", ".mp3", ".m4a", ".webm", ".flac", ".opus"}

# ---------------------------------------------------------------------------
# Lazy model singleton
# ---------------------------------------------------------------------------
_model = None
_backend: Optional[str] = None  # "faster-whisper" | "openai-whisper"


def _load_model():
    """Load the whisper model once. Prefers faster-whisper, falls back to openai-whisper."""
    global _model, _backend

    if _model is not None:
        return _model

    # Try faster-whisper first (CTranslate2-based, much faster on CPU)
    try:
        from faster_whisper import WhisperModel

        logger.info(
            "Loading faster-whisper model=%s device=%s compute_type=%s",
            WHISPER_MODEL,
            WHISPER_DEVICE,
            WHISPER_COMPUTE_TYPE,
        )
        _model = WhisperModel(
            WHISPER_MODEL,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
        )
        _backend = "faster-whisper"
        logger.info("faster-whisper model loaded successfully")
        return _model
    except ImportError:
        logger.warning("faster-whisper not installed, trying openai-whisper fallback")

    # Fallback to openai-whisper
    try:
        import whisper

        logger.info("Loading openai-whisper model=%s", WHISPER_MODEL)
        _model = whisper.load_model(WHISPER_MODEL)
        _backend = "openai-whisper"
        logger.info("openai-whisper model loaded successfully")
        return _model
    except ImportError:
        raise RuntimeError(
            "Neither faster-whisper nor openai-whisper is installed. "
            "Install one of them: pip install faster-whisper  OR  pip install openai-whisper"
        )


def get_backend() -> Optional[str]:
    """Return the name of the loaded backend, or None if not loaded yet."""
    return _backend


# ---------------------------------------------------------------------------
# Audio conversion via ffmpeg
# ---------------------------------------------------------------------------
def _ffmpeg_to_f32_mono_16k(input_path: str | Path) -> np.ndarray:
    """
    Convert any supported audio file to a 16 kHz mono float32 numpy array
    using ffmpeg as a subprocess.

    Returns:
        numpy array of shape (num_samples,) with dtype float32, values in [-1, 1].
    """
    cmd = [
        "ffmpeg",
        "-i", str(input_path),
        "-f", "s16le",        # raw PCM signed 16-bit little-endian
        "-acodec", "pcm_s16le",
        "-ar", "16000",        # 16 kHz sample rate
        "-ac", "1",            # mono
        "-loglevel", "error",
        "pipe:1",              # output to stdout
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "ffmpeg not found. Install it: apt-get install ffmpeg  OR  brew install ffmpeg"
        )
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"ffmpeg conversion failed: {exc.stderr.decode()}")

    raw_bytes = result.stdout
    if len(raw_bytes) == 0:
        raise ValueError("ffmpeg produced no output — input file may be empty or corrupt")

    # Convert s16le bytes -> float32 numpy array normalised to [-1, 1]
    num_samples = len(raw_bytes) // 2
    samples = struct.unpack(f"<{num_samples}h", raw_bytes)
    audio = np.array(samples, dtype=np.float32) / 32768.0
    return audio


def _audio_duration_seconds(audio: np.ndarray, sample_rate: int = 16000) -> float:
    """Return the duration of the audio array in seconds."""
    return round(len(audio) / sample_rate, 2)


# ---------------------------------------------------------------------------
# Transcription helpers
# ---------------------------------------------------------------------------
def _transcribe_with_faster_whisper(model, audio: np.ndarray) -> dict:
    """Run transcription using the faster-whisper backend."""
    segments, info = model.transcribe(
        audio,
        beam_size=5,
        language=None,  # auto-detect
        vad_filter=True,
    )
    text_parts = [segment.text for segment in segments]
    text = " ".join(text_parts).strip()
    return {
        "text": text,
        "language": info.language or "en",
        "duration": round(info.duration, 2),
    }


def _transcribe_with_openai_whisper(model, audio: np.ndarray) -> dict:
    """Run transcription using the openai-whisper backend."""
    import whisper

    # openai-whisper expects a float32 tensor-like or numpy array
    result = model.transcribe(
        audio,
        fp16=False,  # CPU-safe
    )
    return {
        "text": result.get("text", "").strip(),
        "language": result.get("language", "en"),
        "duration": _audio_duration_seconds(audio),
    }


def _transcribe_array(audio: np.ndarray) -> dict:
    """Transcribe a float32 numpy array using whichever backend is loaded."""
    model = _load_model()

    if _backend == "faster-whisper":
        return _transcribe_with_faster_whisper(model, audio)
    else:
        return _transcribe_with_openai_whisper(model, audio)


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------
async def transcribe_file(file_path: Path) -> dict:
    """
    Transcribe an audio file on disk.

    Args:
        file_path: Path to an audio file (.ogg, .wav, .mp3, .m4a, etc.)

    Returns:
        dict with keys: text (str), language (str), duration (float seconds)
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Audio file not found: {file_path}")

    suffix = file_path.suffix.lower()
    if suffix not in SUPPORTED_FORMATS:
        raise ValueError(
            f"Unsupported audio format '{suffix}'. Supported: {SUPPORTED_FORMATS}"
        )

    loop = asyncio.get_event_loop()

    # Convert to 16 kHz mono float32 (runs ffmpeg in a thread to avoid blocking)
    audio = await loop.run_in_executor(None, _ffmpeg_to_f32_mono_16k, file_path)

    # Transcribe (also CPU-bound, run in executor)
    result = await loop.run_in_executor(None, _transcribe_array, audio)

    # If the backend didn't set a duration, compute from audio length
    if result.get("duration") is None or result["duration"] == 0:
        result["duration"] = _audio_duration_seconds(audio)

    return result


async def transcribe_bytes(audio_bytes: bytes, format: str = "ogg") -> dict:
    """
    Transcribe raw audio bytes.

    Writes the bytes to a temporary file with the appropriate extension,
    then delegates to transcribe_file.

    Args:
        audio_bytes: Raw audio content.
        format: File extension without dot (e.g. "ogg", "wav", "mp3", "m4a").

    Returns:
        dict with keys: text (str), language (str), duration (float seconds)
    """
    ext = format if format.startswith(".") else f".{format}"
    if ext not in SUPPORTED_FORMATS:
        raise ValueError(
            f"Unsupported audio format '{ext}'. Supported: {SUPPORTED_FORMATS}"
        )

    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = Path(tmp.name)

    try:
        return await transcribe_file(tmp_path)
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass
