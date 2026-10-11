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

/** True when `device` takes its power from `supply` (by id or tag). */
const feedsFrom = (device: Equipment, supply: Equipment) =>
  device.id !== supply.id && (device.fedFrom.ref === supply.id || device.fedFrom.ref === supply.tag);

/** Watts a device fed from a supply output draws: the runs on it, plus a controller's own power. */
export function deviceWatts(
  design: Design,
  device: Equipment,
  ignore: ReadonlySet<string> = new Set(),
  catalog?: ReadonlyMap<string, CatalogItem>,
): number {
  let watts = 0;
  for (const run of design.runs)
    if (run.assignment?.equipmentId === device.id && !ignore.has(run.key)) watts += run.watts;
  const specs = catalog?.get(device.catalogId)?.specs;
  if (specs?.kind === 'controller') watts += specs.ownPowerW * device.qty;
  return watts;
}

/**
 * Watts on each output of a supply: its runs, and the devices it powers (a decoder carries its runs).
 * Runs on an unknown port count against the first output. Pass the catalog to count controllers' own power.
 */
export function outputLoads(
  design: Design,
  equipmentId: string,
  ignore: ReadonlySet<string> = new Set(),
  catalog?: ReadonlyMap<string, CatalogItem>,
) {
  const loads = new Map<string, number>();
  const add = (port: string, watts: number) => loads.set(port, (loads.get(port) ?? 0) + watts);
  for (const run of design.runs)
    if (run.assignment?.equipmentId === equipmentId && !ignore.has(run.key)) add(run.assignment.port, run.watts);
  const supply = design.project.equipment.find((item) => item.id === equipmentId);
  if (supply)
    for (const device of design.project.equipment)
      if (feedsFrom(device, supply) && device.fedFrom.port)
        add(device.fedFrom.port, deviceWatts(design, device, ignore, catalog));
  return loads;
}

/** The supply output a device is powered from, or null when it is on a circuit or not fed yet. */
export function feedOf(design: Design, device: Equipment): { supply: Equipment; port: string } | null {
  if (!device.fedFrom.port) return null;
  const supply = design.project.equipment.find((item) => feedsFrom(device, item));
  return supply ? { supply, port: device.fedFrom.port } : null;
}

const sum = (values: Iterable<number>) => [...values].reduce((total, value) => total + value, 0);

function equipmentOf(design: Design, equipmentId: string) {
  const found = design.project.equipment.find((item) => item.id === equipmentId);
  if (!found) throw new Error(`Unknown supply: ${equipmentId}`);
  return found;
}

/** Zone methods a DMX decoder dims by; its runs sit in such a zone or in none. */
export const DECODER_METHODS: ReadonlySet<Zone['method']> = new Set(['DMX512', 'CRMX-wireless']);

type DecoderSpecs = Extract<CatalogItem['specs'], { kind: 'decoder' }>;

export function decoderSpecs(item: CatalogItem | undefined): DecoderSpecs | null {
  return item?.specs.kind === 'decoder' ? item.specs : null;
}

/** Channels a run takes on a decoder: its tape's channel count, else one. */
export function runChannels(run: Run, context: PowerContext): number {
  const specs = context.catalog.get(run.catalogId)?.specs;
  return specs?.kind === 'tape' ? specs.channels : 1;
}

/** A decoder output: `CH3`, or `CH1-3` for a three-channel run (the engine's port names). */
export const decoderPort = (start: number, width: number) =>
  width > 1 ? `CH${start}-${start + width - 1}` : `CH${start}`;

/** `[first, last]` channel of a decoder port, or null when the name is not a channel. */
export function channelRange(port: string): [number, number] | null {
  const match = port.match(/^CH(\d+)(?:-(\d+))?$/);
  if (!match) return null;
  const first = Number(match[1]);
  const last = match[2] ? Number(match[2]) : first;
  return first >= 1 && last >= first ? [first, last] : null;
}

/** The first decoder output of `width` channels no other run uses, or null when the decoder is full. */
export function freeDecoderPort(
  design: Design,
  context: PowerContext,
  decoderId: string,
  width: number,
  ignore: ReadonlySet<string> = new Set(),
): string | null {
  const decoder = design.project.equipment.find((item) => item.id === decoderId);
  const specs = decoder ? decoderSpecs(context.catalog.get(decoder.catalogId)) : null;
  if (!specs || width < 1) return null;
  const used = new Set<number>();
  for (const run of design.runs) {
    if (run.assignment?.equipmentId !== decoderId || ignore.has(run.key)) continue;
    const range = channelRange(run.assignment.port);
    if (range) for (let channel = range[0]; channel <= range[1]; channel += 1) used.add(channel);
  }
  for (let start = 1; start + width - 1 <= specs.channels; start += 1)
    if (Array.from({ length: width }, (_, index) => start + index).every((channel) => !used.has(channel)))
      return decoderPort(start, width);
  return null;
}

