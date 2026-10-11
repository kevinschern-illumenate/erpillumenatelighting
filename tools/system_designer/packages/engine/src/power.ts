import type { CatalogItem } from '@ill/core-schemas/catalog';
import type { Protocol } from '@ill/core-schemas/common';
import type { Cabinet, Design, Run, Zone } from '@ill/core-schemas/design';
import type { Builds, Line } from '@ill/core-schemas/open-design';
import type { Equipment } from '@ill/core-schemas/project';
import { DMX_PROTOCOLS, PHASE_PROTOCOLS } from '@ill/data/protocols';
import { round } from './messages';
import { spaceIdFor } from './expand';
import { buildFor, runLabel } from './runs';

/**
 * Power board edits (plan §10.1–10.2, §10.5, WP-3.4). Like `site.ts`, each function changes the design it
 * is given; the app calls them inside one undoable store edit. Supplies are sized against
 * `ratedW × usableLoadFactor` per supply and `maxW × usableLoadFactor` per output (the ERP derate, A.2);
 * a supply without a factor uses the project operating target. Nothing here sees a price (D6).
 */

export interface PowerContext {
  catalog: ReadonlyMap<string, CatalogItem>;
  lines: readonly Line[];
  builds: Builds;
}

type PowerSpecs = Extract<CatalogItem['specs'], { kind: 'psu' | 'driver' }>;

/** Methods the supply itself dims; DMX, wireless and Lutron zones dim through other devices. */
export const SUPPLY_DIMMED: ReadonlySet<Protocol> = new Set(['phase-forward', 'phase-reverse', '0-10V', 'DALI-2']);

export const ZONE_METHODS: readonly { id: Zone['method']; label: string }[] = [
  { id: 'phase-forward', label: 'Phase forward (TRIAC)' },
  { id: 'phase-reverse', label: 'Phase reverse (ELV)' },
  { id: '0-10V', label: '0-10V' },
  { id: 'DALI-2', label: 'DALI-2' },
  { id: 'DMX512', label: 'DMX512' },
  { id: 'Lutron-QS', label: 'Lutron QS' },
  { id: 'Lutron-EcoSystem', label: 'Lutron EcoSystem' },
  { id: 'CRMX-wireless', label: 'Wireless (CRMX)' },
  { id: 'none', label: 'Switched, no dimming' },
];

const ZONE_COLORS = ['#00588c', '#d97706', '#15803d', '#7c3aed', '#be123c', '#0f766e', '#a16207', '#4338ca'];

export const catalogMap = (items: readonly CatalogItem[]) => new Map(items.map((item) => [item.id, item]));

export function powerSpecs(item: CatalogItem | undefined): PowerSpecs | null {
  return item && (item.specs.kind === 'psu' || item.specs.kind === 'driver') ? item.specs : null;
}

/** Usable watts for a supply and each output, from the ERP factor or the project target. */
export function capacity(specs: PowerSpecs, deratePct: number) {
  const factor = specs.usableLoadFactor ?? deratePct / 100;
  return {
    factor,
    usableW: round(specs.ratedW * factor, 2),
    outputs: specs.outputs.map((output) => ({
      name: output.name,
      class2: output.class2,
      maxW: output.maxW,
      usableW: round(output.maxW * factor, 2),
    })),
  };
}

export interface RunElectrical {
  voltage: number | null;
  lineVoltage: boolean;
  protocols: Protocol[];
}

/** What a run needs from a supply: its tape or fixture voltage and the protocols its product dims by. */
export function runElectrical(run: Run, context: PowerContext): RunElectrical {
  if (run.source.kind === 'third-party') {
    const data = context.lines.find((line) => line.key === run.lineKey)?.thirdParty;
    return {
      voltage: data?.inputVoltageV ?? null,
      lineVoltage: data?.voltageClass === 'Line Voltage',
      protocols: data?.dimming && data.dimming !== 'none' ? [data.dimming] : [],
    };
  }
  const tape = context.catalog.get(run.catalogId)?.specs;
  return {
    voltage: tape?.kind === 'tape' ? tape.voltage : null,
    lineVoltage: false,
    protocols: (buildFor(run, context.builds)?.protocols ?? []).filter((item) => item !== 'none'),
  };
}

