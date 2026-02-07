"""
WebSocket audio stream manager.

Accumulates chunked audio data from a WebSocket client, detects silence or
max-duration boundaries, and triggers transcription.  This is a stub
implementation — silence detection uses a simple RMS threshold rather than
a production VAD model.
"""

from __future__ import annotations

import asyncio
import logging
import struct
import time
from dataclasses import dataclass, field
from typing import Callable, Coroutine, Optional

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration defaults
# ---------------------------------------------------------------------------
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_SILENCE_THRESHOLD = 0.01       # RMS below this = silence
DEFAULT_SILENCE_DURATION_S = 1.5       # seconds of silence before flush
DEFAULT_MAX_CHUNK_DURATION_S = 30.0    # force flush after this many seconds


@dataclass
class AudioStreamConfig:
    """Tunable knobs for the stream manager."""

    sample_rate: int = DEFAULT_SAMPLE_RATE
    silence_threshold: float = DEFAULT_SILENCE_THRESHOLD
    silence_duration: float = DEFAULT_SILENCE_DURATION_S
    max_chunk_duration: float = DEFAULT_MAX_CHUNK_DURATION_S


@dataclass
class AudioStreamState:
    """Mutable state for a single audio stream session."""

    buffer: bytearray = field(default_factory=bytearray)
    last_voice_time: float = field(default_factory=time.monotonic)
    stream_start_time: float = field(default_factory=time.monotonic)
    is_active: bool = True
    total_chunks_received: int = 0


# Type alias for the callback invoked when a segment is ready
TranscribeCallback = Callable[[bytes], Coroutine]


class AudioStreamManager:
    """
    Manages a single bidirectional audio stream over WebSocket.

    Usage::

        manager = AudioStreamManager(config, on_segment_ready=my_callback)
        while connected:
            chunk = await ws.receive_bytes()
            result = await manager.feed(chunk)
            if result:
                await ws.send_json(result)
        await manager.close()
    """

    def __init__(
        self,
        config: Optional[AudioStreamConfig] = None,
        on_segment_ready: Optional[TranscribeCallback] = None,
    ):
        self.config = config or AudioStreamConfig()
        self.state = AudioStreamState()
        self._on_segment_ready = on_segment_ready

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def feed(self, chunk: bytes) -> Optional[dict]:
        """
        Feed a raw audio chunk (16-bit PCM, 16 kHz, mono expected).

        Returns a transcription result dict if a segment boundary was
        detected, otherwise None.
        """
        if not self.state.is_active:
            return None

        self.state.buffer.extend(chunk)
        self.state.total_chunks_received += 1

        now = time.monotonic()

        # Check if we should flush
        should_flush = False

        # 1. Max duration exceeded
        elapsed = now - self.state.stream_start_time
        if elapsed >= self.config.max_chunk_duration:
            logger.debug("Max chunk duration reached (%.1fs), flushing", elapsed)
            should_flush = True

        # 2. Silence detection (simple RMS-based)
        if not should_flush and len(chunk) >= 640:  # at least 20ms of audio at 16kHz
            rms = self._compute_rms(chunk)
            if rms < self.config.silence_threshold:
                silence_elapsed = now - self.state.last_voice_time
                if silence_elapsed >= self.config.silence_duration:
                    logger.debug(
                        "Silence detected (%.2fs, rms=%.4f), flushing",
                        silence_elapsed,
                        rms,
                    )
                    should_flush = True
            else:
                self.state.last_voice_time = now

        if should_flush:
            return await self.flush()

        return None

    async def flush(self) -> Optional[dict]:
        """
        Force-flush the current buffer and run transcription.

        Returns transcription result dict or None if buffer is empty.
        """
        if not self.state.buffer:
            return None

        segment_bytes = bytes(self.state.buffer)
        self._reset_buffer()

        if self._on_segment_ready:
            try:
                result = await self._on_segment_ready(segment_bytes)
                return result
            except Exception:
                logger.exception("Transcription callback failed")
                return {"error": "transcription_failed"}

        # Default stub: return metadata without actual transcription
        duration = len(segment_bytes) / (2 * self.config.sample_rate)  # 16-bit mono
        return {
            "type": "transcription",
            "text": "",
            "duration": round(duration, 2),
            "chunks_processed": self.state.total_chunks_received,
            "stub": True,
        }

    async def close(self):
        """Flush remaining audio and mark stream as inactive."""
        result = await self.flush()
        self.state.is_active = False
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _reset_buffer(self):
        """Clear the buffer and reset timing for the next segment."""
        self.state.buffer = bytearray()
        self.state.stream_start_time = time.monotonic()
        self.state.last_voice_time = time.monotonic()

    @staticmethod
    def _compute_rms(pcm_bytes: bytes) -> float:
        """
        Compute Root Mean Square of 16-bit PCM audio bytes.

        Returns a float in [0, 1] range (normalised).
        """
        num_samples = len(pcm_bytes) // 2
        if num_samples == 0:
            return 0.0

        samples = struct.unpack(f"<{num_samples}h", pcm_bytes[: num_samples * 2])
        arr = np.array(samples, dtype=np.float32) / 32768.0
        return float(np.sqrt(np.mean(arr ** 2)))
