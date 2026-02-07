"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.forwardToOpenClaw = forwardToOpenClaw;
const axios_1 = __importDefault(require("axios"));
const pino_1 = __importDefault(require("pino"));
const logger = (0, pino_1.default)({ name: "bridge" });
const OPENCLAW_URL = process.env.OPENCLAW_URL || "http://openclaw:8000";
/**
 * Forward an incoming WhatsApp message to the OpenClaw orchestrator.
 * POST ${OPENCLAW_URL}/api/v1/message
 */
async function forwardToOpenClaw(senderId, content) {
    const url = `${OPENCLAW_URL}/api/v1/message`;
    const payload = {
        channel: "whatsapp",
        sender_id: senderId,
        content,
    };
    try {
        logger.info({ url, sender_id: senderId, contentLength: content.length }, "Forwarding message to OpenClaw");
        const response = await axios_1.default.post(url, payload, {
            headers: { "Content-Type": "application/json" },
            timeout: 30_000,
        });
        logger.info({ status: response.status, data: response.data }, "OpenClaw response received");
        return response.data;
    }
    catch (err) {
        if (axios_1.default.isAxiosError(err)) {
            logger.error({
                status: err.response?.status,
                data: err.response?.data,
                message: err.message,
            }, "Failed to forward message to OpenClaw");
        }
        else {
            logger.error({ err }, "Unexpected error forwarding to OpenClaw");
        }
        return null;
    }
}
//# sourceMappingURL=bridge.js.map