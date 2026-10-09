import { useEffect, useState } from 'react';
import { CatalogItemSchema, type CatalogItem } from '@ill/core-schemas/catalog';
import { WireTypeSchema, type WireType } from '@ill/core-schemas/wire';
import { DesignApiError, type DesignApi } from './api';

/** The catalog snapshot a design was opened with (H6 ``get_catalog``), indexed by item id. */
export interface DesignCatalog {
  hash: string;
  items: CatalogItem[];
  wires: WireType[];
  byId: ReadonlyMap<string, CatalogItem>;
}

/** Items and wires that parse with the engine schemas; example records never reach a dealer design. */
export function parseCatalog(hash: string, payload: unknown): DesignCatalog {
  const body = (payload ?? {}) as { items?: unknown[]; wires?: unknown[] };
  const items: CatalogItem[] = [];
  for (const entry of Array.isArray(body.items) ? body.items : []) {
    const parsed = CatalogItemSchema.safeParse(entry);
    if (parsed.success && !parsed.data.isExample) items.push(parsed.data);
  }
  const wires: WireType[] = [];
  for (const entry of Array.isArray(body.wires) ? body.wires : []) {
    const parsed = WireTypeSchema.safeParse(entry);
    if (parsed.success && !parsed.data.isExample) wires.push(parsed.data);
  }
  return { hash, items, wires, byId: new Map(items.map((item) => [item.id, item])) };
}

const cache = new Map<string, Promise<DesignCatalog>>();

/** Snapshots never change, so each hash is fetched once per page. */
export function loadCatalog(api: DesignApi, hash: string): Promise<DesignCatalog> {
  let pending = cache.get(hash);
  if (!pending) {
    pending = Promise.resolve()
      .then(() => api.getCatalog(hash))
      .then((payload) => parseCatalog(hash, payload));
    pending.catch(() => cache.delete(hash));
    cache.set(hash, pending);
  }
  return pending;
}

export type CatalogState =
  { state: 'loading' } | { state: 'error'; message: string } | { state: 'ready'; catalog: DesignCatalog };

export function useCatalog(api: DesignApi, hash: string): CatalogState {
  const [state, setState] = useState<CatalogState & { hash?: string }>({ state: 'loading' });
  useEffect(() => {
    let cancelled = false;
    loadCatalog(api, hash).then(
      (catalog) => !cancelled && setState({ state: 'ready', catalog, hash }),
      (problem: unknown) =>
        !cancelled &&
        setState({
          state: 'error',
          hash,
          message: problem instanceof DesignApiError ? problem.message : 'The ilLumenate catalog could not be loaded.',
        }),
    );
    return () => {
      cancelled = true;
    };
  }, [api, hash]);
  return state.hash === hash ? state : { state: 'loading' };
}
