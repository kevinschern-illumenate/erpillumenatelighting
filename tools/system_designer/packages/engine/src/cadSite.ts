import { z } from 'zod';
import { EquipmentCategorySchema } from '@ill/core-schemas/common';
import {
  EnvChoiceSchema,
  FeedMethodSchema,
  ZoneSchema,
  type Cabinet,
  type Design,
  type EnvChoice,
} from '@ill/core-schemas/design';
import type { Equipment } from '@ill/core-schemas/project';
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
  /** Controls in v1: each drawn control's schedule line, catalog item, cabinet and DMX address. */
  controls: z
    .record(
      z.string(),
      z.object({
        lineKey: z.string().min(1),
        catalogId: z.string().min(1),
        category: EquipmentCategorySchema,
        cabinet: z.string().nullish(),
        room: z.string().nullish(),
        dmx: z
          .object({
            universe: z.number().int().min(1).max(63999),
            start_address: z.union([z.number().int().min(1).max(512), z.literal('auto')]).default('auto'),
          })
          .nullish(),
        controlFrom: z.string().nullish(),
      }),
    )
    .default({}),
  zones: z
    .array(
      z.object({
        id: z.string().min(1).max(160),
        name: z.string().min(1).max(120),
        method: ZoneSchema.shape.method,
        control: z.object({ id: z.string(), port: z.string() }).nullish(),
        lines: z.array(z.string()).default([]),
      }),
    )
    .default([]),
});
export type CadSite = z.infer<typeof CadSiteSchema>;

/** Patch length inside one cabinet and the estimate between cabinets (as `controls.ts`). */
const PATCH_FT = 3;
const CROSS_CABINET_FT = 25;
const ZONE_COLORS = ['#00588c', '#d97706', '#15803d', '#7c3aed', '#be123c', '#0f766e', '#a16207', '#4338ca'];
const RECEIVES_DMX = new Set(['dmx-decoder', 'dmx-0-10v-converter']);

export interface CadSiteResult {
  spaces: number;
  cabinets: number;
  runs: number;
  controls: number;
  zones: number;
  /** Lines of the drawing that have no run in the design (unconfigured or skipped lines). */
  unmatchedLines: string[];
}

const RATING_CHOICE: Record<'Dry' | 'Damp' | 'Wet', EnvChoice> = { Dry: 'dry-concealed', Damp: 'damp', Wet: 'wet' };

/** Apply the drawing's site to `design` in place (call it inside an immer recipe, or on a copy). */
export function applyCadSite(design: Design, site: CadSite): CadSiteResult {
  const result: CadSiteResult = { spaces: 0, cabinets: 0, runs: 0, controls: 0, zones: 0, unmatchedLines: [] };
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
  result.controls = applyControls(design, site, spaces);
  result.zones = applyZones(design, site);
  return result;
}

/**
 * The drawn controls as design equipment, tied to their schedule lines (`scheduleLine`) so the power
 * board's schedule sync keeps them instead of adding them again. They wait for power (`unassigned`):
 * the board's "power controls" step feeds them from their cabinet.
 */
function applyControls(design: Design, site: CadSite, spaces: Map<string, Design['site']['spaces'][number]>) {
  let added = 0;
  const entries = Object.entries(site.controls);
  for (const [id, control] of entries) {
    if (design.project.equipment.some((item) => item.id === id || item.scheduleLine === control.lineKey)) continue;
    const cabinet = control.cabinet ? design.site.cabinets.find((item) => item.id === control.cabinet) : undefined;
    const space = control.room ? spaces.get(spaceIdFor(control.room)) : undefined;
    const equipment: Equipment = {
      id,
      tag: id,
      catalogId: control.catalogId,
      category: control.category,
      qty: 1,
      location: (cabinet?.name || cabinet?.tag || control.room || id).slice(0, 300),
      ...(cabinet ? { enclosure: cabinet.id } : {}),
      fedFrom: { ref: 'unassigned' },
      feedLengthFt: PATCH_FT,
      env: cabinet?.env ?? space?.env ?? 'dry-concealed',
      scheduleLine: control.lineKey,
      ...(RECEIVES_DMX.has(control.category)
        ? { dmx: { universe: control.dmx?.universe ?? 1, startAddress: control.dmx?.start_address ?? ('auto' as const) } }
        : {}),
    };
    design.project.equipment.push(equipment);
    added += 1;
  }
  for (const [id, control] of entries) {
    if (!control.controlFrom) continue;
    const target = design.project.equipment.find((item) => item.id === id);
    const source = design.project.equipment.find((item) => item.id === control.controlFrom);
    if (!target || !source || target.controlFrom) continue;
    target.controlFrom = { ref: source.id };
    target.controlLengthFt = source.enclosure && source.enclosure === target.enclosure ? PATCH_FT : CROSS_CABINET_FT;
  }
  return added;
}

/** Zones as drawn: each names its control output, and its runs (by schedule line) join it. */
function applyZones(design: Design, site: CadSite) {
  let added = 0;
  for (const zone of site.zones) {
    if (design.zones.some((item) => item.id === zone.id)) continue;
    const control = zone.control && design.project.equipment.some((item) => item.id === zone.control!.id)
      ? { equipmentId: zone.control.id, port: zone.control.port }
      : undefined;
    design.zones.push({
      id: zone.id,
      name: zone.name,
      color: ZONE_COLORS[design.zones.length % ZONE_COLORS.length]!,
      method: zone.method,
      ...(control ? { control } : {}),
    });
    const lines = new Set(zone.lines);
    for (const run of design.runs) if (lines.has(run.lineKey) && !run.zoneId) run.zoneId = zone.id;
    added += 1;
  }
  return added;
}
