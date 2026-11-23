/**
 * Replays `lisp-trace/1` logs written by `tools/cad_toolkit/test/trace_mini_lisp.py` (W-0.1): every
 * interaction the Python CAD tests had with `mini_lisp`, with its result, so the TypeScript interpreter
 * can be checked against the Python one on the same inputs.
 */

import { Interpreter } from './interp';
import { CaughtError, Cons, FileHandle, LispFunction, Sym, type Value, list } from './values';

export type Encoded =
  | null
  | string
  | Encoded[]
  | { i: number }
  | { r: number | 'nan' | 'inf' | '-inf' }
  | { y: string }
  | { p: [Encoded, Encoded] }
  | { fn: string }
  | { err: string }
  | { file: true }
  | { unencodable: string };

export type TraceOp =
  | { op: 'file'; path: string; content: string }
  | { op: 'load'; path: string; result?: Encoded; error?: string }
  | { op: 'run'; text: string; result?: Encoded; error?: string }
  | { op: 'set'; name: string; value: Encoded }
  | { op: 'get'; name: string; result?: Encoded }
  | {
      op: 'call';
      name: string;
      args: Encoded[];
      result?: Encoded;
      error?: string;
    };

export class Unreplayable extends Error {}

export function decode(interp: Interpreter, value: Encoded): Value {
  if (value === null || typeof value === 'string') return value;
  if (Array.isArray(value)) return list(value.map((item) => decode(interp, item)));
  if ('i' in value) return interp.N.int(value.i);
  if ('r' in value) {
    const r = value.r;
    return interp.N.real(r === 'nan' ? NaN : r === 'inf' ? Infinity : r === '-inf' ? -Infinity : r);
  }
  if ('y' in value) return interp.sym(value.y);
  if ('p' in value) return new Cons(decode(interp, value.p[0]), decode(interp, value.p[1]));
  if ('err' in value) return new CaughtError(value.err);
  throw new Unreplayable(JSON.stringify(value).slice(0, 80));
}

export function encode(interp: Interpreter, value: Value): Encoded {
  const N = interp.N;
  if (value === null || typeof value === 'string') return value;
  if (N.isNum(value)) {
    const v = N.val(value);
    if (N.isInt(value)) return { i: v };
    return {
      r: Number.isNaN(v) ? 'nan' : v === Infinity ? 'inf' : v === -Infinity ? '-inf' : v,
    };
  }
  if (value instanceof Cons) {
    // A proper list encodes as an array; anything ending in an atom as nested pairs (Python's Pair).
    const items: Value[] = [];
    let cell: Value = value;
    while (cell instanceof Cons) {
      items.push(cell.car);
      cell = cell.cdr;
    }
    if (cell === null) return items.map((item) => encode(interp, item));
    let tail = encode(interp, cell);
    for (let i = items.length - 1; i >= 0; i--) tail = { p: [encode(interp, items[i]!), tail] };
    return tail;
  }
  if (value instanceof Sym) return { y: value.name };
  if (value instanceof LispFunction) return { fn: value.name };
  if (value instanceof CaughtError) return { err: value.message };
  if (value instanceof FileHandle) return { file: true };
  return { unencodable: typeof value };
}

export interface Difference {
  op: number;
  name: string;
  path: string;
  expected: unknown;
  actual: unknown;
}