/** Why `addingW` more on a supply output would overload it or the supply, or null when it fits. */
function feedCapacityProblem(
  design: Design,
  context: PowerContext,
  supply: Equipment,
  port: string,
  ignore: ReadonlySet<string>,
  addingW: number,
): string | null {
  const specs = powerSpecs(context.catalog.get(supply.catalogId));
  if (!specs) return `${supply.tag} has incomplete catalog data, so it cannot be loaded yet`;
  const limits = capacity(specs, design.project.settings.psuDeratePct);
  const output = limits.outputs.find((item) => item.name === port);
  if (!output) return `${supply.tag} has no output ${port}`;
  const loads = outputLoads(design, supply.id, ignore, context.catalog);
  const onOutput = (loads.get(port) ?? 0) + addingW;
  if (onOutput > output.usableW)
    return `${supply.tag}/${port} would carry ${round(onOutput, 1)} W of its ${output.usableW} W usable`;
  const total = sum(loads.values()) + addingW;
  if (total > limits.usableW) return `${supply.tag} would carry ${round(total, 1)} W of its ${limits.usableW} W usable`;
  return null;
}

/** Devices (decoders, controllers) powered from one supply output. */
const devicesOn = (design: Design, supply: Equipment, port: string) =>
  design.project.equipment.filter((device) => feedsFrom(device, supply) && device.fedFrom.port === port);

/** Why these runs cannot go on this decoder output (plan §10.1): power, voltage, channels, zone, current. */
function decoderProblem(
  design: Design,
  context: PowerContext,
  runs: readonly Run[],
  keys: ReadonlySet<string>,
  decoder: Equipment,
  specs: DecoderSpecs,
  port: string,
): string | null {
  const tag = decoder.tag;
  if (specs.powerType === 'AC') return `${tag} has a line-voltage output; put line-voltage fixtures on a panel circuit`;
  const feed = feedOf(design, decoder);
  const feedSpecs = feed ? powerSpecs(context.catalog.get(feed.supply.catalogId)) : null;
  if (!feed || !feedSpecs?.outputV) return `Power ${tag} from a supply output first`;
  const volts = feedSpecs.outputV;
  const range = channelRange(port);
  if (!range || range[1] > specs.channels) return `${tag} has no output ${port}`;
  const width = range[1] - range[0] + 1;
  const zones = new Map(design.zones.map((zone) => [zone.id, zone]));
  for (const run of runs) {
    const label = runLabel(run);
    const needs = runElectrical(run, context);
    if (needs.lineVoltage) return `${label} is line voltage; feed it from a panel circuit, not a decoder`;
    if (needs.voltage !== null && needs.voltage !== volts)
      return `${label} needs ${needs.voltage} V; ${tag} is powered at ${volts} V from ${feed.supply.tag}`;
    const channels = runChannels(run, context);
    if (channels !== width)
      return `${label} needs ${channels} ${channels === 1 ? 'channel' : 'channels'}; ${port} has ${width}`;
    const zone = run.zoneId ? zones.get(run.zoneId) : undefined;
    if (zone && !DECODER_METHODS.has(zone.method)) return `${zone.name} dims by ${zone.method}; ${tag} dims by DMX`;
  }
  const others = design.runs.filter((run) => !keys.has(run.key) && run.assignment?.equipmentId === decoder.id);
  for (const other of others) {
    const used = channelRange(other.assignment!.port);
    if (used && other.assignment!.port !== port && used[0] <= range[1] && range[0] <= used[1])
      return `${tag}/${port} overlaps ${other.assignment!.port}, which ${runLabel(other)} uses`;
  }
  if (new Set([...others, ...runs].map((run) => run.zoneId ?? '')).size > 1)
    return `${tag} would feed more than one zone; give each zone its own decoder`;
  const portW = sum([...others.filter((run) => run.assignment!.port === port), ...runs].map((run) => run.watts));
  const channelA = portW / volts / width;
  if (channelA > specs.maxAPerChannel)
    return `${tag}/${port} would draw ${round(channelA, 2)} A per channel of its ${specs.maxAPerChannel} A`;
  if (specs.maxWPerChannel !== undefined && portW / width > specs.maxWPerChannel)
    return `${tag}/${port} would carry ${round(portW / width, 1)} W per channel of its ${specs.maxWPerChannel} W`;
  const adding = sum(runs.map((run) => run.watts));
  const totalW = sum(others.map((run) => run.watts)) + adding;
  if (totalW / volts > specs.maxATotal)
    return `${tag} would draw ${round(totalW / volts, 2)} A of its ${specs.maxATotal} A total`;
  if (specs.maxWTotal !== undefined && totalW > specs.maxWTotal)
    return `${tag} would carry ${round(totalW, 1)} W of its ${specs.maxWTotal} W total`;
  return feedCapacityProblem(design, context, feed.supply, feed.port, keys, adding);
}

