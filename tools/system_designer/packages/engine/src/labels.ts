import type { Run } from '@ill/core-schemas/design';
import type { Builds, Line } from '@ill/core-schemas/open-design';

/**
 * Run labels the dealer recognizes: the part number the fixture schedule shows, then `.1`, `.2`, `.3`…
 * for each run of that part number in design order (copies of a line and repeated part numbers keep
 * counting, so every label is unique). Runs with no part number keep the line-based `runLabel`.
 */

/** The part number a run's schedule line shows: a group member's own, else the build's, else a third-party model. */
export function runPartNumber(
  run: Pick<Run, 'lineKey' | 'runIndex' | 'source'>,
  lines: ReadonlyMap<string, Line>,
  builds: Builds,
): string | undefined {
  if (run.source.kind === 'third-party') return lines.get(run.lineKey)?.thirdParty?.model?.trim() || undefined;
  const build = builds[run.source.doctype]?.[run.source.name];
  if (!build) return undefined;
  const own = build.runs.find((row) => row.runIndex === run.runIndex)?.partNumber;
  // A group's build-level part number lists every member's; only a member's own names one run.
  return (own || (build.family === 'group' ? undefined : build.partNumber))?.trim() || undefined;
}

/** Runs with `label` set from the current schedule; unchanged runs keep their object. */
export function labelRuns<T extends Run>(runs: readonly T[], lines: readonly Line[], builds: Builds): T[] {
  const byKey = new Map(lines.map((line) => [line.key, line]));
  const counts = new Map<string, number>();
  return runs.map((run) => {
    const partNumber = runPartNumber(run, byKey, builds);
    let label: string | undefined;
    if (partNumber) {
      const count = (counts.get(partNumber) ?? 0) + 1;
      counts.set(partNumber, count);
      label = `${partNumber}.${count}`.slice(0, 200);
    }
    if (run.label === label) return run;
    const next = { ...run };
    if (label) next.label = label;
    else delete next.label;
    return next;
  });
}
