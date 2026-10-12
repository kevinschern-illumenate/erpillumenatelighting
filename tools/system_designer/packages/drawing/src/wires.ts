import type { LibrarySnapshot } from '@ill/core-schemas/library';
import type { WireType } from '@ill/core-schemas/wire';
import type { EngineResult, RunResult } from '@ill/engine/model';
import { controlName } from './layout/continuations';

/** Low-voltage power runs; parallel ones between the same two terminals are drawn as one line. */
export const LOW_VOLTAGE_TYPES: readonly string[] = ['class2-dc', 'class2-dc-multichannel'];

/**
 * Runs as they are drawn, keyed by the run that stands for them. Low-voltage runs from the same output
 * to the same load (a double-end feed, for example) become one line whose callout counts every
 * conductor; the schedules keep each run.
 */
export interface DrawnRuns {
  result: EngineResult;
  members: Map<string, RunResult[]>;
}

export function drawnRuns(result: EngineResult): DrawnRuns {
  const groups = new Map<string, RunResult[]>();
  for (const run of result.runs) {
    const key = LOW_VOLTAGE_TYPES.includes(run.type)
      ? [
          run.type,
          run.from.id,
          run.from.port ?? '',
          run.to.id,
          run.to.port ?? '',
          run.wireTypeId ?? '',
        ].join('|')
      : run.runId;
    groups.set(key, [...(groups.get(key) ?? []), run]);
  }
  const members = new Map<string, RunResult[]>();
  const runs = [...groups.values()].map((group) => {
    const first = group[0]!;
    members.set(first.runId, group);
    if (group.length === 1) return first;
    const vd = group.map((run) => run.vdPct).filter((value): value is number => value !== null);
    return {
      ...first,
      tag: group.map((run) => run.tag).join(', '),
      lengthFt: Math.max(...group.map((run) => run.lengthFt)),
      vdPct: vd.length ? Math.max(...vd) : null,
    };
  });
  return { result: { ...result, runs }, members };
}

const wireOf = (library: LibrarySnapshot, run: RunResult): WireType | undefined =>
  library.wires.find((wire) => wire.id === run.wireTypeId);

/** Conductors in all of a line's runs, or `null` when one has no valid wire. */
export function conductorCount(
  library: LibrarySnapshot,
  runs: readonly RunResult[],
): number | null {
  let total = 0;
  for (const run of runs) {
    const wire = wireOf(library, run);
    if (!wire) return null;
    total +=
      wire.conductors.reduce((sum, group) => sum + group.count, 0) * Math.max(1, run.parallelSets);
  }
  return total;
}

/** The gauge of a wire's power conductors (or its first conductors), e.g. `18 AWG`. */
export function wireGauge(wire: WireType | undefined): string | null {
  const group = wire?.conductors.find((item) => item.role === 'power') ?? wire?.conductors[0];
  return group ? `${group.awg} AWG` : null;
}

const conductorsText = (count: number | null) => (count === null ? '' : ` · ${count} COND`);

/** The engineering callout's `{wireLabel}`: the wire, how many runs share the line, and the conductors. */
export function riserWireLabel(library: LibrarySnapshot, runs: readonly RunResult[]): string {
  const first = runs[0]!;
  const label = wireOf(library, first)?.riserLabel ?? 'NO VALID WIRE';
  if (!LOW_VOLTAGE_TYPES.includes(first.type)) return label;
  return `${runs.length > 1 ? `${runs.length} × ` : ''}${label}${conductorsText(conductorCount(library, runs))}`;
}

/** Friendly wire names for the client diagram. */
export function clientWireName(run: RunResult): string {
  if (LOW_VOLTAGE_TYPES.includes(run.type)) return 'LV Wire';
  if (run.type === 'landscape-ac') return 'Landscape Wire';
  if (run.type.startsWith('lv-')) return 'Line Voltage';
  return `${controlName(run)} Wire`;
}

/** The client diagram's callouts, longest first: name, recommended gauge and conductors. */
export function clientWireLabels(library: LibrarySnapshot, runs: readonly RunResult[]): string[] {
  const first = runs[0]!;
  const name = clientWireName(first);
  if (first.type.startsWith('lv-')) return [`${name} · by electrician`, name];
  const gauge = wireGauge(wireOf(library, first));
  const count = conductorCount(library, runs);
  const full = [
    name,
    gauge ?? 'gauge to be confirmed',
    ...(count === null ? [] : [`${count} conductors`]),
  ].join(' · ');
  return [...new Set([full, gauge ? `${name} · ${gauge}` : name, name])];
}