/** Watts on each output of a supply. Runs on an unknown port count against the first output. */
export function outputLoads(design: Design, equipmentId: string, ignore: ReadonlySet<string> = new Set()) {
  const loads = new Map<string, number>();
  for (const run of design.runs)
    if (run.assignment?.equipmentId === equipmentId && !ignore.has(run.key))
      loads.set(run.assignment.port, (loads.get(run.assignment.port) ?? 0) + run.watts);
  return loads;
}

const sum = (values: Iterable<number>) => [...values].reduce((total, value) => total + value, 0);

function equipmentOf(design: Design, equipmentId: string) {
  const found = design.project.equipment.find((item) => item.id === equipmentId);
  if (!found) throw new Error(`Unknown supply: ${equipmentId}`);
  return found;
}

/** Why these runs cannot go on this output, or null when they can. */
export function assignmentProblem(
  design: Design,
  context: PowerContext,
  runKeys: readonly string[],
  equipmentId: string,
  port: string,
): string | null {
  const keys = new Set(runKeys);
  const runs = design.runs.filter((run) => keys.has(run.key));
  if (!runs.length) return 'Choose runs to assign';
  const supply = design.project.equipment.find((item) => item.id === equipmentId);
  if (!supply) return 'That supply is no longer in the design';
  const specs = powerSpecs(context.catalog.get(supply.catalogId));
  if (!specs) return `${supply.tag} has incomplete catalog data, so it cannot be loaded yet`;
  const limits = capacity(specs, design.project.settings.psuDeratePct);
  const output = limits.outputs.find((item) => item.name === port);
  if (!output) return `${supply.tag} has no output ${port}`;
  const zones = new Map(design.zones.map((zone) => [zone.id, zone]));

  for (const run of runs) {
    const label = runLabel(run);
    const needs = runElectrical(run, context);
    if (needs.lineVoltage) return `${label} is line voltage; feed it from a panel circuit, not a supply`;
    if (specs.outputType === 'CC') return `${label} needs a constant-voltage supply; ${supply.tag} is constant current`;
    if (needs.voltage !== null && specs.outputV !== undefined && needs.voltage !== specs.outputV)
      return `${label} needs ${needs.voltage} V; ${supply.tag} gives ${specs.outputV} V`;
    const dimmed = needs.protocols.filter((protocol) => SUPPLY_DIMMED.has(protocol));
    if (dimmed.length && !dimmed.some((protocol) => specs.dimming.includes(protocol)))
      return `${label} dims by ${dimmed.join(' or ')}; ${supply.tag} accepts ${specs.dimming.join(', ') || 'no dimming'}`;
    const zone = run.zoneId ? zones.get(run.zoneId) : undefined;
    if (zone && SUPPLY_DIMMED.has(zone.method) && !specs.dimming.includes(zone.method))
      return `${zone.name} dims by ${zone.method}; ${supply.tag} does not accept it`;
  }

  const sharing = design.runs.filter(
    (run) => !keys.has(run.key) && run.assignment?.equipmentId === equipmentId && run.assignment.port === port,
  );
  const zoneIds = new Set([...sharing, ...runs].map((run) => run.zoneId ?? ''));
  if (zoneIds.size > 1) return `${supply.tag}/${port} would feed more than one zone; give each zone its own output`;

  const loads = outputLoads(design, equipmentId, keys);
  const adding = sum(runs.map((run) => run.watts));
  const onOutput = (loads.get(port) ?? 0) + adding;
  if (onOutput > output.usableW)
    return `${supply.tag}/${port} would carry ${round(onOutput, 1)} W of its ${output.usableW} W usable`;
  const total = sum(loads.values()) + adding;
  if (total > limits.usableW) return `${supply.tag} would carry ${round(total, 1)} W of its ${limits.usableW} W usable`;
  return null;
}

/** Put runs on a supply output; throws the refusal reason. */
export function assignRuns(
  design: Design,
  context: PowerContext,
  runKeys: readonly string[],
  equipmentId: string,
  port: string,
) {
  const problem = assignmentProblem(design, context, runKeys, equipmentId, port);
  if (problem) throw new Error(problem);
  const keys = new Set(runKeys);
  for (const run of design.runs) if (keys.has(run.key)) run.assignment = { equipmentId, port };
}

/** The port name for a line-voltage fixture on a panel circuit. */
export const LINE_PORT = 'LINE';

