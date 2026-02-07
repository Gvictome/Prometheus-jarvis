interface BridgeResponse {
    text?: string;
    metadata?: Record<string, unknown>;
    error?: string;
}
/**
 * Forward an incoming WhatsApp message to the OpenClaw orchestrator.
 * POST ${OPENCLAW_URL}/api/v1/message
 */
export declare function forwardToOpenClaw(senderId: string, content: string): Promise<BridgeResponse | null>;
export {};
//# sourceMappingURL=bridge.d.ts.map