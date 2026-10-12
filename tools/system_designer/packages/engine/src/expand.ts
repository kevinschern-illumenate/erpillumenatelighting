import type { Run, Space } from '@ill/core-schemas/design';
import type { Builds, Line } from '@ill/core-schemas/open-design';

export interface ExpandOptions {
  /** Lines with at least this quantity get one `groupId`, so the Runs list can fold them (H8.1). */
  groupThresholdQty: number;
  /** Home-run estimate for a run in the same space as its supply (Settings). */
  defaultHomeRunFt: number;
}

export interface Skipped {
  key: string;
  reason: string;
}

export interface Expansion {
  spaces: Space[];
  runs: Run[];
  skipped: Skipped[];
}

const UNASSIGNED_SPACE = 'unassigned';

/** A space id from a schedule location ("Kitchen – Island" → "kitchen-island"). */
export function spaceIdFor(location: string): string {
  const slug = location
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60);
  return slug ? `space-${slug}` : UNASSIGNED_SPACE;
}

/** One space per distinct line location, in schedule order; lines without one share one "Project" space (H9). */
export function spacesFromLines(lines: Line[]): Space[] {
  const spaces = new Map<string, Space>();
  for (const line of lines) {
    if (line.kind !== 'configured' && line.kind !== 'third-party') continue;
    const id = spaceIdFor(line.location);
    if (!spaces.has(id))
      spaces.set(id, {
        id,
        name: line.location.trim() || 'Project',
        level: '',
        type: 'other',
        archetype: 'none',
        env: 'dry-concealed',
      });
  }
  return [...spaces.values()];
}

/**
 * Schedule lines → design runs (plan H8.1). Each line copy (`qty`) repeats its build's electrical runs;
 * keys are `{line}:{copy}:{run}` so they survive re-expansion. Write-back, accessory and unconfigured
 * lines yield nothing; third-party lines with watts yield one end-fed run each (D8).
 */
export function expandRuns(lines: Line[], builds: Builds, options: ExpandOptions): Expansion {
  const spaces = spacesFromLines(lines);
  const envBySpace = new Map(spaces.map((space) => [space.id, space.env]));
  const runs: Run[] = [];
  const skipped: Skipped[] = [];
  for (const line of lines) {
    const spaceId = spaceIdFor(line.location);
    const groupId = line.qty >= options.groupThresholdQty ? `grp-${line.key}` : undefined;
    const base = {
      lineKey: line.key,
      lineId: line.lineId || line.key,
      spaceId,
      homeRunLengthFt: options.defaultHomeRunFt,
      homeRunProvenance: 'estimate' as const,
      ...(groupId ? { groupId } : {}),
    };
    if (line.kind === 'third-party') {
      const watts = line.thirdParty?.wattsEach;
      if (!watts) {
        skipped.push({ key: line.key, reason: 'Enter the watts for this fixture' });
        continue;
      }
      for (let copy = 1; copy <= line.qty; copy += 1)
        runs.push({
          ...base,
          key: `${line.key}:${copy}:1`,
          buildIndex: copy,
          runIndex: 1,
          source: { kind: 'third-party' },
          catalogId: `tp:${line.key}`,
          watts,
          feedMethod: 'end',
          env: envBySpace.get(spaceId) ?? 'dry-concealed',
        });
      continue;
    }
    if (line.kind !== 'configured' || !line.configured) continue;
    const build = builds[line.configured.doctype]?.[line.configured.name];
    if (!build) {
      skipped.push({ key: line.key, reason: 'The configured record is missing' });
      continue;
    }
    if (build.issues.length || !build.configHash) {
      skipped.push({ key: line.key, reason: build.issues.join('; ') || 'The build has no hash' });
      continue;
    }
    const usable = build.runs.filter((run) => run.watts > 0);
    if (usable.length < build.runs.length) skipped.push({ key: line.key, reason: 'Runs without watts were left out' });
    for (let copy = 1; copy <= line.qty; copy += 1)
      for (const run of usable) {
        const designRun: Run = {
          ...base,
          key: `${line.key}:${copy}:${run.runIndex}`,
          buildIndex: copy,
          runIndex: run.runIndex,
          source: {
            kind: 'configured',
            doctype: build.doctype,
            name: build.name,
            configHash: build.configHash,
          },
          catalogId: build.catalogId ?? `gap:${build.doctype}:${build.name}`,
          watts: run.watts,
          feedMethod: run.feedMethod,
          env: build.environment ?? envBySpace.get(spaceId) ?? 'dry-concealed',
        };
        if (run.lengthFt !== null) designRun.lengthFt = run.lengthFt;
        if (run.feeds !== undefined) designRun.feeds = run.feeds;
        runs.push(designRun);
      }
  }
  return { spaces, runs, skipped };
}
