import { CatalogItemSchema, type CatalogItem } from '@ill/core-schemas/catalog';
import type { Design, Run } from '@ill/core-schemas/design';
import type { Line } from '@ill/core-schemas/open-design';
import type { Load } from '@ill/core-schemas/project';

export const DATA_BY_DEALER_NOTE = 'Data by dealer';

/** The riser load id for a run. Stable, so wire tags and layout overrides survive re-derivation. */
export const loadIdFor = (run: Pick<Run, 'key'>) => `load:${run.key}`;

/**
 * Derive `project.loads` from the design's runs (plan H5). Only assigned runs become loads: the riser
 * engine needs a `fedFrom` port, and an unassigned run is a planning gap the Power step reports.
 * Tape runs carry their length; fixtures and third-party runs count as one fixture each.
 */
export function deriveLoads(design: Pick<Design, 'runs' | 'site'>): Load[] {
  const spaceNames = new Map(design.site.spaces.map((space) => [space.id, space.name]));
  return design.runs
    .filter((run) => run.assignment)
    .map((run) => {
      const load: Load = {
        id: loadIdFor(run),
        typeTag: run.lineId,
        zone: spaceNames.get(run.spaceId) ?? '',
        catalogId: run.catalogId,
        fedFrom: { ref: run.assignment!.equipmentId, port: run.assignment!.port },
        homeRunLengthFt: run.homeRunLengthFt,
        feedMethod: run.feedMethod,
        env: run.env,
      };
      if (run.lengthFt !== undefined) load.lengthFt = run.lengthFt;
      else load.qty = 1;
      if (run.feedMethod === 'multi-feed' && run.feeds !== undefined) load.feeds = run.feeds;
      if (run.source.kind === 'third-party') load.notes = DATA_BY_DEALER_NOTE;
      return load;
    });
}

/** Return the design with `project.loads` replaced by the derived loads. */
export function withDerivedLoads<T extends Pick<Design, 'runs' | 'site' | 'project'>>(design: T): T {
  return { ...design, project: { ...design.project, loads: deriveLoads(design) } };
}

/**
 * Catalog items for third-party lines (plan §9.2, D8): a `fixture` built from the dealer's numbers, so the
 * engine can load and size it. Missing numbers make it `incomplete`, and the engine says what to enter.
 */
export function dealerItems(lines: readonly Line[]): CatalogItem[] {
  const items: CatalogItem[] = [];
  for (const line of lines) {
    const data = line.thirdParty;
    if (line.kind !== 'third-party' || !data) continue;
    const name = [data.manufacturer, data.model].filter(Boolean).join(' ') || `Line ${line.lineId || line.key}`;
    const base = {
      id: `tp:${line.key}`,
      sku: `tp:${line.key}`,
      brand: data.manufacturer || 'Third party',
      model: data.model || name,
      category: 'fixture' as const,
      description: `${name} (${DATA_BY_DEALER_NOTE})`,
      isExample: false,
      source: { kind: 'user-supplied' as const, reference: DATA_BY_DEALER_NOTE },
      localOverrides: [],
    };
    const missing = [
      ...(data.wattsEach ? [] : ['watts']),
      ...(data.inputVoltageV ? [] : ['input voltage']),
      ...(data.voltageClass ? [] : ['voltage class']),
      ...(data.drive === 'CC' && !data.mA ? ['drive current'] : []),
    ];
    const specs = {
      kind: 'fixture' as const,
      voltageClass: data.voltageClass === 'Line Voltage' ? ('line' as const) : ('low' as const),
      inputV: data.inputVoltageV ?? 0,
      watts: data.wattsEach ?? 0,
      ...(data.drive === 'CV' || data.drive === 'CC' ? { drive: data.drive } : {}),
      ...(data.mA ? { mA: data.mA } : {}),
      dimming: data.dimming && data.dimming !== 'none' ? [data.dimming] : [],
      integralDriver: data.drive === 'Integral Driver' || data.voltageClass === 'Line Voltage',
    };
    const parsed = missing.length ? null : CatalogItemSchema.safeParse({ ...base, specs });
    items.push(
      parsed?.success
        ? parsed.data
        : CatalogItemSchema.parse({
            ...base,
            specs: {
              kind: 'incomplete',
              intendedKind: 'fixture',
              available: Object.fromEntries(Object.entries(specs).filter(([, value]) => value !== 0)),
              missingFields: missing.length ? missing : ['dealer data'],
              notes: ['Enter the missing numbers on the schedule line'],
            },
          }),
    );
  }
  return items;
}
