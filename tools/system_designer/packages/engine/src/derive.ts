import type { Design, Run } from '@ill/core-schemas/design';
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
