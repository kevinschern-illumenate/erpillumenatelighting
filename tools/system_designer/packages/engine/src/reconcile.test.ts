import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { DesignSchema, type Design, type Run } from '@ill/core-schemas/design';
import { BuildsSchema, LineSchema, type Builds, type Line } from '@ill/core-schemas/open-design';
import { expandRuns } from './expand';
import { applyReconcile, diffDesign, fingerprints, type Fingerprints, type ReconcileDiff } from './reconcile';

const fixtures = new URL('../../core-schemas/fixtures/', import.meta.url);
const read = (path: string) => JSON.parse(readFileSync(new URL(path, fixtures), 'utf8'));

const opened = read('open-design/expected.json');
const before = {
  lines: LineSchema.array().parse(opened.lines) as Line[],
  builds: BuildsSchema.parse(opened.builds) as Builds,
};
const kase = read('reconcile/case.json') as {
  after: { lines: unknown; builds: unknown };
  stored: Fingerprints;
  design_runs: { key: string; lineKey: string; assignment?: { equipmentId: string; port: string } }[];
  diff: ReconcileDiff;
};
const after = {
  lines: LineSchema.array().parse(kase.after.lines) as Line[],
  builds: BuildsSchema.parse(kase.after.builds) as Builds,
};
const options = { groupThresholdQty: 6, defaultHomeRunFt: 10 };

function savedDesign(): Design {
  const expansion = expandRuns(before.lines, before.builds, options);
  const base = DesignSchema.parse(read('designs/valid/minimal.json'));
  const runs = expansion.runs.map((run): Run => {
    if (run.key === 'a1linear:1:1')
      return { ...run, assignment: { equipmentId: 'PS-02', port: 'OUT 1' }, homeRunLengthFt: 42 };
    if (run.key === 'd1group:1:1') return { ...run, assignment: { equipmentId: 'PS-01', port: 'OUT 1' } };
    if (run.key === 'b1tape:1:1') return { ...run, zoneId: 'z-1', homeRunLengthFt: 33, homeRunProvenance: 'measured' };
    return run;
  });
  return { ...base, site: { ...base.site, spaces: expansion.spaces }, runs };
}

describe('reconcile parity with Python', () => {
  it('computes the same fingerprints and diff', () => {
    expect(fingerprints(before.lines, before.builds)).toEqual(kase.stored);
    expect(diffDesign(kase.stored, after.lines, after.builds, kase.design_runs)).toEqual(kase.diff);
    expect(diffDesign(kase.stored, before.lines, before.builds).in_sync).toBe(true);
  });

  it('reads legacy plain-string fingerprints as changed when anything moved', () => {
    const legacy = Object.fromEntries(
      Object.entries(fingerprints(before.lines, before.builds)).map(([key, value]) => [key, value.fingerprint]),
    );
    const diff = diffDesign(legacy, after.lines, after.builds);
    expect(diff.qty).toEqual([]);
    expect(diff.changed.map((item) => item.key)).toContain('a1linear');
  });
});

describe('applying a diff', () => {
  const design = savedDesign();
  const diff = diffDesign(fingerprints(before.lines, before.builds), after.lines, after.builds, design.runs);
  const result = applyReconcile(design, after.lines, after.builds, diff, options);
  const runs = new Map(result.design.runs.map((run) => [run.key, run]));

  it('drops removed lines and lists their assignments', () => {
    expect([...runs.keys()].some((key) => key.startsWith('d1group:'))).toBe(false);
    expect(result.droppedAssignments).toEqual([{ runKey: 'd1group:1:1', equipmentId: 'PS-01', port: 'OUT 1' }]);
    expect(result.droppedRuns.every((key) => key.startsWith('d1group:'))).toBe(true);
  });

  it('adds copies for a quantity increase and keeps existing assignments', () => {
    const linear = [...runs.keys()].filter((key) => key.startsWith('a1linear:'));
    expect(linear.filter((key) => key.startsWith('a1linear:3:'))).toHaveLength(2);
    expect(runs.get('a1linear:1:1')).toMatchObject({ assignment: { equipmentId: 'PS-02' }, homeRunLengthFt: 42 });
    expect(runs.get('a1linear:3:1')?.assignment).toBeUndefined();
  });

  it('replaces changed builds but keeps the designer fields by run key', () => {
    const tape = runs.get('b1tape:1:1');
    expect(tape?.source).toMatchObject({ configHash: 'changed-config' });
    expect(tape).toMatchObject({ zoneId: 'z-1', homeRunLengthFt: 33, homeRunProvenance: 'measured' });
    expect(runs.get('e1other:1:1')?.watts).toBe(14.5);
  });

  it('adds new lines unassigned, with their spaces, and still parses', () => {
    expect(runs.get('n1new:2:1')).toMatchObject({ catalogId: 'tp:n1new', watts: 10 });
    expect(runs.get('n1new:1:1')?.assignment).toBeUndefined();
    expect(() => DesignSchema.parse(result.design)).not.toThrow();
    expect(diffDesign(fingerprints(after.lines, after.builds), after.lines, after.builds).in_sync).toBe(true);
  });

  it('removes copies from the end on a quantity decrease', () => {
    const fewer = after.lines.map((line) => (line.key === 'e1other' ? { ...line, qty: 2 } : line));
    const shrink = diffDesign(fingerprints(after.lines, after.builds), fewer, after.builds, result.design.runs);
    expect(shrink.qty).toEqual([{ key: 'e1other', lineId: 'E1', from: 6, to: 2 }]);
    const smaller = applyReconcile(result.design, fewer, after.builds, shrink, options);
    expect(smaller.design.runs.filter((run) => run.lineKey === 'e1other').map((run) => run.buildIndex)).toEqual([1, 2]);
    expect(smaller.droppedRuns).toEqual(['e1other:3:1', 'e1other:4:1', 'e1other:5:1', 'e1other:6:1']);
  });
});