/** Why these runs cannot go on this panel circuit, or null when they can (line-voltage fixtures, D8). */
export function circuitProblem(
  design: Design,
  context: PowerContext,
  runKeys: readonly string[],
  sourceId: string,
): string | null {
  const source = design.project.sources.find((item) => item.id === sourceId);
  if (!source) return 'That circuit is no longer in the design';
  const keys = new Set(runKeys);
  const runs = design.runs.filter((run) => keys.has(run.key));
  if (!runs.length) return 'Choose runs to assign';
  for (const run of runs) {
    const needs = runElectrical(run, context);
    if (!needs.lineVoltage) return `${runLabel(run)} is low voltage; put it on a supply output`;
    if (needs.voltage !== null && needs.voltage !== source.voltage)
      return `${runLabel(run)} needs ${needs.voltage} V; ${source.tag} is ${source.voltage} V`;
  }
  return null;
}

/** Feed line-voltage fixtures straight from a panel circuit; throws the refusal reason. */
export function assignToCircuit(design: Design, context: PowerContext, runKeys: readonly string[], sourceId: string) {
  const problem = circuitProblem(design, context, runKeys, sourceId);
  if (problem) throw new Error(problem);
  const keys = new Set(runKeys);
  for (const run of design.runs) if (keys.has(run.key)) run.assignment = { equipmentId: sourceId, port: LINE_PORT };
}

export function unassignRuns(design: Design, runKeys: readonly string[]) {
  const keys = new Set(runKeys);
  for (const run of design.runs) if (keys.has(run.key)) delete run.assignment;
}

function nextTag(design: Design) {
  const used = design.project.equipment
    .map((item) => item.tag.match(/^PS-(\d+)$/)?.[1])
    .filter((value): value is string => value !== undefined)
    .map(Number);
  return used.length ? Math.max(...used) + 1 : 1;
}

function cabinetOf(design: Design, cabinetId: string): Cabinet {
  const cabinet = design.site.cabinets.find((item) => item.id === cabinetId);
  if (!cabinet) throw new Error(`Unknown cabinet: ${cabinetId}`);
  return cabinet;
}

/** A new supply in a cabinet, fed from the cabinet's circuit. Returns its id. */
export function addSupply(
  design: Design,
  context: PowerContext,
  cabinetId: string,
  catalogId: string,
  notes?: string,
): string {
  const cabinet = cabinetOf(design, cabinetId);
  const item = context.catalog.get(catalogId);
  const specs = powerSpecs(item);
  if (!item || !specs) throw new Error('Choose a supply from the ilLumenate catalog');
  const number = nextTag(design);
  const supply: Equipment = {
    id: `PS-${number}`,
    tag: `PS-${number}`,
    catalogId,
    category: specs.kind,
    qty: 1,
    location: cabinet.name || cabinet.tag,
    enclosure: cabinet.id,
    fedFrom: { ref: cabinet.sourceId ?? 'unassigned' },
    feedLengthFt: cabinet.feedLengthFt,
    env: cabinet.env,
    ...(notes ? { notes } : {}),
  };
  while (design.project.equipment.some((other) => other.id === supply.id)) supply.id += 'x';
  design.project.equipment.push(supply);
  return supply.id;
}

/** Remove a supply; its runs go back to unassigned. */
export function removeSupply(design: Design, equipmentId: string) {
  equipmentOf(design, equipmentId);
  for (const run of design.runs) if (run.assignment?.equipmentId === equipmentId) delete run.assignment;
  design.project.equipment = design.project.equipment.filter((item) => item.id !== equipmentId);
}

/** Move a supply to another cabinet; it takes that cabinet's environment, circuit and feed length. */
export function moveSupply(design: Design, equipmentId: string, cabinetId: string) {
  const supply = equipmentOf(design, equipmentId);
  const cabinet = cabinetOf(design, cabinetId);
  supply.enclosure = cabinet.id;
  supply.location = cabinet.name || cabinet.tag;
  supply.env = cabinet.env;
  supply.feedLengthFt = cabinet.feedLengthFt;
  supply.fedFrom = { ref: cabinet.sourceId ?? 'unassigned' };
}

/** Feed a supply from a panel circuit (riser source). */
export function setSupplyCircuit(design: Design, equipmentId: string, sourceId: string | undefined) {
  const supply = equipmentOf(design, equipmentId);
  if (sourceId && !design.project.sources.some((source) => source.id === sourceId))
    throw new Error(`Unknown circuit: ${sourceId}`);
  supply.fedFrom = { ref: sourceId || 'unassigned' };
}

