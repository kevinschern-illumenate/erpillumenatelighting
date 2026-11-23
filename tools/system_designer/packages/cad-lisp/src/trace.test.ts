import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { type TraceOp, replay } from './trace';

const REPO = resolve(import.meta.dirname, '../../../../..');
const TRACE = resolve(REPO, 'tools/system_designer/fixtures/cad/web/lisp-trace.json');
const readSource = (path: string) => readFileSync(path.replace('<repo>', REPO), 'utf8');

// The trace is generated, not committed (5+ MB): python -B -m tools.cad_toolkit.test.trace_mini_lisp
//   --out tools/system_designer/fixtures/cad/web/lisp-trace.json
const traces: TraceOp[][] = existsSync(TRACE) ? JSON.parse(readFileSync(TRACE, 'utf8')).traces : [];

describe.each(['box-int', 'box-real'] as const)('mini_lisp trace replay (%s)', (numbers) => {
  it.skipIf(!traces.length)('matches the Python interpreter on every replayable trace', () => {
    const reports = traces.map((trace) => replay(trace, readSource, { numbers }));
    const replayed = reports.filter((r) => r.replayed);
    const skipped = reports.filter((r) => !r.replayed);
    const differences = replayed.flatMap((r, t) => r.differences.map((d) => ({ trace: t, ...d })));
    const summary = {
      traces: reports.length,
      replayed: replayed.length,
      skipped: skipped.map((r) => r.reason),
      compared: replayed.reduce((n, r) => n + r.compared, 0),
      approx: replayed.reduce((n, r) => n + r.approx, 0),
      expectedErrors: replayed.reduce((n, r) => n + r.expectedErrors, 0),
      differences: differences.length,
    };
    console.log(numbers, JSON.stringify(summary));
    if (differences.length) console.log(JSON.stringify(differences.slice(0, 15), null, 1));
    expect(differences).toEqual([]);
  });
});
