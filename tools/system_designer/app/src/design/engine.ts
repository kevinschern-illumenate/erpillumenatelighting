import { useEffect, useRef, useState } from 'react';
import type { Design } from '@ill/core-schemas/design';
import type { Line } from '@ill/core-schemas/open-design';
import { codeTables } from '@ill/data/codeTables';
import { checkDesign, type CheckInput, type DesignCheck, type VdLimits } from '@ill/engine/designCheck';
import type { DesignCatalog } from './catalog';

type Reply = { id: number; check?: DesignCheck; error?: string };

/** Runs design checks in a Web Worker when the browser has one, else on this thread (tests, old browsers). */
export interface CheckRunner {
  run(input: CheckInput): Promise<DesignCheck>;
  close(): void;
}

export function createCheckRunner(): CheckRunner {
  let worker: Worker | null = null;
  try {
    if (typeof Worker !== 'undefined')
      worker = new Worker(new URL('../workers/engine.worker.ts', import.meta.url), { type: 'module' });
  } catch {
    worker = null;
  }
  if (!worker)
    return {
      run: (input) => Promise.resolve().then(() => checkDesign(input)),
      close: () => undefined,
    };
  const pending = new Map<number, { resolve(check: DesignCheck): void; reject(error: Error): void }>();
  let next = 0;
  worker.onmessage = (event: MessageEvent<Reply>) => {
    const waiting = pending.get(event.data.id);
    pending.delete(event.data.id);
    if (!waiting) return;
    if (event.data.check) waiting.resolve(event.data.check);
    else waiting.reject(new Error(event.data.error ?? 'The checks could not run'));
  };
  worker.onerror = () => {
    for (const waiting of pending.values()) waiting.reject(new Error('The checks could not run'));
    pending.clear();
  };
  const active = worker;
  return {
    run(input) {
      const id = (next += 1);
      return new Promise((resolve, reject) => {
        pending.set(id, { resolve, reject });
        active.postMessage({ id, input });
      });
    },
    close: () => active.terminate(),
  };
}

export type CheckState =
  { state: 'waiting' } | { state: 'error'; message: string } | { state: 'ready'; check: DesignCheck; design: Design };

/** The latest checks for a design: each edit re-runs them after a short pause; stale answers are dropped. */
export function useDesignCheck(
  design: Design | null,
  catalog: DesignCatalog | null,
  lines: readonly Line[],
  limits: VdLimits,
  flags: { reviewRequired: boolean; outOfSync: boolean },
  delayMs = 120,
): CheckState {
  const runner = useRef<CheckRunner | null>(null);
  const [state, setState] = useState<CheckState>({ state: 'waiting' });
  useEffect(() => {
    const created = createCheckRunner();
    runner.current = created;
    return () => {
      created.close();
      runner.current = null;
    };
  }, []);
  const { reviewRequired, outOfSync } = flags;
  useEffect(() => {
    if (!design || !catalog) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      const input: CheckInput = {
        design,
        products: catalog.items,
        wires: catalog.wires,
        codeTables,
        lines,
        limits,
        reviewRequired,
        outOfSync,
      };
      (runner.current ?? createCheckRunner()).run(input).then(
        (check) => !cancelled && setState({ state: 'ready', check, design }),
        (problem: unknown) =>
          !cancelled &&
          setState({ state: 'error', message: problem instanceof Error ? problem.message : String(problem) }),
      );
    }, delayMs);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [design, catalog, lines, limits, reviewRequired, outOfSync, delayMs]);
  return state;
}