export interface SupplyChoice {
  catalogId: string;
  /** D6: the ERP preference order; never a price. */
  rank?: number;
  usableW: number;
  /** How many of this supply the runs need, by total and by largest run. */
  count: number;
  fits: boolean;
}

/**
 * Order eligible supplies by fit (plan §10.1): one supply that carries the load first, smallest first;
 * then fewest supplies; the catalog rank breaks ties. Never by price (D6).
 */
export function fitSorted(
  candidates: readonly { catalogId: string; rank?: number }[],
  context: PowerContext,
  loadW: number,
  largestRunW: number,
  deratePct: number,
): SupplyChoice[] {
  const choices: SupplyChoice[] = [];
  for (const candidate of candidates) {
    const specs = powerSpecs(context.catalog.get(candidate.catalogId));
    if (!specs) continue;
    const limits = capacity(specs, deratePct);
    const biggestOutput = Math.max(...limits.outputs.map((output) => output.usableW));
    const fitsRun = largestRunW <= biggestOutput;
    const count = Math.max(1, Math.ceil(loadW / limits.usableW));
    choices.push({
      catalogId: candidate.catalogId,
      ...(candidate.rank !== undefined ? { rank: candidate.rank } : {}),
      usableW: limits.usableW,
      count: fitsRun ? count : Infinity,
      fits: fitsRun && count === 1,
    });
  }
  return choices.sort(
    (a, b) =>
      Number(b.fits) - Number(a.fits) ||
      a.count - b.count ||
      a.usableW - b.usableW ||
      (a.rank ?? Number.MAX_SAFE_INTEGER) - (b.rank ?? Number.MAX_SAFE_INTEGER) ||
      a.catalogId.localeCompare(b.catalogId),
  );
}

export const FROM_CONFIGURATOR = 'From configurator';

/**
 * Pre-place the supplies the configurator chose (plan §10.2): one supply per build copy and allocation
 * supply, in a cabinet in the run's space (added when the space has none). Runs keep these assignments
 * until the dealer consolidates them. Returns the number of supplies added.
 */
export function placeConfiguratorSupplies(
  design: Design,
  context: PowerContext,
  addCabinetFor: (spaceId: string) => string,
): number {
  const byErpCode = new Map(
    [...context.catalog.values()].filter((item) => item.erpItemCode).map((item) => [item.erpItemCode!, item.id]),
  );
  const placed = new Map<string, string>();
  let added = 0;
  for (const run of design.runs) {
    if (run.assignment) continue;
    const build = buildFor(run, context.builds);
    const allocation = build?.allocations.find((item) => item.runKey === String(run.runIndex));
    if (!allocation?.itemCode || allocation.supply === null || allocation.output === null) continue;
    const catalogId = byErpCode.get(allocation.itemCode);
    const specs = powerSpecs(catalogId ? context.catalog.get(catalogId) : undefined);
    const port = specs?.outputs[allocation.output - 1]?.name;
    if (!catalogId || !port) continue;
    const key = `${run.lineKey}:${run.buildIndex}:${allocation.supply}`;
    let supplyId = placed.get(key);
    if (!supplyId) {
      const cabinetId =
        design.site.cabinets.find((cabinet) => cabinet.spaceId === run.spaceId)?.id ?? addCabinetFor(run.spaceId);
      supplyId = addSupply(design, context, cabinetId, catalogId, FROM_CONFIGURATOR);
      placed.set(key, supplyId);
      added += 1;
    }
    run.assignment = { equipmentId: supplyId, port };
  }
  return added;
}

export const FROM_SCHEDULE = 'On the schedule';

export interface ScheduleSupplyLine {
  line: Line;
  catalogId: string;
}

/**
 * The power supplies the dealer already has on the fixture schedule: accessory lines (their own, or the
 * configurator's lines under a fixture) whose Item is a catalog supply. Design write-back lines are the
 * design's own output and are not read back.
 */
export function scheduleSupplyLines(context: PowerContext): ScheduleSupplyLine[] {
  const byErpCode = new Map<string, string>();
  for (const item of context.catalog.values())
    if (item.erpItemCode && powerSpecs(item) && !item.isExample) byErpCode.set(item.erpItemCode, item.id);
  const found: ScheduleSupplyLine[] = [];
  for (const line of context.lines) {
    if (line.kind !== 'accessory' || line.designLineRole || !line.accessoryItem || line.qty <= 0) continue;
    const catalogId = byErpCode.get(line.accessoryItem);
    if (catalogId) found.push({ line, catalogId });
  }
  return found;
}

