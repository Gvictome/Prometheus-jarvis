import { WASocket, proto } from "@whiskeysockets/baileys";
/**
 * Download a voice message from WhatsApp (.ogg) and POST it to
 * the Voice Gateway for transcription.
 *
 * Returns the transcribed text, or null on failure.
 */
export declare function handleAudioMessage(sock: WASocket, msg: proto.IWebMessageInfo): Promise<string | null>;
//# sourceMappingURL=audio-handler.d.ts.map