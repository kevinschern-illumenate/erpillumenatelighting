import type { CatalogItem } from '@ill/core-schemas/catalog';
import type { Protocol } from '@ill/core-schemas/common';
import type { Cabinet, Design, Run, Zone } from '@ill/core-schemas/design';
import type { Builds, Line } from '@ill/core-schemas/open-design';
import type { Equipment } from '@ill/core-schemas/project';
import { round } from './messages';
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

/** D4 hints the dealer sees before the server decides (§10.5): DMX or phase-cut zones, or over 1.5 kW. */
export function reviewHints(design: Design): string[] {
  const hints: string[] = [];
  const used = new Set(design.runs.map((run) => run.zoneId).filter(Boolean));
  const methods = new Set(design.zones.filter((zone) => used.has(zone.id)).map((zone) => zone.method));
  if (methods.has('DMX512') || methods.has('CRMX-wireless')) hints.push('DMX control');
  if (methods.has('phase-forward') || methods.has('phase-reverse')) hints.push('Phase-cut dimming');
  const total = sum(design.runs.map((run) => run.watts));
  if (total > 1500) hints.push(`${round(total / 1000, 2)} kW connected load`);
  return hints;
}