/**
 * How far the design's schedule supplies are from the schedule: units with no supply in the design yet,
 * and supplies whose line is gone, changed Item or has fewer units now.
 */
export function scheduleSupplyDrift(design: Design, context: PowerContext): { missing: number; extra: number } {
  const wanted = new Map(scheduleSupplyLines(context).map((entry) => [entry.line.key, entry]));
  const placed = new Map<string, number>();
  let extra = 0;
  for (const supply of design.project.equipment) {
    if (supply.scheduleLine === undefined) continue;
    if (wanted.get(supply.scheduleLine)?.catalogId === supply.catalogId)
      placed.set(supply.scheduleLine, (placed.get(supply.scheduleLine) ?? 0) + 1);
    else extra += 1;
  }
  let missing = 0;
  for (const { line } of wanted.values()) {
    const count = placed.get(line.key) ?? 0;
    missing += Math.max(line.qty - count, 0);
    extra += Math.max(count - line.qty, 0);
  }
  return { missing, extra };
}

/** The space a schedule supply belongs in: its fixture's space, else its own location, else the first one. */
function scheduleSupplySpace(design: Design, context: PowerContext, line: Line): string | undefined {
  if (line.powerSupplyForLine) {
    const owner = context.lines.find((item) => item.lineKey === line.powerSupplyForLine);
    const run = owner ? design.runs.find((item) => item.lineKey === owner.key) : undefined;
    if (run) return run.spaceId;
  }
  const own = spaceIdFor(line.location);
  if (design.site.spaces.some((space) => space.id === own)) return own;
  return design.site.spaces[0]?.id;
}

/**
 * Bring the schedule's own supply lines into the design (plan §10.2): one supply per unit of each line's
 * quantity, tied to the line by `scheduleLine`, so write-back never adds them a second time. Supplies
 * whose line left the schedule, or more than the line's quantity, are removed (idle ones first) and their
 * runs go back to unassigned. A new supply goes in the cabinet its line's other supplies use, else a
 * cabinet in its space (added when the space has none). Returns what changed.
 */
export function syncScheduleSupplies(
  design: Design,
  context: PowerContext,
  addCabinetFor: (spaceId: string) => string,
): { added: number; removed: number } {
  const wanted = scheduleSupplyLines(context);
  const byLine = new Map(wanted.map((entry) => [entry.line.key, entry]));
  let added = 0;
  let removed = 0;
  const busy = (id: string) => design.runs.some((run) => run.assignment?.equipmentId === id);
  for (const supply of [...design.project.equipment]) {
    if (supply.scheduleLine === undefined) continue;
    const entry = byLine.get(supply.scheduleLine);
    if (!entry || entry.catalogId !== supply.catalogId) {
      removeSupply(design, supply.id);
      removed += 1;
    }
  }
  for (const { line, catalogId } of wanted) {
    const placed = design.project.equipment.filter((item) => item.scheduleLine === line.key);
    if (placed.length > line.qty) {
      const extra = [...placed]
        .reverse()
        .sort((a, b) => Number(busy(a.id)) - Number(busy(b.id)))
        .slice(0, placed.length - line.qty);
      for (const supply of extra) removeSupply(design, supply.id);
      removed += extra.length;
      continue;
    }
    if (placed.length === line.qty) continue;
    let cabinetId = placed.find((item) => item.enclosure)?.enclosure;
    if (!cabinetId) {
      const spaceId = scheduleSupplySpace(design, context, line);
      if (!spaceId) continue;
      cabinetId = design.site.cabinets.find((cabinet) => cabinet.spaceId === spaceId)?.id ?? addCabinetFor(spaceId);
    }
    for (let count = placed.length; count < line.qty; count += 1) {
      const id = addSupply(design, context, cabinetId, catalogId, FROM_SCHEDULE);
      equipmentOf(design, id).scheduleLine = line.key;
      added += 1;
    }
  }
  return { added, removed };
}

/**
 * Put every unassigned low-voltage run on a supply already in the design (schedule supplies first), and
 * return how many were placed. A fixture's runs go first where the configurator's power plan put them
 * on that fixture's own supply lines; then runs fill outputs, those with supply lines of their own first
 * and largest first, preferring the fixture's own supplies, then supplies in the run's space. Every placement passes `assignmentProblem`, so loads, zones,
 * voltage and dimming stay within limits; runs nothing can carry stay unassigned.
 */
