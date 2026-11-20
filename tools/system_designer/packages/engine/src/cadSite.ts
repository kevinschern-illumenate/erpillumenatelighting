import { z } from 'zod';
import { EnvChoiceSchema, FeedMethodSchema, type Cabinet, type Design, type EnvChoice } from '@ill/core-schemas/design';
import { environmentOption } from '@ill/data/environments';
import { spaceIdFor } from './expand';

/**
 * The drawing a schedule was imported from (`cad-site/1`, draw-to-quote plan 2.3): rooms, cabinets and
 * measured home-run lengths per schedule line. The portal drawing import stores it; a new design starts
 * from it. Spaces are matched by room name, because the import sets each line's location to its room
 * and the designer makes one space per location (`spaceIdFor`).
 */
export const CadSiteSchema = z.object({
  schema: z.literal('cad-site/1'),
  import: z.string().nullish(),
  drawing: z.object({ file: z.string().nullish(), rev: z.number().nullish(), hash: z.string().nullish() }).partial(),
  rooms: z
    .array(
      z.object({
        id: z.string(),
        name: z.string().min(1).max(120),
        level: z.string().max(60).default(''),
        envChoice: EnvChoiceSchema.nullish(),
      }),
    )
    .default([]),
  cabinets: z
    .array(
      z.object({
        id: z.string().min(1).max(160),
        room: z.string().nullish(),
        locationRating: z.enum(['Dry', 'Damp', 'Wet']).default('Dry'),
        accessNote: z.string().max(300).default(''),
        feedLengthFt: z.number().finite().nonnegative().default(0),
      }),
    )
    .default([]),
  lines: z
    .record(
      z.string(),
      z.object({
        runId: z.string(),
        room: z.string().nullish(),
        cabinet: z.string().nullish(),
        feedMethod: FeedMethodSchema.default('end'),
        homeRunLengthFt: z.number().finite().nonnegative().optional(),
      }),
    )
    .default({}),
});
export type CadSite = z.infer<typeof CadSiteSchema>;

export interface CadSiteResult {
  spaces: number;
  cabinets: number;
  runs: number;
  /** Lines of the drawing that have no run in the design (unconfigured or skipped lines). */
  unmatchedLines: string[];
}

const RATING_CHOICE: Record<'Dry' | 'Damp' | 'Wet', EnvChoice> = { Dry: 'dry-concealed', Damp: 'damp', Wet: 'wet' };

/** Apply the drawing's site to `design` in place (call it inside an immer recipe, or on a copy). */
export function applyCadSite(design: Design, site: CadSite): CadSiteResult {
  const result: CadSiteResult = { spaces: 0, cabinets: 0, runs: 0, unmatchedLines: [] };
  const spaces = new Map(design.site.spaces.map((space) => [space.id, space]));
  for (const room of site.rooms) {
    const id = spaceIdFor(room.name);
    let space = spaces.get(id);
    if (!space) {
      space = { id, name: room.name, level: '', type: 'other', archetype: 'none', env: 'dry-concealed' };
      design.site.spaces.push(space);
      spaces.set(id, space);
    }
    space.level = room.level.slice(0, 60);
    if (room.envChoice) {
      space.env = environmentOption(room.envChoice).engine;
      space.envChoice = room.envChoice;
    }
    result.spaces += 1;
  }
  const fallbackSpace = design.site.spaces[0]?.id;
  for (const item of site.cabinets) {
    if (design.site.cabinets.some((cabinet) => cabinet.id === item.id)) continue;
    const spaceId = item.room ? spaceIdFor(item.room) : fallbackSpace;
    const space = spaceId ? spaces.get(spaceId) : undefined;
    if (!space) continue;
    const choice = space.envChoice ?? RATING_CHOICE[item.locationRating];
    const cabinet: Cabinet = {
      id: item.id,
      tag: item.id,
      name: `${space.name} ${item.id}`.slice(0, 120),
      spaceId: space.id,
      locationRating: item.locationRating,
      env: environmentOption(choice).engine,
      envChoice: choice,
      accessNote: item.accessNote,
      feedLengthFt: item.feedLengthFt,
      feedLengthProvenance: item.feedLengthFt > 0 ? 'measured' : 'estimate',
    };
    design.site.cabinets.push(cabinet);
    result.cabinets += 1;
  }
  const seen = new Set<string>();
  for (const run of design.runs) {
    const line = site.lines[run.lineKey];
    if (!line) continue;
    seen.add(run.lineKey);
    if (line.room) {
      const space = spaces.get(spaceIdFor(line.room));
      if (space) {
        run.spaceId = space.id;
        run.env = space.env;
        if (space.envChoice) run.envChoice = space.envChoice;
      }
    }
    if (line.homeRunLengthFt !== undefined) {
      run.homeRunLengthFt = line.homeRunLengthFt;
      run.homeRunProvenance = 'measured';
    }
    run.feedMethod = line.feedMethod;
    result.runs += 1;
  }
  result.unmatchedLines = Object.keys(site.lines).filter((key) => !seen.has(key));
  return result;
}
