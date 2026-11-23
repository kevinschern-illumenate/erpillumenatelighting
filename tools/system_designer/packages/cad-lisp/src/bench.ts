/**
 * W-0.1 benchmark: the ILQUOTE steps (`il-check`, `il-model-hash`, `il-package`, `il-json-text`) on
 * scaled drawing models (`fixtures/cad/web/bench-models.json`, from `tools/cad_toolkit/test/bench_models.py`).
 * Runs in Node (Vitest) and in a browser Web Worker (`bench/worker.ts`).
 */

import { Interpreter } from './interp';
import { Cons } from './values';
import { installNativeJson } from './native-json';
import { sha256Text } from './sha256';
import { type Encoded, decode } from './trace';

/** The pure files, in `tests/portal_unit/test_cad_lisp.py PURE` order. */
export const PURE_FILES = [
  'il-util.lsp',
  'il-json.lsp',
  'il-math.lsp',
  'il-sha256.lsp',
  'il-catalog.lsp',
  'il-model.lsp',
  'il-controls.lsp',
] as const;

export interface BenchInput {
  catalog: Encoded;
  today: string;
  models: Record<string, Encoded>;
}

export interface BenchOptions {
  numbers: 'box-int' | 'box-real';
  nativeSha: boolean;
  nativeJson?: boolean;
  repeat: number;
  sizes?: string[];
}

export type Timings = Record<string, number>;

export function createVm(
  sources: Record<string, string>,
  options: Pick<BenchOptions, 'numbers' | 'nativeSha' | 'nativeJson'>,
) {
  const interp = new Interpreter({ numbers: options.numbers });
  for (const name of PURE_FILES) interp.loadText(sources[name]!);
  if (options.nativeSha) interp.set('il-sha256', (args) => sha256Text(args[0] as string));
  if (options.nativeJson) installNativeJson(interp);
  return interp;
}

const now = () => (typeof performance !== 'undefined' ? performance.now() : Date.now());

export function runBench(sources: Record<string, string>, input: BenchInput, options: BenchOptions) {
  let start = now();
  const interp = createVm(sources, options);
  const loadMs = now() - start;
  const catalog = decode(interp, input.catalog);
  const results: Record<string, Timings> = {};
  for (const size of options.sizes ?? Object.keys(input.models)) {
    const model = decode(interp, input.models[size]!);
    const best: Timings = {};
    let issues = 0;
    let packageChars = 0;
    let hash = '';
    for (let r = 0; r < options.repeat; r++) {
      const t: Timings = {};
      start = now();
      const found = interp.call('il-check', model, catalog, input.today);
      t.check = now() - start;
      start = now();
      hash = interp.call('il-model-hash', model, catalog) as string;
      t.hash = now() - start;
      start = now();
      const pkg = interp.call('il-package', model, catalog, found, 'bench');
      t.package = now() - start;
      start = now();
      const text = interp.call('il-json-text', pkg) as string;
      t.json = now() - start;
      t.total = t.check + t.hash + t.package + t.json;
      for (const [key, value] of Object.entries(t)) best[key] = Math.min(best[key] ?? Infinity, value);
      issues = 0;
      for (let cell = found; cell instanceof Cons; cell = cell.cdr) issues++;
      packageChars = text.length;
    }
    results[size] = {
      ...roundAll(best),
      issues,
      packageChars,
      hashPrefix: parseInt(hash.slice(0, 6), 16),
    };
  }
  return { loadMs: Math.round(loadMs), results };
}

function roundAll(t: Timings): Timings {
  return Object.fromEntries(Object.entries(t).map(([k, v]) => [k, Math.round(v * 10) / 10]));
}
