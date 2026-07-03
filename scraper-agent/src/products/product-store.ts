import fs from "fs";
import path from "path";
import crypto from "crypto";
import type { ProductData } from "../modules/shopping/ai/claude";

export interface StoredProduct {
  id: string;
  url: string;
  domain: string;
  crawled_at: string;
  list_url?: string;
  data: ProductData;
}

const DATA_DIR = path.resolve(__dirname, "../../data");
const STORE_FILE = path.join(DATA_DIR, "products.json");

let _cache: StoredProduct[] | null = null;

function load(): StoredProduct[] {
  if (_cache !== null) return _cache;
  try {
    if (!fs.existsSync(STORE_FILE)) return (_cache = []);
    _cache = JSON.parse(fs.readFileSync(STORE_FILE, "utf-8")) as StoredProduct[];
    return _cache;
  } catch {
    return (_cache = []);
  }
}

function persist(products: StoredProduct[]) {
  _cache = products;
  fs.mkdirSync(DATA_DIR, { recursive: true });
  fs.writeFileSync(STORE_FILE, JSON.stringify(products, null, 2), "utf-8");
}

export const productStore = {
  list({ domain, q, limit = 100, offset = 0 }: { domain?: string; q?: string; limit?: number; offset?: number } = {}): StoredProduct[] {
    let items = load().slice();
    if (domain) items = items.filter(p => p.domain === domain);
    if (q) {
      const lq = q.toLowerCase();
      items = items.filter(p =>
        p.url.toLowerCase().includes(lq) ||
        String(p.data.title ?? "").toLowerCase().includes(lq) ||
        String(p.data.brand ?? "").toLowerCase().includes(lq) ||
        String(p.data.seller ?? "").toLowerCase().includes(lq)
      );
    }
    items.sort((a, b) => new Date(b.crawled_at).getTime() - new Date(a.crawled_at).getTime());
    return items.slice(offset, offset + limit);
  },

  count(domain?: string): number {
    const all = load();
    return domain ? all.filter(p => p.domain === domain).length : all.length;
  },

  domains(): string[] {
    return [...new Set(load().map(p => p.domain))].sort();
  },

  upsert(url: string, domain: string, data: ProductData, listUrl?: string): StoredProduct {
    const products = load();
    const idx = products.findIndex(p => p.url === url);
    const product: StoredProduct = {
      id: idx >= 0 ? products[idx].id : crypto.randomUUID(),
      url,
      domain,
      crawled_at: new Date().toISOString(),
      ...(listUrl ? { list_url: listUrl } : {}),
      data,
    };
    if (idx >= 0) products[idx] = product;
    else products.push(product);
    persist(products);
    return product;
  },

  delete(id: string): boolean {
    const products = load();
    const idx = products.findIndex(p => p.id === id);
    if (idx < 0) return false;
    products.splice(idx, 1);
    persist(products);
    return true;
  },

  clear(): void {
    persist([]);
  },
};
