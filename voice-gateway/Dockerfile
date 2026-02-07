FROM python:3.12-slim

# ---- System dependencies ----
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

# ---- Working directory ----
WORKDIR /app

# ---- Python dependencies ----
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Optional: install piper-tts (uncomment if TTS is required at build time)
# RUN pip install --no-cache-dir piper-tts

# ---- Application code ----
COPY gateway/ gateway/

# ---- Environment defaults ----
ENV WHISPER_MODEL=base \
    WHISPER_DEVICE=cpu \
    WHISPER_COMPUTE_TYPE=int8 \
    PIPER_VOICE=en_US-lessac-medium \
    PIPER_DATA_DIR=/app/piper-data

# ---- Piper model cache (mount or bake in) ----
RUN mkdir -p /app/piper-data

# ---- Expose port ----
EXPOSE 8000

# ---- Health check ----
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# ---- Start the service ----
CMD ["uvicorn", "gateway.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