/** Compare encodings; reals within `tolerance` (relative) count as `approx`. */
export function compare(
  expected: Encoded | undefined,
  actual: Encoded,
  path: string,
  out: {
    diffs: { path: string; expected: unknown; actual: unknown }[];
    approx: number;
  },
  tolerance = 1e-12,
) {
  if (expected === undefined) return;
  if (expected !== null && typeof expected === 'object' && !Array.isArray(expected) && 'r' in expected) {
    if (actual !== null && typeof actual === 'object' && !Array.isArray(actual) && 'r' in actual) {
      const a = expected.r;
      const b = actual.r;
      if (a === b) return;
      if (typeof a === 'number' && typeof b === 'number' && Math.abs(a - b) <= tolerance * Math.max(1, Math.abs(a))) {
        out.approx += 1;
        return;
      }
    }
    out.diffs.push({ path, expected, actual });
    return;
  }
  if (expected !== null && typeof expected === 'object' && !Array.isArray(expected) && 'fn' in expected) {
    if (!(actual !== null && typeof actual === 'object' && !Array.isArray(actual) && 'fn' in actual))
      out.diffs.push({ path, expected, actual });
    return;
  }
  if (Array.isArray(expected)) {
    if (!Array.isArray(actual) || actual.length !== expected.length) {
      out.diffs.push({
        path,
        expected: summary(expected),
        actual: summary(actual),
      });
      return;
    }
    expected.forEach((item, index) => compare(item, actual[index]!, `${path}[${index}]`, out, tolerance));
    return;
  }
  if (expected !== null && typeof expected === 'object' && 'p' in expected) {
    if (!(actual !== null && typeof actual === 'object' && !Array.isArray(actual) && 'p' in actual)) {
      out.diffs.push({
        path,
        expected: summary(expected),
        actual: summary(actual),
      });
      return;
    }
    compare(expected.p[0], actual.p[0], `${path}.car`, out, tolerance);
    compare(expected.p[1], actual.p[1], `${path}.cdr`, out, tolerance);
    return;
  }
  if (JSON.stringify(expected) !== JSON.stringify(actual)) out.diffs.push({ path, expected, actual });
}

function summary(value: unknown) {
  const text = JSON.stringify(value);
  return text && text.length > 160 ? `${text.slice(0, 160)}…` : value;
}

export interface ReplayReport {
  replayed: boolean;
  reason?: string;
  ops: number;
  compared: number;
  approx: number;
  expectedErrors: number;
  differences: Difference[];
}

/** Replay one trace on a fresh interpreter. `readSource` reads a `<repo>/…` path. */
export function replay(
  trace: TraceOp[],
  readSource: (path: string) => string,
  options: { numbers?: 'box-int' | 'box-real' } = {},
): ReplayReport {
  const report: ReplayReport = {
    replayed: true,
    ops: trace.length,
    compared: 0,
    approx: 0,
    expectedErrors: 0,
    differences: [],
  };
  for (const op of trace) {
    if (op.op === 'set' && JSON.stringify(op.value).includes('"unencodable"'))
      return {
        ...report,
        replayed: false,
        reason: `stubs AutoCAD function ${op.name}`,
      };
    if (op.op === 'call' && JSON.stringify(op.args).includes('"unencodable"'))
      return {
        ...report,
        replayed: false,
        reason: `unencodable argument to ${op.name}`,
      };
  }
  const interp = new Interpreter(options);
  trace.forEach((op, index) => {
    const out = {
      diffs: [] as { path: string; expected: unknown; actual: unknown }[],
      approx: 0,
    };
    let name = op.op as string;
    const run = (body: () => Value, expectError: boolean | undefined, expected: Encoded | undefined) => {
      let result: Value;
      try {
        result = body();
      } catch (error) {
        if (expectError) {
          report.expectedErrors += 1;
          return;
        }
        out.diffs.push({
          path: 'error',
          expected: expected === undefined ? '(no result)' : summary(expected),
          actual: String(error),
        });
        return;
      }
      if (expectError) {
        out.diffs.push({
          path: 'error',
          expected: 'an error',
          actual: summary(encode(interp, result)),
        });
        return;
      }
      report.compared += 1;
      compare(expected, encode(interp, result), '', out);
    };
    switch (op.op) {
      case 'file':
        interp.vfs.put(op.path, op.content);
        return;
      case 'set':
        interp.set(op.name, decode(interp, op.value));
        return;
      case 'load':
        name = `load ${op.path}`;
        run(() => interp.loadText(readSource(op.path)), op.error !== undefined, op.result);
        break;
      case 'run':
        name = 'run';
        run(() => interp.run(op.text), op.error !== undefined, op.result);
        break;
      case 'get':
        name = `get ${op.name}`;
        run(() => interp.get(op.name), false, op.result);
        break;
      case 'call':
        name = op.name;
        run(
          () => interp.call(op.name, ...op.args.map((arg) => decode(interp, arg))),
          op.error !== undefined,
          op.result,
        );
        break;
    }
    report.approx += out.approx;
    for (const diff of out.diffs) report.differences.push({ op: index, name, ...diff });
  });
  return report;
}
