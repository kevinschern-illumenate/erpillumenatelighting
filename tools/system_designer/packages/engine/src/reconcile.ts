import type { Design, Run, Space } from '@ill/core-schemas/design';
import { roundNumber, sha256Hex } from '@ill/core-schemas/hash';
import type { Builds, Line } from '@ill/core-schemas/open-design';
import { expandRuns, type ExpandOptions } from './expand';

/**
 * Saved design versus the schedule now (plan H8.4), mirroring `system_design/reconcile.py`.
 * The fingerprint is byte-for-byte the Python one; both suites check `fixtures/reconcile/case.json`.
 */

export interface LineFingerprint {
  fingerprint: string;
  qty: number;
}
export type Fingerprints = Record<string, LineFingerprint | string>;

export interface LineRef {
  key: string;
  lineId: string | null;
}
export interface DroppedAssignment {
  runKey: string;
  equipmentId: string;
  port: string;
}
export interface ReconcileDiff {
  added: LineRef[];
  removed: { key: string; runs: string[]; assignments: DroppedAssignment[] }[];
  changed: LineRef[];
  qty: (LineRef & { from: number; to: number })[];
  in_sync: boolean;
}

function part(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return '';
  return typeof value === 'number' ? String(roundNumber(value)) : value;
}

export function lineFingerprint(line: Line, builds: Builds, qty?: number): string {
  const ref = line.configured;
  const build = ref ? builds[ref.doctype]?.[ref.name] : undefined;
  const third = line.thirdParty;
  const parts = [
    line.key,
    ref?.doctype,
    ref?.name,
    build?.configHash,
    qty ?? line.qty,
    third?.wattsEach,
    third?.inputVoltageV,
    third?.voltageClass,
    third?.drive,
    third?.mA,
    third?.dimmingName,
  ];
  return sha256Hex(parts.map(part).join('|'));
}

/** Lines that feed a design; write-back lines are its outputs. */
export function designLines(lines: Line[]): Line[] {
  return lines.filter((line) => line.kind !== 'writeback' && !line.designLineRole);
}

export function fingerprints(lines: Line[], builds: Builds): Record<string, LineFingerprint> {
  return Object.fromEntries(
    designLines(lines).map((line) => [line.key, { fingerprint: lineFingerprint(line, builds), qty: line.qty }]),
  );
}

type RunLike = Pick<Run, 'key' | 'lineKey'> & { assignment?: { equipmentId: string; port: string } };

const byKey = (a: { key: string }, b: { key: string }) => (a.key < b.key ? -1 : a.key > b.key ? 1 : 0);

export function diffDesign(
  stored: Fingerprints,
  lines: Line[],
  builds: Builds,
  runs: readonly RunLike[] = [],
): ReconcileDiff {
  const current = new Map(designLines(lines).map((line) => [line.key, line]));
  const diff: ReconcileDiff = { added: [], removed: [], changed: [], qty: [], in_sync: true };
  for (const [key, line] of current) {
    const label = { key, lineId: line.lineId };
    const entry = stored[key];
    if (entry === undefined) {
      diff.added.push(label);
      continue;
    }
    const saved = typeof entry === 'string' ? entry : entry.fingerprint;
    if (saved === lineFingerprint(line, builds)) continue;
    const oldQty = typeof entry === 'string' ? undefined : entry.qty;
    if (oldQty !== undefined && saved === lineFingerprint(line, builds, oldQty))
      diff.qty.push({ ...label, from: oldQty, to: line.qty });
    else diff.changed.push(label);
  }
  for (const key of Object.keys(stored).sort()) {
    if (current.has(key)) continue;
    const dropped = runs.filter((run) => run.lineKey === key).sort(byKey);
    diff.removed.push({
      key,
      runs: dropped.map((run) => run.key),
      assignments: dropped.flatMap((run) => (run.assignment ? [{ runKey: run.key, ...run.assignment }] : [])),
    });
  }
  diff.in_sync = !(diff.added.length || diff.removed.length || diff.changed.length || diff.qty.length);
  return diff;
}

export interface ApplyResult {
  design: Design;
  droppedRuns: string[];
  droppedAssignments: DroppedAssignment[];
}

/** Fields the designer owns on a run; ERP fields (length, watts, feed, source) come from the schedule. */
const KEPT_FIELDS = ['spaceId', 'env', 'homeRunLengthFt', 'homeRunProvenance', 'assignment', 'zoneId'] as const;

/**
 * Apply a diff to the design's runs: removed lines drop their runs, added lines arrive unassigned,
 * changed lines take the new ERP values but keep the designer's fields by run key, and a quantity
 * change adds or drops copies from the end. Spaces for new runs are added when missing.
 */
export function applyReconcile(
  design: Design,
  lines: Line[],
  builds: Builds,
  diff: ReconcileDiff,
  options: ExpandOptions,
): ApplyResult {
  const touched = new Set([...diff.added, ...diff.changed, ...diff.qty].map((item) => item.key));
  const removed = new Set(diff.removed.map((item) => item.key));
  const existing = new Map(design.runs.map((run) => [run.key, run]));
  const expansion = expandRuns(lines, builds, options);
  const fresh = expansion.runs.filter((run) => touched.has(run.lineKey));
  const freshKeys = new Set(fresh.map((run) => run.key));

  const kept = design.runs.filter((run) => !removed.has(run.lineKey) && !touched.has(run.lineKey));
  const merged = fresh.map((run) => {
    const old = existing.get(run.key);
    if (!old) return run;
    const next: Run = { ...run };
    for (const field of KEPT_FIELDS) {
      if (old[field] === undefined) delete next[field];
      else (next as Record<string, unknown>)[field] = old[field];
    }
    return next;
  });
  const dropped = design.runs
    .filter((run) => removed.has(run.lineKey) || (touched.has(run.lineKey) && !freshKeys.has(run.key)))
    .sort(byKey);

  const spaceIds = new Set(design.site.spaces.map((space) => space.id));
  const newSpaces: Space[] = expansion.spaces.filter(
    (space) => !spaceIds.has(space.id) && merged.some((run) => run.spaceId === space.id),
  );
  return {
    design: {
      ...design,
      site: { ...design.site, spaces: [...design.site.spaces, ...newSpaces] },
      runs: [...kept, ...merged],
    },
    droppedRuns: dropped.map((run) => run.key),
    droppedAssignments: dropped.flatMap((run) => (run.assignment ? [{ runKey: run.key, ...run.assignment }] : [])),
  };
}