export function autoAssignRuns(design: Design, context: PowerContext): number {
  const lineByKey = new Map(context.lines.map((line) => [line.key, line]));
  const supplyLine = (supply: Equipment) => (supply.scheduleLine ? lineByKey.get(supply.scheduleLine) : undefined);
  const ownedBy = (run: Run) => {
    const lineKey = lineByKey.get(run.lineKey)?.lineKey;
    return lineKey
      ? design.project.equipment.filter((supply) => supplyLine(supply)?.powerSupplyForLine === lineKey)
      : [];
  };
  const cabinetSpace = new Map(design.site.cabinets.map((cabinet) => [cabinet.id, cabinet.spaceId]));
  const supplies = () =>
    design.project.equipment.filter((supply) => powerSpecs(context.catalog.get(supply.catalogId)));
  const open = () =>
    design.runs.filter((run) => !run.assignment && !runElectrical(run, context).lineVoltage);
  const tryAssign = (run: Run, supply: Equipment, port: string) => {
    if (assignmentProblem(design, context, [run.key], supply.id, port)) return false;
    run.assignment = { equipmentId: supply.id, port };
    return true;
  };
  let assigned = 0;

  // The configurator's own allocation, on that fixture's supply lines.
  const taken = new Map<string, string>();
  for (const run of open()) {
    const owned = ownedBy(run);
    if (!owned.length) continue;
    const allocation = buildFor(run, context.builds)?.allocations.find((item) => item.runKey === String(run.runIndex));
    if (!allocation?.itemCode || allocation.supply === null || allocation.output === null) continue;
    const key = `${run.lineKey}:${run.buildIndex}:${allocation.supply}:${allocation.itemCode}`;
    let supplyId = taken.get(key);
    if (!supplyId) {
      const used = new Set(taken.values());
      supplyId = owned.find(
        (supply) => !used.has(supply.id) && context.catalog.get(supply.catalogId)?.erpItemCode === allocation.itemCode,
      )?.id;
      if (!supplyId) continue;
      taken.set(key, supplyId);
    }
    const supply = equipmentOf(design, supplyId);
    const port = powerSpecs(context.catalog.get(supply.catalogId))?.outputs[allocation.output - 1]?.name;
    if (port && tryAssign(run, supply, port)) assigned += 1;
  }

  // First fit: runs with supplies of their own first (so others never crowd them out), largest first.
  const runs = open()
    .map((run) => ({ run, owned: new Set(ownedBy(run).map((supply) => supply.id)) }))
    .sort(
      (a, b) =>
        Number(b.owned.size > 0) - Number(a.owned.size > 0) ||
        b.run.watts - a.run.watts ||
        a.run.key.localeCompare(b.run.key),
    );
  for (const { run, owned } of runs) {
    const rank = (supply: Equipment) =>
      owned.has(supply.id)
        ? 0
        : (supply.enclosure && cabinetSpace.get(supply.enclosure)) === run.spaceId
          ? 1
          : supply.scheduleLine
            ? 2
            : 3;
    const candidates = supplies()
      .map((supply, index) => ({ supply, index }))
      .sort((a, b) => rank(a.supply) - rank(b.supply) || a.index - b.index);
    placing: for (const { supply } of candidates)
      for (const output of powerSpecs(context.catalog.get(supply.catalogId))!.outputs)
        if (tryAssign(run, supply, output.name)) {
          assigned += 1;
          break placing;
        }
  }
  return assigned;
}

/** Low-voltage runs no supply carries yet, and their load: what more supplies must cover. */
export function powerShortfall(design: Design, context: PowerContext): { runs: Run[]; watts: number } {
  const runs = design.runs.filter((run) => !run.assignment && !runElectrical(run, context).lineVoltage);
  return { runs, watts: round(sum(runs.map((run) => run.watts)), 1) };
}

/** A new control zone. Returns its id. */
export function addZone(design: Design, method: Zone['method'], name?: string): string {
  const numbers = design.zones.map((zone) => Number(zone.id.match(/^zone-(\d+)$/)?.[1] ?? 0));
  const number = Math.max(0, ...numbers) + 1;
  const zone: Zone = {
    id: `zone-${number}`,
    name: (name?.trim() || `Zone ${number}`).slice(0, 120),
    color: ZONE_COLORS[(number - 1) % ZONE_COLORS.length]!,
    method,
  };
  design.zones.push(zone);
  return zone.id;
}

