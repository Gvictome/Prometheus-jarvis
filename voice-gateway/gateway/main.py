"""
Voice Gateway — FastAPI application.

Endpoints:
    POST /api/transcribe   - Upload audio file, get transcription
    POST /api/synthesize    - Send text, get WAV audio back
    GET  /health            - Service health check
    WS   /ws/voice          - Real-time audio streaming (stub)
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from gateway import stt, tts
from gateway.stream import AudioStreamManager, AudioStreamConfig

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Prometheus Jarvis — Voice Gateway",
    version="0.1.0",
    description="Speech-to-text and text-to-speech gateway service.",
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------
class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000, description="Text to synthesize")
    voice: str = Field(default="default", description="Voice identifier")


class TranscriptionResponse(BaseModel):
    text: str
    language: str
    duration: float


# ---------------------------------------------------------------------------
# POST /api/transcribe
# ---------------------------------------------------------------------------
@app.post("/api/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(file: UploadFile = File(...)):
    """
    Accept a multipart audio file upload and return the transcription.

    Supported formats: .ogg, .wav, .mp3, .m4a, .webm, .flac, .opus
    """
    # Determine file extension from the uploaded filename
    original_name = file.filename or "audio.ogg"
    suffix = Path(original_name).suffix.lower() or ".ogg"

    audio_bytes = await file.read()

    if len(audio_bytes) == 0:
        return JSONResponse(
            status_code=400,
            content={"detail": "Uploaded file is empty"},
        )

    logger.info(
        "Transcribe request: filename=%s size=%d bytes format=%s",
        original_name,
        len(audio_bytes),
        suffix,
    )

    try:
        result = await stt.transcribe_bytes(audio_bytes, format=suffix)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"detail": str(exc)})
    except RuntimeError as exc:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    return TranscriptionResponse(
        text=result["text"],
        language=result["language"],
        duration=result["duration"],
    )


# ---------------------------------------------------------------------------
# POST /api/synthesize
# ---------------------------------------------------------------------------
@app.post("/api/synthesize")
async def synthesize_speech(request: SynthesizeRequest):
    """
    Accept a JSON body with text and voice, return WAV audio.
    """
    voice = request.voice
    if voice == "default":
        voice = tts.DEFAULT_VOICE

    logger.info(
        "Synthesize request: text_length=%d voice=%s",
        len(request.text),
        voice,
    )

    wav_bytes = await tts.synthesize(text=request.text, voice=voice)

    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={
            "Content-Disposition": 'attachment; filename="speech.wav"',
        },
    )


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------
@app.get("/health")
async def health_check():
    """Return service health status."""
    return {
        "status": "ok",
        "whisper_model": stt.WHISPER_MODEL,
        "tts_available": tts.is_available(),
    }


# ---------------------------------------------------------------------------
# WebSocket /ws/voice  (real-time streaming stub)
# ---------------------------------------------------------------------------
@app.websocket("/ws/voice")
async def websocket_voice(ws: WebSocket):
    """
    WebSocket endpoint for real-time voice streaming.

    Protocol (stub):
        Client sends: binary audio chunks (16-bit PCM, 16 kHz, mono)
        Server sends: JSON messages with transcription results

    This is a minimal stub — it accumulates chunks and triggers
    transcription when silence is detected or max duration is reached.
    """
    await ws.accept()
    logger.info("WebSocket voice session opened")

    async def _transcribe_segment(pcm_bytes: bytes) -> dict:
        """Callback: transcribe a completed audio segment."""
        try:
            result = await stt.transcribe_bytes(pcm_bytes, format="wav")
            return {
                "type": "transcription",
                "text": result["text"],
                "language": result["language"],
                "duration": result["duration"],
            }
        except Exception as exc:
            logger.exception("WebSocket transcription failed")
            return {"type": "error", "message": str(exc)}

    manager = AudioStreamManager(
        config=AudioStreamConfig(),
        on_segment_ready=_transcribe_segment,
    )

    try:
        while True:
            data = await ws.receive_bytes()
            result = await manager.feed(data)
            if result:
                await ws.send_json(result)
    except WebSocketDisconnect:
        logger.info("WebSocket voice session closed by client")
    except Exception:
        logger.exception("WebSocket voice session error")
    finally:
        # Flush any remaining audio
        final = await manager.close()
        if final:
            try:
                await ws.send_json(final)
            except Exception:
                pass
