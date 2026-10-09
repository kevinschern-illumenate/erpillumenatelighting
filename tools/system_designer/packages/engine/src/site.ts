import type { Cabinet, Design, EnvChoice, Run, Space } from '@ill/core-schemas/design';
import type { Source } from '@ill/core-schemas/project';
import { choiceOf, environmentOption } from '@ill/data/environments';

/**
 * Site model edits (plan §8, WP-3.2). Each function changes the design it is given, so the app calls
 * them inside an immer recipe (one undo step) and tests call them on a copy.
 */

export type DistancePick = 'same-space' | 'adjacent' | 'other-level';

export interface DistanceDefaults {
  sameSpaceFt: number;
  adjacentFt: number;
  otherLevelFt: number;
}

export const DISTANCE_LABELS: Record<DistancePick, string> = {
  'same-space': 'Same space',
  adjacent: 'Adjacent space',
  'other-level': 'Other level',
};

/** Plan §8 quick picks, from Settings when set. */
export function distanceDefaults(settings: Record<string, unknown>): DistanceDefaults {
  const value = (key: string, fallback: number) => {
    const number = settings[key];
    return typeof number === 'number' && Number.isFinite(number) && number >= 0 ? number : fallback;
  };
  return {
    sameSpaceFt: value('default_distance_same_space_ft', 10),
    adjacentFt: value('default_distance_adjacent_ft', 25),
    otherLevelFt: value('default_distance_other_level_ft', 40),
  };
}

export function pickLength(pick: DistancePick, defaults: DistanceDefaults): number {
  return pick === 'same-space'
    ? defaults.sameSpaceFt
    : pick === 'adjacent'
      ? defaults.adjacentFt
      : defaults.otherLevelFt;
}

function setEnv(record: Space | Cabinet | Run, choice: EnvChoice) {
  record.env = environmentOption(choice).engine;
  record.envChoice = choice;
}

function space(design: Design, spaceId: string): Space {
  const found = design.site.spaces.find((item) => item.id === spaceId);
  if (!found) throw new Error(`Unknown space: ${spaceId}`);
  return found;
}

/**
 * Change a space's environment. Cabinets and runs in the space that still follow it (same choice as
 * the space had) follow the change; ones set on their own keep their environment.
 */
export function setSpaceEnvironment(design: Design, spaceId: string, choice: EnvChoice) {
  const target = space(design, spaceId);
  const previous = choiceOf(target);
  setEnv(target, choice);
  for (const cabinet of design.site.cabinets)
    if (cabinet.spaceId === spaceId && choiceOf(cabinet) === previous) {
      setEnv(cabinet, choice);
      cabinet.locationRating = environmentOption(choice).locationRating;
    }
  for (const run of design.runs) if (run.spaceId === spaceId && choiceOf(run) === previous) setEnv(run, choice);
}

export function setCabinetEnvironment(design: Design, cabinetId: string, choice: EnvChoice) {
  const cabinet = design.site.cabinets.find((item) => item.id === cabinetId);
  if (!cabinet) throw new Error(`Unknown cabinet: ${cabinetId}`);
  setEnv(cabinet, choice);
  cabinet.locationRating = environmentOption(choice).locationRating;
}

export function setRunEnvironment(design: Design, runKeys: readonly string[], choice: EnvChoice) {
  const keys = new Set(runKeys);
  for (const run of design.runs) if (keys.has(run.key)) setEnv(run, choice);
}

export function renameSpace(design: Design, spaceId: string, name: string, level?: string) {
  const target = space(design, spaceId);
  const trimmed = name.trim();
  if (!trimmed) throw new Error('Enter a space name');
  target.name = trimmed.slice(0, 120);
  if (level !== undefined) target.level = level.trim().slice(0, 60);
}

/** Merge `fromId` into `intoId`: its runs and cabinets move, then it is removed. */
export function mergeSpaces(design: Design, fromId: string, intoId: string) {
  if (fromId === intoId) throw new Error('Choose a different space to merge into');
  space(design, fromId);
  space(design, intoId);
  for (const run of design.runs) if (run.spaceId === fromId) run.spaceId = intoId;
  for (const cabinet of design.site.cabinets) if (cabinet.spaceId === fromId) cabinet.spaceId = intoId;
  design.site.spaces = design.site.spaces.filter((item) => item.id !== fromId);
}

function nextNumber(values: readonly string[], prefix: string) {
  const used = values
    .map((value) => value.match(new RegExp(`^${prefix}(\\d+)$`))?.[1])
    .filter((value): value is string => value !== undefined)
    .map(Number);
  return used.length ? Math.max(...used) + 1 : 1;
}

