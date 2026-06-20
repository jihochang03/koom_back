// Background prefetch queue: crawls product detail URLs one by one
// and pushes results to the Django backend.
import analyzeSiteHandler from "../modules/shopping/apis/analyze-site";

interface PrefetchItem {
  productId: number;
  url: string;
  djangoBase: string;
}

const queue: PrefetchItem[] = [];
let busy = false;

export function enqueuePrefetch(productId: number, url: string, djangoBase: string): void {
  queue.push({ productId, url, djangoBase });
  if (!busy) drain();
}

async function patchDjango(item: PrefetchItem, body: Record<string, unknown>): Promise<void> {
  await fetch(`${item.djangoBase}/api/products/${item.productId}/detail/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function drain(): Promise<void> {
  busy = true;
  while (queue.length > 0) {
    const item = queue.shift()!;
    console.info(`[prefetch] ▶ ${item.url} (id=${item.productId})`);

    try {
      // Mark as in-progress
      await patchDjango(item, { detail_status: "prefetching", detail_data: {} });

      // Crawl
      const result = await analyzeSiteHandler(
        { url: item.url, category: "shopping" },
        null,
        null,
      );

      await patchDjango(item, { detail_status: "ready", detail_data: result });
      console.info(`[prefetch] ✓ done id=${item.productId}`);
    } catch (err) {
      console.error(`[prefetch] ✗ failed id=${item.productId}:`, err);
      try {
        await patchDjango(item, { detail_status: "failed", detail_data: {} });
      } catch {}
    }
  }
  busy = false;
}
