"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
require("dotenv/config");
const express_1 = __importDefault(require("express"));
const whatsapp_js_1 = require("./whatsapp.js");
const message_handler_js_1 = require("./message-handler.js");
const pino_1 = __importDefault(require("pino"));
const logger = (0, pino_1.default)({ name: "whatsapp-bridge" });
const app = (0, express_1.default)();
app.use(express_1.default.json());
const PORT = parseInt(process.env.PORT || "3001", 10);
// Health check
app.get("/health", (_req, res) => {
    const sock = (0, whatsapp_js_1.getSocket)();
    res.json({
        status: "ok",
        connected: sock !== null,
    });
});
// POST /api/send - OpenClaw pushes messages back to WhatsApp
app.post("/api/send", async (req, res) => {
    try {
        const { recipient, message } = req.body;
        if (!recipient || !message) {
            res.status(400).json({ error: "Missing 'recipient' or 'message' in request body" });
            return;
        }
        const sock = (0, whatsapp_js_1.getSocket)();
        if (!sock) {
            res.status(503).json({ error: "WhatsApp not connected" });
            return;
        }
        await sock.sendMessage(recipient, { text: message });
        logger.info({ recipient }, "Message sent to WhatsApp");
        res.json({ status: "sent", recipient });
    }
    catch (err) {
        logger.error({ err }, "Failed to send WhatsApp message");
        res.status(500).json({ error: "Failed to send message" });
    }
});
async function main() {
    logger.info("Starting WhatsApp Bridge service...");
    // Initialize WhatsApp connection
    const sock = await (0, whatsapp_js_1.initWhatsApp)();
    // Register the incoming message handler
    (0, message_handler_js_1.registerMessageHandler)(sock);
    // Start HTTP server
    app.listen(PORT, () => {
        logger.info({ port: PORT }, "WhatsApp Bridge HTTP server listening");
    });
}
main().catch((err) => {
    logger.error({ err }, "Fatal error in WhatsApp Bridge");
    process.exit(1);
});
//# sourceMappingURL=index.js.map