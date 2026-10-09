import { CatalogItemSchema, type CatalogItem } from '@ill/core-schemas/catalog';
import type { DesignApi } from './api';

/** The catalog snapshot a design was opened with (H6 ``get_catalog``), indexed by item id. */
export interface DesignCatalog {
  hash: string;
  items: CatalogItem[];
  byId: ReadonlyMap<string, CatalogItem>;
}

/** Items that parse with the engine schema; example products never reach a dealer design. */
export function parseCatalog(hash: string, payload: unknown): DesignCatalog {
  const raw = (payload as { items?: unknown[] } | null)?.items;
  const items: CatalogItem[] = [];
  for (const entry of Array.isArray(raw) ? raw : []) {
    const parsed = CatalogItemSchema.safeParse(entry);
    if (parsed.success && !parsed.data.isExample) items.push(parsed.data);
  }
  return { hash, items, byId: new Map(items.map((item) => [item.id, item])) };
}

const cache = new Map<string, Promise<DesignCatalog>>();

/** Snapshots never change, so each hash is fetched once per page. */
export function loadCatalog(api: DesignApi, hash: string): Promise<DesignCatalog> {
  let pending = cache.get(hash);
  if (!pending) {
    pending = api.getCatalog(hash).then((payload) => parseCatalog(hash, payload));
    pending.catch(() => cache.delete(hash));
    cache.set(hash, pending);
  }
  return pending;
}
