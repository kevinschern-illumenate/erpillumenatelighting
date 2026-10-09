import type { Design } from '@ill/core-schemas/design';
import type { Builds, Line } from '@ill/core-schemas/open-design';
import type { Project } from '@ill/core-schemas/project';
import type { ClientFixtureRow, ClientLoad, ClientProductType, DrawingOptions } from '@ill/drawing/options';

/** The client diagram's family for a schedule line: what the dealer picked, else what was configured. */
export function lineFamily(line: Line, builds: Builds): ClientProductType {
  if (line.kind === 'third-party') return 'fixture';
  const type = (line.productType ?? '').toLowerCase();
  if (type.includes('neon')) return 'neon';
  if (type.includes('sheet')) return 'sheet';
  if (type.includes('tape')) return 'tape';
  if (type.includes('linear') || type.includes('extrusion')) return 'linear';
  const build = line.configured ? builds[line.configured.doctype]?.[line.configured.name] : undefined;
  if (build?.family === 'linear') return 'linear';
  if (build?.family === 'sheet') return 'sheet';
  if (build) return 'tape';
  return 'fixture';
}

/** The part number a client sees: the configured product's own (a fixture's, never its tape's). */
export function linePartNumber(line: Line, builds: Builds): string | undefined {
  if (line.kind === 'third-party') return line.thirdParty?.model || undefined;
  if (line.kind === 'accessory') return line.accessoryItem || undefined;
  const build = line.configured ? builds[line.configured.doctype]?.[line.configured.name] : undefined;
  return build?.partNumber || undefined;
}

function productName(line: Line): string {
  if (line.kind === 'third-party')
    return [line.thirdParty?.manufacturer, line.thirdParty?.model].filter(Boolean).join(' ') || 'Fixture';
  if (line.kind === 'accessory') return line.productType || 'Accessory';
  return line.productType || 'Fixture';
}

/**
 * Inputs for the client diagram (plan §12.2): every load's family and part number, and the fixture schedule
 * the dealer made. Power supplies the designer wrote back to the schedule are on the diagram already.
 */
export function clientOptions(
  lines: readonly Line[],
  builds: Builds,
  design: Design,
  project: Project,
): DrawingOptions {
  const byKey = new Map(lines.map((line) => [line.key, line]));
  // Load ids are `load:<run key>` (engine `loadIdFor`).
  const lineOf = new Map(design.runs.map((run) => [`load:${run.key}`, byKey.get(run.lineKey)]));
  const loads: Record<string, ClientLoad> = {};
  for (const load of project.loads) {
    const line = lineOf.get(load.id);
    if (!line) continue;
    const partNumber = linePartNumber(line, builds);
    loads[load.id] = { type: lineFamily(line, builds), ...(partNumber ? { partNumber } : {}) };
  }
  const fixtureSchedule: ClientFixtureRow[] = lines
    .filter((line) => line.kind !== 'writeback')
    .map((line) => ({
      type: line.lineId || String(line.idx),
      product: productName(line),
      partNumber: linePartNumber(line, builds) ?? (line.kind === 'unconfigured' ? 'Not configured yet' : '—'),
      qty: String(line.qty),
      location: line.location,
    }));
  return { style: 'client', loads, fixtureSchedule };
}
