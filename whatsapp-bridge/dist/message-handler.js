"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.registerMessageHandler = registerMessageHandler;
const bridge_js_1 = require("./bridge.js");
const audio_handler_js_1 = require("./audio-handler.js");
const pino_1 = __importDefault(require("pino"));
const logger = (0, pino_1.default)({ name: "message-handler" });
/** JID suffix for status broadcast -- these should be filtered out */
const STATUS_BROADCAST = "status@broadcast";
/**
 * Register the incoming-message event handler on the Baileys socket.
 */
function registerMessageHandler(sock) {
    sock.ev.on("messages.upsert", async ({ messages, type }) => {
        // Only process new messages that arrive in real time
        if (type !== "notify")
            return;
        for (const msg of messages) {
            try {
                await processMessage(sock, msg);
            }
            catch (err) {
                logger.error({ err, msgId: msg.key.id }, "Error processing message");
            }
        }
    });
    logger.info("Message handler registered");
}
async function processMessage(sock, msg) {
    const jid = msg.key.remoteJid;
    // Ignore messages without a remote JID
    if (!jid)
        return;
    // Filter out status broadcasts
    if (jid === STATUS_BROADCAST) {
        logger.debug("Ignoring status broadcast message");
        return;
    }
    // Ignore messages sent by us
    if (msg.key.fromMe)
        return;
    const isGroup = jid.endsWith("@g.us");
    const senderId = isGroup ? msg.key.participant || jid : jid;
    logger.info({
        jid,
        senderId,
        isGroup,
        msgId: msg.key.id,
        hasText: !!msg.message?.conversation || !!msg.message?.extendedTextMessage,
        hasAudio: !!msg.message?.audioMessage,
    }, "Incoming message");
    // --- Text messages ---
    const textContent = msg.message?.conversation ||
        msg.message?.extendedTextMessage?.text;
    if (textContent) {
        const prefix = isGroup ? `[group:${jid}] ` : "";
        const fullContent = `${prefix}${textContent}`;
        logger.info({ senderId, isGroup, contentLength: textContent.length }, "Forwarding text message to OpenClaw");
        const response = await (0, bridge_js_1.forwardToOpenClaw)(senderId, fullContent);
        if (response?.text) {
            await sock.sendMessage(jid, { text: response.text });
        }
        return;
    }
    // --- Voice / audio messages ---
    const audioMessage = msg.message?.audioMessage;
    if (audioMessage) {
        logger.info({ senderId, isGroup }, "Received audio message, transcribing");
        const transcribedText = await (0, audio_handler_js_1.handleAudioMessage)(sock, msg);
        if (transcribedText) {
            const prefix = isGroup ? `[group:${jid}] ` : "";
            const fullContent = `${prefix}[voice] ${transcribedText}`;
            logger.info({ senderId, transcribedLength: transcribedText.length }, "Forwarding transcribed audio to OpenClaw");
            const response = await (0, bridge_js_1.forwardToOpenClaw)(senderId, fullContent);
            if (response?.text) {
                await sock.sendMessage(jid, { text: response.text });
            }
        }
        else {
            logger.warn({ senderId }, "Audio transcription returned empty result");
        }
        return;
    }
    // --- Unsupported message types ---
    logger.debug({ senderId, messageKeys: Object.keys(msg.message || {}) }, "Ignoring unsupported message type");
}
//# sourceMappingURL=message-handler.js.map