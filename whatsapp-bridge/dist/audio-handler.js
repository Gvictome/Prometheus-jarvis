"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.handleAudioMessage = handleAudioMessage;
const baileys_1 = require("@whiskeysockets/baileys");
const axios_1 = __importDefault(require("axios"));
const form_data_1 = __importDefault(require("form-data"));
const pino_1 = __importDefault(require("pino"));
const logger = (0, pino_1.default)({ name: "audio-handler" });
const VOICE_GATEWAY_URL = process.env.VOICE_GATEWAY_URL || "http://voice-gateway:8001";
/**
 * Download a voice message from WhatsApp (.ogg) and POST it to
 * the Voice Gateway for transcription.
 *
 * Returns the transcribed text, or null on failure.
 */
async function handleAudioMessage(sock, msg) {
    try {
        // Download the audio buffer from WhatsApp servers
        logger.info({ msgId: msg.key.id }, "Downloading voice message");
        const buffer = await (0, baileys_1.downloadMediaMessage)(msg, "buffer", {});
        if (!buffer || buffer.length === 0) {
            logger.warn("Downloaded audio buffer is empty");
            return null;
        }
        const audioBuffer = buffer;
        logger.info({ size: audioBuffer.length }, "Voice message downloaded, sending to transcription service");
        // Build multipart form data
        const form = new form_data_1.default();
        form.append("file", audioBuffer, {
            filename: "voice.ogg",
            contentType: "audio/ogg",
        });
        // POST to Voice Gateway transcription endpoint
        const url = `${VOICE_GATEWAY_URL}/api/transcribe`;
        const response = await axios_1.default.post(url, form, {
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
        logger.info({ textLength: transcribedText.length }, "Audio transcription successful");
        return transcribedText;
    }
    catch (err) {
        if (axios_1.default.isAxiosError(err)) {
            logger.error({
                status: err.response?.status,
                data: err.response?.data,
                message: err.message,
            }, "Voice Gateway transcription request failed");
        }
        else {
            logger.error({ err }, "Failed to handle audio message");
        }
        return null;
    }
}
//# sourceMappingURL=audio-handler.js.map