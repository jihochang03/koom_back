// @intuned/runtime equivalent — timeout extension + payload chaining
interface PayloadEntry {
  api: string;
  parameters: Record<string, unknown>;
}

const payloadQueue: PayloadEntry[] = [];
let timeoutExtensionCount = 0;

// Signal the runtime to allow more execution time.
// In production Intuned this sends a heartbeat; here we log it.
export function extendTimeout(): void {
  timeoutExtensionCount += 1;
  console.info(`[runtime] Timeout extended (×${timeoutExtensionCount})`);
}

// Schedule a follow-up API call (e.g., list-items → get-item chain).
export function extendPayload({
  api,
  parameters,
}: {
  api: string;
  parameters: Record<string, unknown>;
}): void {
  payloadQueue.push({ api, parameters });
}

export function getPayloadQueue(): PayloadEntry[] {
  return [...payloadQueue];
}

export function clearPayloadQueue(): void {
  payloadQueue.length = 0;
}
