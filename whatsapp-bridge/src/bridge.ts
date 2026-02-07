import axios from "axios";
import pino from "pino";

const logger = pino({ name: "bridge" });

const OPENCLAW_URL = process.env.OPENCLAW_URL || "http://openclaw:8000";

interface BridgePayload {
  channel: string;
  sender_id: string;
  content: string;
}

interface BridgeResponse {
  text?: string;
  metadata?: Record<string, unknown>;
  error?: string;
}

/**
 * Forward an incoming WhatsApp message to the OpenClaw orchestrator.
 * POST ${OPENCLAW_URL}/api/v1/message
 */
export async function forwardToOpenClaw(
  senderId: string,
  content: string
): Promise<BridgeResponse | null> {
  const url = `${OPENCLAW_URL}/api/v1/message`;

  const payload: BridgePayload = {
    channel: "whatsapp",
    sender_id: senderId,
    content,
  };

  try {
    logger.info(
      { url, sender_id: senderId, contentLength: content.length },
      "Forwarding message to OpenClaw"
    );

    const response = await axios.post<BridgeResponse>(url, payload, {
      headers: { "Content-Type": "application/json" },
      timeout: 30_000,
    });

    logger.info(
      { status: response.status, data: response.data },
      "OpenClaw response received"
    );

    return response.data;
  } catch (err) {
    if (axios.isAxiosError(err)) {
      logger.error(
        {
          status: err.response?.status,
          data: err.response?.data,
          message: err.message,
        },
        "Failed to forward message to OpenClaw"
      );
    } else {
      logger.error({ err }, "Unexpected error forwarding to OpenClaw");
    }

    return null;
  }
}