export function updateZone(design: Design, zoneId: string, changes: Partial<Pick<Zone, 'name' | 'method'>>) {
  const zone = design.zones.find((item) => item.id === zoneId);
  if (!zone) throw new Error(`Unknown zone: ${zoneId}`);
  if (changes.name !== undefined) {
    const name = changes.name.trim();
    if (!name) throw new Error('Enter a zone name');
    zone.name = name.slice(0, 120);
  }
  if (changes.method) zone.method = changes.method;
}

export function removeZone(design: Design, zoneId: string) {
  for (const run of design.runs) if (run.zoneId === zoneId) delete run.zoneId;
  design.zones = design.zones.filter((zone) => zone.id !== zoneId);
}

/**
 * Put runs in a zone (or none). Refused when an assigned run's supply cannot dim by the zone's method or
 * its output would then feed two zones.
 */
export function setRunZone(design: Design, context: PowerContext, runKeys: readonly string[], zoneId?: string) {
  const zone = zoneId ? design.zones.find((item) => item.id === zoneId) : undefined;
  if (zoneId && !zone) throw new Error(`Unknown zone: ${zoneId}`);
  const keys = new Set(runKeys);
  const before = new Map(design.runs.filter((run) => keys.has(run.key)).map((run) => [run, run.zoneId]));
  const apply = (run: Run, value: string | undefined) => {
    if (value) run.zoneId = value;
    else delete run.zoneId;
  };
  for (const run of before.keys()) apply(run, zoneId);
  const outputs = new Set(
    design.runs
      .filter((run) => keys.has(run.key) && run.assignment)
      .map((run) => `${run.assignment!.equipmentId}\u0000${run.assignment!.port}`),
  );
  for (const output of outputs) {
    const [equipmentId, port] = output.split('\u0000') as [string, string];
    const onOutput = design.runs.filter(
      (run) => run.assignment?.equipmentId === equipmentId && run.assignment.port === port,
    );
    const problem = assignmentProblem(
      design,
      context,
      onOutput.map((run) => run.key),
      equipmentId,
      port,
    );
    if (problem) {
      for (const [run, value] of before) apply(run, value);
      throw new Error(problem);
    }
  }
}

/** The D4 thresholds (H8.5): Settings `review_gate_watts`, `review_gate_dmx`, `review_gate_phase_dimming`. */
export interface ReviewGate {
  watts: number;
  dmx: boolean;
  phaseDimming: boolean;
}
export const DEFAULT_REVIEW_GATE: ReviewGate = { watts: 1500, dmx: true, phaseDimming: true };
export type ReviewTrigger = 'LOAD_OVER_THRESHOLD' | 'DMX' | 'PHASE_DIMMING';

/** D4 triggers from the design: zone methods in use and the connected load. Mirrored in `gate.py`. */
export function reviewTriggers(design: Design, gate: ReviewGate = DEFAULT_REVIEW_GATE): ReviewTrigger[] {
  const triggers: ReviewTrigger[] = [];
  const used = new Set(design.runs.map((run) => run.zoneId).filter(Boolean));
  const methods = design.zones.filter((zone) => used.has(zone.id)).map((zone) => zone.method);
  if (sum(design.runs.map((run) => run.watts)) > gate.watts) triggers.push('LOAD_OVER_THRESHOLD');
  if (gate.dmx && methods.some((method) => DMX_PROTOCOLS.has(method))) triggers.push('DMX');
  if (gate.phaseDimming && methods.some((method) => PHASE_PROTOCOLS.has(method))) triggers.push('PHASE_DIMMING');
  return triggers;
}

/** D4 hints the dealer sees before the server decides (§10.5): DMX or phase-cut zones, or over 1.5 kW. */
export function reviewHints(design: Design): string[] {
  const triggers = reviewTriggers(design);
  const hints: string[] = [];
  if (triggers.includes('DMX')) hints.push('DMX control');
  if (triggers.includes('PHASE_DIMMING')) hints.push('Phase-cut dimming');
  if (triggers.includes('LOAD_OVER_THRESHOLD'))
    hints.push(`${round(sum(design.runs.map((run) => run.watts)) / 1000, 2)} kW connected load`);
  return hints;
}
