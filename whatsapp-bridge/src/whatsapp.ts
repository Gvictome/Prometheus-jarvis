import makeWASocket, {
  DisconnectReason,
  useMultiFileAuthState,
  WASocket,
  fetchLatestBaileysVersion,
} from "@whiskeysockets/baileys";
import { Boom } from "@hapi/boom";
import pino from "pino";
import fs from "node:fs";
import path from "node:path";

const logger = pino({ name: "whatsapp-client" });

const SESSION_DIR = process.env.SESSION_DIR || "/app/session";

let socket: WASocket | null = null;

export function getSocket(): WASocket | null {
  return socket;
}

export async function initWhatsApp(): Promise<WASocket> {
  // Ensure session directory exists
  if (!fs.existsSync(SESSION_DIR)) {
    fs.mkdirSync(SESSION_DIR, { recursive: true });
    logger.info({ dir: SESSION_DIR }, "Created session directory");
  }

  const sock = await connectWhatsApp();
  return sock;
}

async function connectWhatsApp(): Promise<WASocket> {
  const { state, saveCreds } = await useMultiFileAuthState(
    path.resolve(SESSION_DIR)
  );

  const { version } = await fetchLatestBaileysVersion();
  logger.info({ version }, "Using Baileys version");

  const sock = makeWASocket({
    version,
    auth: state,
    logger: pino({ level: "silent" }) as any,
    printQRInTerminal: true,
    generateHighQualityLinkPreview: false,
    markOnlineOnConnect: true,
  });

  // Persist credentials on update
  sock.ev.on("creds.update", saveCreds);

  // Handle connection updates (QR code, reconnection)
  sock.ev.on("connection.update", (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      logger.info("QR code generated - scan with WhatsApp to authenticate");
    }

    if (connection === "close") {
      const statusCode = (lastDisconnect?.error as Boom)?.output?.statusCode;
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

      logger.warn(
        { statusCode, shouldReconnect },
        "WhatsApp connection closed"
      );

      if (shouldReconnect) {
        logger.info("Reconnecting to WhatsApp in 3 seconds...");
        setTimeout(() => {
          connectWhatsApp().catch((err) => {
            logger.error({ err }, "Reconnection failed");
          });
        }, 3000);
      } else {
        logger.error(
          "Logged out of WhatsApp. Delete the session directory and restart to re-authenticate."
        );
        socket = null;
      }
    }

    if (connection === "open") {
      logger.info("WhatsApp connection established successfully");
      socket = sock;
    }
  });

  socket = sock;
  return sock;
}
