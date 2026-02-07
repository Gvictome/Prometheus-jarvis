"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.getSocket = getSocket;
exports.initWhatsApp = initWhatsApp;
const baileys_1 = __importStar(require("@whiskeysockets/baileys"));
const pino_1 = __importDefault(require("pino"));
const node_fs_1 = __importDefault(require("node:fs"));
const node_path_1 = __importDefault(require("node:path"));
const logger = (0, pino_1.default)({ name: "whatsapp-client" });
const SESSION_DIR = process.env.SESSION_DIR || "/app/session";
let socket = null;
function getSocket() {
    return socket;
}
async function initWhatsApp() {
    // Ensure session directory exists
    if (!node_fs_1.default.existsSync(SESSION_DIR)) {
        node_fs_1.default.mkdirSync(SESSION_DIR, { recursive: true });
        logger.info({ dir: SESSION_DIR }, "Created session directory");
    }
    const sock = await connectWhatsApp();
    return sock;
}
async function connectWhatsApp() {
    const { state, saveCreds } = await (0, baileys_1.useMultiFileAuthState)(node_path_1.default.resolve(SESSION_DIR));
    const { version } = await (0, baileys_1.fetchLatestBaileysVersion)();
    logger.info({ version }, "Using Baileys version");
    const sock = (0, baileys_1.default)({
        version,
        auth: state,
        logger: (0, pino_1.default)({ level: "silent" }),
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
            const statusCode = lastDisconnect?.error?.output?.statusCode;
            const shouldReconnect = statusCode !== baileys_1.DisconnectReason.loggedOut;
            logger.warn({ statusCode, shouldReconnect }, "WhatsApp connection closed");
            if (shouldReconnect) {
                logger.info("Reconnecting to WhatsApp in 3 seconds...");
                setTimeout(() => {
                    connectWhatsApp().catch((err) => {
                        logger.error({ err }, "Reconnection failed");
                    });
                }, 3000);
            }
            else {
                logger.error("Logged out of WhatsApp. Delete the session directory and restart to re-authenticate.");
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
//# sourceMappingURL=whatsapp.js.map