import { WASocket, downloadMediaMessage, proto } from "@whiskeysockets/baileys";
import axios from "axios";
import FormData from "form-data";
import pino from "pino";

const logger = pino({ name: "audio-handler" });

const VOICE_GATEWAY_URL =
  process.env.VOICE_GATEWAY_URL || "http://voice-gateway:8001";

interface TranscribeResponse {
  text: string;
}

/**
 * Download a voice message from WhatsApp (.ogg) and POST it to
 * the Voice Gateway for transcription.
 *
 * Returns the transcribed text, or null on failure.
 */
export async function handleAudioMessage(
  sock: WASocket,
  msg: proto.IWebMessageInfo
): Promise<string | null> {
  try {
    // Download the audio buffer from WhatsApp servers
    logger.info({ msgId: msg.key.id }, "Downloading voice message");

    const buffer = await downloadMediaMessage(
      msg,
      "buffer",
      {}
    );

    if (!buffer || (buffer as Buffer).length === 0) {
      logger.warn("Downloaded audio buffer is empty");
      return null;
    }

    const audioBuffer = buffer as Buffer;
    logger.info(
      { size: audioBuffer.length },
      "Voice message downloaded, sending to transcription service"
    );

    // Build multipart form data
    const form = new FormData();
    form.append("file", audioBuffer, {
      filename: "voice.ogg",
      contentType: "audio/ogg",
    });

    // POST to Voice Gateway transcription endpoint
    const url = `${VOICE_GATEWAY_URL}/api/transcribe`;
    const response = await axios.post<TranscribeResponse>(url, form, {
      headers: {
        ...form.getHeaders(),
      },
      timeout: 60_000, // voice transcription can take a while
      maxContentLength: 50 * 1024 * 1024, // 50 MB
    });

    const transcribedText = response.data?.text?.trim();

    if (!transcribedText) {
      logger.warn("Transcription service returned empty text");
      return null;
    }

    logger.info(
      { textLength: transcribedText.length },
      "Audio transcription successful"
    );

    return transcribedText;
  } catch (err) {
    if (axios.isAxiosError(err)) {
      logger.error(
        {
          status: err.response?.status,
          data: err.response?.data,
          message: err.message,
        },
        "Voice Gateway transcription request failed"
      );
    } else {
      logger.error({ err }, "Failed to handle audio message");
    }

    return null;
  }
}
