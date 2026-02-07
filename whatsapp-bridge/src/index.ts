import "dotenv/config";
import express, { Request, Response } from "express";
import { initWhatsApp, getSocket } from "./whatsapp.js";
import { registerMessageHandler } from "./message-handler.js";
import pino from "pino";

const logger = pino({ name: "whatsapp-bridge" });

const app = express();
app.use(express.json());

const PORT = parseInt(process.env.PORT || "3001", 10);

// Health check
app.get("/health", (_req: Request, res: Response) => {
  const sock = getSocket();
  res.json({
    status: "ok",
    connected: sock !== null,
  });
});

// POST /api/send - OpenClaw pushes messages back to WhatsApp
app.post("/api/send", async (req: Request, res: Response) => {
  try {
    const { recipient, message } = req.body;

    if (!recipient || !message) {
      res.status(400).json({ error: "Missing 'recipient' or 'message' in request body" });
      return;
    }

    const sock = getSocket();
    if (!sock) {
      res.status(503).json({ error: "WhatsApp not connected" });
      return;
    }

    await sock.sendMessage(recipient, { text: message });
    logger.info({ recipient }, "Message sent to WhatsApp");

    res.json({ status: "sent", recipient });
  } catch (err) {
    logger.error({ err }, "Failed to send WhatsApp message");
    res.status(500).json({ error: "Failed to send message" });
  }
});

async function main(): Promise<void> {
  logger.info("Starting WhatsApp Bridge service...");

  // Initialize WhatsApp connection
  const sock = await initWhatsApp();

  // Register the incoming message handler
  registerMessageHandler(sock);

  // Start HTTP server
  app.listen(PORT, () => {
    logger.info({ port: PORT }, "WhatsApp Bridge HTTP server listening");
  });
}

main().catch((err) => {
  logger.error({ err }, "Fatal error in WhatsApp Bridge");
  process.exit(1);
});