/** Why these runs cannot go on this output (a supply output or a decoder channel), or null when they can. */
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
  const decoder = decoderSpecs(context.catalog.get(supply.catalogId));
  if (decoder) return decoderProblem(design, context, runs, keys, supply, decoder, port);
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
    if (zone && SUPPLY_DIMMED.has(zone.method)) {
      if (!specs.dimming.includes(zone.method)) return `${zone.name} dims by ${zone.method}; ${supply.tag} does not accept it`;
      const device = devicesOn(design, supply, port)[0];
      if (device) return `${supply.tag}/${port} powers ${device.tag}; a dimmed zone needs an output of its own`;
    }
  }

  const sharing = design.runs.filter(
    (run) => !keys.has(run.key) && run.assignment?.equipmentId === equipmentId && run.assignment.port === port,
  );
  const zoneIds = new Set([...sharing, ...runs].map((run) => run.zoneId ?? ''));
  if (zoneIds.size > 1) return `${supply.tag}/${port} would feed more than one zone; give each zone its own output`;

  return feedCapacityProblem(design, context, supply, port, keys, sum(runs.map((run) => run.watts)));
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

/**
 * The decoder output for these runs: the first free channels as wide as their tape (runs put on a decoder
 * together share one output and dim together). Throws when the runs differ in width or the decoder is full.
 */