/** A new supply cabinet in a space, taking the space's environment. Returns its id. */
export function addCabinet(design: Design, spaceId: string, defaults: DistanceDefaults): string {
  const home = space(design, spaceId);
  const number = nextNumber(
    design.site.cabinets.map((item) => item.tag),
    'C-',
  );
  const choice = choiceOf(home);
  const cabinet: Cabinet = {
    id: `cab-${number}`,
    tag: `C-${number}`,
    name: `${home.name} cabinet`.slice(0, 120),
    spaceId,
    locationRating: environmentOption(choice).locationRating,
    env: environmentOption(choice).engine,
    envChoice: choice,
    accessNote: '',
    feedLengthFt: defaults.sameSpaceFt,
    feedLengthProvenance: 'estimate',
  };
  while (design.site.cabinets.some((item) => item.id === cabinet.id)) cabinet.id += 'x';
  design.site.cabinets.push(cabinet);
  return cabinet.id;
}

export function updateCabinet(
  design: Design,
  cabinetId: string,
  changes: Partial<Pick<Cabinet, 'name' | 'tag' | 'spaceId' | 'accessNote' | 'sourceId' | 'locationRating'>>,
) {
  const cabinet = design.site.cabinets.find((item) => item.id === cabinetId);
  if (!cabinet) throw new Error(`Unknown cabinet: ${cabinetId}`);
  if (changes.spaceId !== undefined) space(design, changes.spaceId);
  if (changes.sourceId && !design.project.sources.some((source) => source.id === changes.sourceId))
    throw new Error(`Unknown circuit: ${changes.sourceId}`);
  if (changes.tag !== undefined) {
    const tag = changes.tag.trim();
    if (!tag) throw new Error('Enter a cabinet tag');
    if (design.site.cabinets.some((item) => item.id !== cabinetId && item.tag === tag))
      throw new Error(`Another cabinet is already ${tag}`);
    changes = { ...changes, tag };
  }
  Object.assign(cabinet, changes);
  if ('sourceId' in changes && !changes.sourceId) delete cabinet.sourceId;
}

/** Remove a cabinet that holds no equipment yet. */
export function removeCabinet(design: Design, cabinetId: string) {
  const inside = design.project.equipment.filter((item) => item.enclosure === cabinetId).length;
  if (inside) throw new Error(`Move the ${inside === 1 ? 'supply' : `${inside} supplies`} out of this cabinet first`);
  design.site.cabinets = design.site.cabinets.filter((item) => item.id !== cabinetId);
}

/** Home-run length (run to its supply) for some runs: a quick pick is an estimate, a typed value is entered. */
export function setHomeRuns(design: Design, runKeys: readonly string[], lengthFt: number, picked: boolean) {
  if (!Number.isFinite(lengthFt) || lengthFt < 0) throw new Error('Enter a length of 0 ft or more');
  const keys = new Set(runKeys);
  for (const run of design.runs)
    if (keys.has(run.key)) {
      run.homeRunLengthFt = lengthFt;
      run.homeRunProvenance = picked ? 'estimate' : 'entered';
    }
}

/** Feed length (cabinet to its circuit), with the same provenance rule. */
export function setCabinetFeed(design: Design, cabinetId: string, lengthFt: number, picked: boolean) {
  if (!Number.isFinite(lengthFt) || lengthFt < 0) throw new Error('Enter a length of 0 ft or more');
  const cabinet = design.site.cabinets.find((item) => item.id === cabinetId);
  if (!cabinet) throw new Error(`Unknown cabinet: ${cabinetId}`);
  cabinet.feedLengthFt = lengthFt;
  cabinet.feedLengthProvenance = picked ? 'estimate' : 'entered';
}

/** A new panel circuit (riser source). Returns its id. */
export function addCircuit(design: Design, panel = 'LP-1'): string {
  const number = nextNumber(
    design.project.sources.map((item) => item.tag),
    'CKT-',
  );
  const source: Source = {
    id: `src-${number}`,
    tag: `CKT-${number}`,
    panel,
    circuit: String(number),
    voltage: 120,
    phase: '1PH',
    breakerA: 20,
    poles: 1,
  };
  while (design.project.sources.some((item) => item.id === source.id)) source.id += 'x';
  design.project.sources.push(source);
  return source.id;
}

export function updateCircuit(
  design: Design,
  sourceId: string,
  changes: Partial<Pick<Source, 'panel' | 'circuit' | 'voltage' | 'breakerA' | 'phase' | 'poles'>>,
) {
  const source = design.project.sources.find((item) => item.id === sourceId);
  if (!source) throw new Error(`Unknown circuit: ${sourceId}`);
  Object.assign(source, changes);
}

/** Remove a circuit; cabinets on it lose the link, and one feeding equipment is refused. */
export function removeCircuit(design: Design, sourceId: string) {
  const source = design.project.sources.find((item) => item.id === sourceId);
  const refs = new Set([sourceId, source?.tag]);
  if (design.project.equipment.some((item) => refs.has(item.fedFrom.ref)))
    throw new Error('Equipment is fed from this circuit; move it first');
  design.project.sources = design.project.sources.filter((item) => item.id !== sourceId);
  for (const cabinet of design.site.cabinets) if (cabinet.sourceId === sourceId) delete cabinet.sourceId;
}
