import type { Design, Run } from '@ill/core-schemas/design';
import type { Build, Builds } from '@ill/core-schemas/open-design';
import type { ValidationMessage } from '@ill/core-schemas/project';
import { message, round } from './messages';

/**
 * Run editor (plan §9.3, WP-3.3): labels, grouping and run-level checks. Lengths, watts and feeds come
 * from the ERP build and stay read-only here; tape runs joined by jumpers already arrive as one run
 * (`connected_runs` in the ERP expansion), so each run is one circuit.
 */

/** Share of the effective maximum at which a run gets a length hint. */
export const MAX_LENGTH_HINT_SHARE = 0.9;

/** "F3-1.2": line, copy and run (plan §9.1). */
export const runLabel = (run: Pick<Run, 'lineId' | 'buildIndex' | 'runIndex'>) =>
  `${run.lineId}-${run.buildIndex}.${run.runIndex}`;

export function buildFor(run: Run, builds: Builds): Build | undefined {
  return run.source.kind === 'configured' ? builds[run.source.doctype]?.[run.source.name] : undefined;
}

const FAMILY_LABELS: Record<Build['family'], string> = {
  linear: 'Linear fixture',
  tape: 'Tape / neon',
  sheet: 'LED sheet',
  group: 'Fixture group',
};

export function runType(run: Run, builds: Builds): string {
  if (run.source.kind === 'third-party') return 'Third-party';
  const build = buildFor(run, builds);
  return build ? FAMILY_LABELS[build.family] : 'Configured';
}

/** Where the feeds sit along a run, as shares of its length (0 = start, 1 = end). */
export function feedPositions(run: Pick<Run, 'feedMethod' | 'feeds'>): number[] {
  if (run.feedMethod === 'double-end') return [0, 1];
  if (run.feedMethod === 'center') return [0.5];
  if (run.feedMethod === 'multi-feed') {
    const count = Math.max(run.feeds ?? 2, 2);
    return Array.from({ length: count }, (_, index) => round(index / (count - 1), 4));
  }
  return [0];
}

/** Run-level checks: length against the build's effective maximum, and feed counts that do not fit the method. */
export function runChecks(design: Design, builds: Builds): ValidationMessage[] {
  const messages: ValidationMessage[] = [];
  for (const run of design.runs) {
    const label = runLabel(run);
    const max = buildFor(run, builds)?.maxRunFtEffective ?? null;
    if (max !== null && run.lengthFt !== undefined) {
      if (run.lengthFt > max)
        messages.push(
          message(
            'TAPE_RUN_TOO_LONG',
            'error',
            run.key,
            `${label} is ${round(run.lengthFt, 1)} ft; this build allows ${round(max, 1)} ft from its feed. ` +
              'Feed it from both ends or split it in the configurator.',
          ),
        );
      else if (run.lengthFt > max * MAX_LENGTH_HINT_SHARE)
        messages.push(
          message(
            'MAX_LENGTH_HINT',
            'info',
            run.key,
            `${label} is ${round(run.lengthFt, 1)} ft, close to the ${round(max, 1)} ft maximum for this build.`,
          ),
        );
    }
    const feeds = run.feeds;
    if (feeds !== undefined && run.feedMethod === 'double-end' && feeds !== 2)
      messages.push(message('INVALID_SPEC', 'warning', run.key, `${label} is fed from both ends but lists ${feeds}.`));
    if (run.feedMethod === 'multi-feed' && (feeds === undefined || feeds < 2))
      messages.push(
        message(
          'INVALID_SPEC',
          'warning',
          run.key,
          `${label} is multi-feed but its build does not say how many feeds.`,
        ),
      );
  }
  return messages;
}

/** Move runs to another space; they take its environment unless set on their own. */
export function moveRuns(design: Design, runKeys: readonly string[], spaceId: string) {
  if (!design.site.spaces.some((space) => space.id === spaceId)) throw new Error(`Unknown space: ${spaceId}`);
  const keys = new Set(runKeys);
  for (const run of design.runs) if (keys.has(run.key)) run.spaceId = spaceId;
}

/** Runs of one group, in design order. */
export const groupMembers = (design: Design, groupId: string) => design.runs.filter((run) => run.groupId === groupId);

/** Stop treating a group as one: each run is listed and assigned on its own. */
export function splitGroup(design: Design, groupId: string) {
  for (const run of design.runs) if (run.groupId === groupId) delete run.groupId;
}

/**
 * Group runs of identical builds (copies of one schedule line, plan §9.1) so they are assigned once.
 * Returns the group id. Runs already in another group leave it.
 */
export function groupRuns(design: Design, runKeys: readonly string[]): string {
  const keys = new Set(runKeys);
  const runs = design.runs.filter((run) => keys.has(run.key));
  if (runs.length < 2) throw new Error('Select at least two runs to group');
  const first = runs[0]!;
  if (!runs.every((run) => run.lineKey === first.lineKey))
    throw new Error('Only runs of one schedule line can be grouped');
  if (runs.some((run) => run.assignment?.equipmentId !== first.assignment?.equipmentId))
    throw new Error('Unassign the runs, or assign them to the same supply, before grouping');
  const used = new Set(design.runs.filter((run) => !keys.has(run.key) && run.groupId).map((run) => run.groupId));
  let id = `grp-${first.lineKey}`;
  for (let number = 2; used.has(id); number += 1) id = `grp-${first.lineKey}-${number}`;
  for (const run of runs) run.groupId = id;
  return id;
}

/** One table row: a run, or a folded group of identical runs. */
export interface RunRow {
  id: string;
  label: string;
  runs: Run[];
  groupId?: string;
}

/** Table rows in design order; each group folds into the row of its first run. */
export function runRows(runs: readonly Run[]): RunRow[] {
  const rows: RunRow[] = [];
  const groups = new Map<string, RunRow>();
  for (const run of runs) {
    if (!run.groupId) {
      rows.push({ id: run.key, label: runLabel(run), runs: [run] });
      continue;
    }
    const row = groups.get(run.groupId);
    if (row) row.runs.push(run);
    else {
      const created: RunRow = { id: run.groupId, label: '', runs: [run], groupId: run.groupId };
      groups.set(run.groupId, created);
      rows.push(created);
    }
  }
  for (const row of groups.values()) {
    const first = row.runs[0]!;
    const last = row.runs[row.runs.length - 1]!;
    row.label =
      row.runs.length === 1 ? runLabel(first) : `${runLabel(first)} … ${runLabel(last)} (${row.runs.length} runs)`;
  }
  return rows;
}