export function decoderPortFor(design: Design, context: PowerContext, runKeys: readonly string[], decoderId: string) {
  const keys = new Set(runKeys);
  const widths = new Set(design.runs.filter((run) => keys.has(run.key)).map((run) => runChannels(run, context)));
  if (widths.size > 1) throw new Error('Select runs with the same number of channels to share a decoder output');
  const decoder = equipmentOf(design, decoderId);
  const port = freeDecoderPort(design, context, decoderId, [...widths][0] ?? 1, keys);
  if (!port) throw new Error(`${decoder.tag} has no free channels for these runs`);
  return port;
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

/**
 * Remove a supply or control. Its runs go back to unassigned, devices it powered lose their feed, and
 * zones, control inputs and control links that named it let go of it.
 */
export function removeSupply(design: Design, equipmentId: string) {
  const removed = equipmentOf(design, equipmentId);
  const refs = new Set([removed.id, removed.tag]);
  for (const run of design.runs) if (run.assignment?.equipmentId === equipmentId) delete run.assignment;
  for (const device of design.project.equipment) {
    if (device.id === equipmentId) continue;
    if (refs.has(device.fedFrom.ref)) device.fedFrom = { ref: 'unassigned' };
    if (device.controlFrom && refs.has(device.controlFrom.ref)) {
      delete device.controlFrom;
      delete device.controlLengthFt;
    }
  }
  for (const zone of design.zones) if (zone.control?.equipmentId === equipmentId) delete zone.control;
  design.project.controlLinks = design.project.controlLinks.filter(
    (link) => !refs.has(link.from.ref) && !refs.has(link.to.ref),
  );
  design.project.equipment = design.project.equipment.filter((item) => item.id !== equipmentId);
}

/**
 * Move a supply to another cabinet; it takes that cabinet's environment, circuit and feed length. Devices
 * it powered stay in their cabinet and lose that feed (power is patched within a cabinet).
 */
export function moveSupply(design: Design, equipmentId: string, cabinetId: string) {
  const supply = equipmentOf(design, equipmentId);
  const cabinet = cabinetOf(design, cabinetId);
  supply.enclosure = cabinet.id;
  supply.location = cabinet.name || cabinet.tag;
  supply.env = cabinet.env;
  supply.feedLengthFt = cabinet.feedLengthFt;
  supply.fedFrom = { ref: cabinet.sourceId ?? 'unassigned' };
  for (const device of design.project.equipment)
    if (feedsFrom(device, supply) && device.enclosure !== cabinet.id) device.fedFrom = { ref: 'unassigned' };
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
/** A schedule line that is a catalog product the design places as equipment (a supply or a control). */
export type ScheduleEquipmentLine = ScheduleSupplyLine;
type ItemTest = (item: CatalogItem | undefined) => boolean;

/**
 * Accessory lines (the dealer's own, or the configurator's lines under a fixture) whose Item is a catalog
 * product `accept` takes. Design write-back lines are the design's own output and are not read back.
 */
export function scheduleItemLines(context: PowerContext, accept: ItemTest): ScheduleEquipmentLine[] {
  const byErpCode = new Map<string, string>();
  for (const item of context.catalog.values())
    if (item.erpItemCode && accept(item) && !item.isExample) byErpCode.set(item.erpItemCode, item.id);
  const found: ScheduleEquipmentLine[] = [];
  for (const line of context.lines) {
    if (line.kind !== 'accessory' || line.designLineRole || !line.accessoryItem || line.qty <= 0) continue;
    const catalogId = byErpCode.get(line.accessoryItem);
    if (catalogId) found.push({ line, catalogId });
  }
  return found;
}

const isSupplyItem: ItemTest = (item) => Boolean(powerSpecs(item));

/** The power supplies the dealer already has on the fixture schedule. */
export function scheduleSupplyLines(context: PowerContext): ScheduleSupplyLine[] {
  return scheduleItemLines(context, isSupplyItem);
}

/**
 * How far the design's schedule equipment of one kind is from the schedule: units with no equipment in
 * the design yet, and equipment whose line is gone, changed Item or has fewer units now.
 */
export function scheduleItemDrift(
  design: Design,
  context: PowerContext,
  accept: ItemTest,
): { missing: number; extra: number } {
  const wanted = new Map(scheduleItemLines(context, accept).map((entry) => [entry.line.key, entry]));
  const placed = new Map<string, number>();
  let extra = 0;
  for (const item of design.project.equipment) {
    if (item.scheduleLine === undefined || !accept(context.catalog.get(item.catalogId))) continue;
    if (wanted.get(item.scheduleLine)?.catalogId === item.catalogId)
      placed.set(item.scheduleLine, (placed.get(item.scheduleLine) ?? 0) + 1);
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

export function scheduleSupplyDrift(design: Design, context: PowerContext): { missing: number; extra: number } {
  return scheduleItemDrift(design, context, isSupplyItem);
}

/** The space a schedule line's equipment belongs in: its fixture's space, else its own location, else the first one. */
function scheduleLineSpace(design: Design, context: PowerContext, line: Line): string | undefined {
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
 * Bring the schedule's own lines of one kind into the design (plan §10.2): one piece of equipment per unit
 * of each line's quantity, tied to the line by `scheduleLine`, so write-back never adds it a second time.
 * Equipment whose line left the schedule, or more than the line's quantity, is removed (idle first) and its
 * runs go back to unassigned. New equipment goes in the cabinet its line's other units use, else a cabinet
 * in its space (added when the space has none). `add` places one unit and returns its id.
 */
export function syncScheduleItems(
  design: Design,
  context: PowerContext,
  accept: ItemTest,
  addCabinetFor: (spaceId: string) => string,
  add: (cabinetId: string, catalogId: string) => string,
): { added: number; removed: number } {
  const wanted = scheduleItemLines(context, accept);
  const byLine = new Map(wanted.map((entry) => [entry.line.key, entry]));
  let added = 0;
  let removed = 0;
  const busy = (item: Equipment) =>
    design.runs.some((run) => run.assignment?.equipmentId === item.id) ||
    design.project.equipment.some((device) => feedsFrom(device, item)) ||
    design.zones.some((zone) => zone.control?.equipmentId === item.id);
  const ours = (item: Equipment) => item.scheduleLine !== undefined && accept(context.catalog.get(item.catalogId));
  for (const item of design.project.equipment.filter(ours)) {
    const entry = byLine.get(item.scheduleLine!);
    if (!entry || entry.catalogId !== item.catalogId) {
      removeSupply(design, item.id);
      removed += 1;
    }
  }
  for (const { line, catalogId } of wanted) {
    const placed = design.project.equipment.filter((item) => item.scheduleLine === line.key);
    if (placed.length > line.qty) {
      const extra = [...placed]
        .reverse()
        .sort((a, b) => Number(busy(a)) - Number(busy(b)))
        .slice(0, placed.length - line.qty);
      for (const item of extra) removeSupply(design, item.id);
      removed += extra.length;
      continue;
    }
    if (placed.length === line.qty) continue;
    let cabinetId = placed.find((item) => item.enclosure)?.enclosure;
    if (!cabinetId) {
      const spaceId = scheduleLineSpace(design, context, line);
      if (!spaceId) continue;
      cabinetId = design.site.cabinets.find((cabinet) => cabinet.spaceId === spaceId)?.id ?? addCabinetFor(spaceId);
    }
    for (let count = placed.length; count < line.qty; count += 1) {
      const id = add(cabinetId, catalogId);
      equipmentOf(design, id).scheduleLine = line.key;
      added += 1;
    }
  }
  return { added, removed };
}

/** Bring the schedule's own supply lines into the design (see `syncScheduleItems`). */
export function syncScheduleSupplies(
  design: Design,
  context: PowerContext,
  addCabinetFor: (spaceId: string) => string,
): { added: number; removed: number } {
  return syncScheduleItems(design, context, isSupplyItem, addCabinetFor, (cabinetId, catalogId) =>
    addSupply(design, context, cabinetId, catalogId, FROM_SCHEDULE),
  );
}

/**
 * Put every unassigned low-voltage run on a supply already in the design (schedule supplies first), and
 * return how many were placed. Runs in a DMX zone try a powered decoder's free channels first. A fixture's runs go first where the configurator's power plan put them
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
  const zones = new Map(design.zones.map((zone) => [zone.id, zone]));
  const dmxRun = (run: Run) => DECODER_METHODS.has(zones.get(run.zoneId ?? '')?.method ?? 'none');
  const decoders = () =>
    design.project.equipment.filter((item) => decoderSpecs(context.catalog.get(item.catalogId))?.powerType === 'DC');
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
    if (!owned.length || dmxRun(run)) continue;
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
    // Runs in a DMX zone go on a decoder channel first.
    if (dmxRun(run)) {
      const placed = decoders()
        .map((decoder, index) => ({ decoder, index }))
        .sort((a, b) => rank(a.decoder) - rank(b.decoder) || a.index - b.index)
        .some(({ decoder }) => {
          const port = freeDecoderPort(design, context, decoder.id, runChannels(run, context), new Set([run.key]));
          return port !== null && tryAssign(run, decoder, port);
        });
      if (placed) {
        assigned += 1;
        continue;
      }
    }
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

/** The control protocol each zone method needs from its control output; phase-cut and switched zones have none. */
export const ZONE_CONTROL_PROTOCOL: Readonly<Partial<Record<Zone['method'], Protocol>>> = {
  DMX512: 'DMX512',
  'CRMX-wireless': 'DMX512', // A wireless receiver's DMX output feeds the decoders.
  '0-10V': '0-10V',
  'DALI-2': 'DALI-2',
  'Lutron-QS': 'Lutron-QS',
  'Lutron-EcoSystem': 'Lutron-EcoSystem',
};

/**
 * Rename a zone or change its dimming method. A new method must suit every supply and decoder already
 * carrying the zone's runs (checked when `context` is given), and a control sending another protocol is let go.
 */
export function updateZone(
  design: Design,
  zoneId: string,
  changes: Partial<Pick<Zone, 'name' | 'method'>>,
  context?: PowerContext,
) {
  const zone = design.zones.find((item) => item.id === zoneId);
  if (!zone) throw new Error(`Unknown zone: ${zoneId}`);
  if (changes.name !== undefined) {
    const name = changes.name.trim();
    if (!name) throw new Error('Enter a zone name');
    zone.name = name.slice(0, 120);
  }
  if (!changes.method || changes.method === zone.method) return;
  const before = zone.method;
  zone.method = changes.method;
  if (context) {
    const outputs = new Map<string, Run[]>();
    for (const run of design.runs)
      if (run.zoneId === zoneId && run.assignment && design.project.equipment.some((item) => item.id === run.assignment!.equipmentId)) {
        const key = `${run.assignment.equipmentId}\u0000${run.assignment.port}`;
        outputs.set(key, [...(outputs.get(key) ?? []), run]);
      }
    for (const [key, runs] of outputs) {
      const [equipmentId, port] = key.split('\u0000') as [string, string];
      const problem = assignmentProblem(
        design,
        context,
        runs.map((run) => run.key),
        equipmentId,
        port,
      );
      if (problem) {
        zone.method = before;
        throw new Error(problem);
      }
    }
  }
  if (zone.control && ZONE_CONTROL_PROTOCOL[before] !== ZONE_CONTROL_PROTOCOL[zone.method]) delete zone.control;
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
  // Panel circuits (line-voltage fixtures) have no output rules; supplies and decoders do.
  const equipment = new Set(design.project.equipment.map((item) => item.id));
  const outputs = new Set(
    design.runs
      .filter((run) => keys.has(run.key) && run.assignment && equipment.has(run.assignment.equipmentId))
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
