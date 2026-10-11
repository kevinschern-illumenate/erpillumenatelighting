import type { CatalogItem } from '@ill/core-schemas/catalog';
import type { Protocol } from '@ill/core-schemas/common';
import type { Cabinet, Design, Zone } from '@ill/core-schemas/design';
import type { ControlLink, Equipment, ValidationMessage } from '@ill/core-schemas/project';
import { message } from './messages';
import { inputVoltageRange, supportedProtocols } from './ports';
import {
  DECODER_METHODS,
  FROM_SCHEDULE,
  ZONE_CONTROL_PROTOCOL,
  ZONE_METHODS,
  deviceWatts,
  feedOf,
  outputLoads,
  powerSpecs,
  capacity,
  removeSupply,
  scheduleItemDrift,
  scheduleItemLines,
  syncScheduleItems,
  type PowerContext,
  type ScheduleEquipmentLine,
} from './power';
import { runLabel } from './runs';

/**
 * Controls on the power board (plan §10.3–10.4): controllers, decoders, converters and dimmers. Like
 * `power.ts`, each function changes the design it is given inside one undoable store edit.
 *
 * - The controls already on the fixture schedule come in first, one per unit, tied to their line by
 *   `scheduleLine`, so write-back never lists them twice.
 * - A control is powered from its cabinet's circuit (AC input) or a supply output in the same cabinet (DC).
 * - A decoder's channels carry runs like a supply output (`assignmentProblem`).
 * - A zone names the control output that dims it (`Zone.control`); the control links the riser draws are
 *   derived from that and from where the zone's runs sit (`deriveControlLinks`), never stored, so moving a
 *   run never leaves a stale link. Links drawn in engineering mode are kept and win.
 */

export type ControlSpecs = Extract<CatalogItem['specs'], { kind: 'controller' | 'decoder' }>;

/** Patch length inside one cabinet, and the estimate between cabinets, for derived control links. */
export const PATCH_FT = 3;
export const CROSS_CABINET_FT = 25;

export function controlSpecs(item: CatalogItem | undefined): ControlSpecs | null {
  return item && (item.specs.kind === 'controller' || item.specs.kind === 'decoder') ? item.specs : null;
}

const isControlItem = (item: CatalogItem | undefined) => Boolean(controlSpecs(item));

export const isControl = (equipment: Equipment, catalog: ReadonlyMap<string, CatalogItem>) =>
  isControlItem(catalog.get(equipment.catalogId));

/** DMX receivers take an address: decoders and DMX to 0-10V converters (A.5). */
export const receivesDmx = (item: CatalogItem | undefined) =>
  item?.category === 'dmx-decoder' || item?.category === 'dmx-0-10v-converter';

export const CONTROL_LABELS: Readonly<Record<string, string>> = {
  'dmx-decoder': 'DMX decoder',
  'dmx-controller': 'DMX controller',
  'dmx-0-10v-converter': 'DMX to 0-10V converter',
  'wireless-tx': 'Wireless transmitter',
  'wireless-rx': 'Wireless receiver',
  'pixel-controller': 'Pixel controller',
  'opto-splitter': 'DMX splitter',
  'sacn-gateway': 'Gateway',
  'lutron-module': 'Lutron module',
  '0-10v-dimmer': '0-10V dimmer',
  keypad: 'Keypad',
  relay: 'Relay',
};

export const controlLabel = (item: CatalogItem | undefined) =>
  (item && CONTROL_LABELS[item.category]) ?? 'Control';

function acInput(specs: ControlSpecs) {
  return specs.kind === 'decoder' ? specs.powerType === 'AC' : specs.inputType !== 'DC';
}
function dcInput(specs: ControlSpecs) {
  return specs.kind === 'decoder' ? specs.powerType === 'DC' : specs.inputType !== 'AC';
}

function equipmentOf(design: Design, id: string): Equipment {
  const found = design.project.equipment.find((item) => item.id === id);
  if (!found) throw new Error(`Unknown control: ${id}`);
  return found;
}

function cabinetOf(design: Design, cabinetId: string): Cabinet {
  const cabinet = design.site.cabinets.find((item) => item.id === cabinetId);
  if (!cabinet) throw new Error(`Unknown cabinet: ${cabinetId}`);
  return cabinet;
}

function nextNumber(design: Design, prefix: string) {
  const used = design.project.equipment
    .map((item) => item.tag.match(new RegExp(`^${prefix}-(\\d+)$`))?.[1])
    .filter((value): value is string => value !== undefined)
    .map(Number);
  return used.length ? Math.max(...used) + 1 : 1;
}

/** Catalog controls a dealer may place: complete, real products, by label then model. */
export function controlChoices(context: PowerContext): CatalogItem[] {
  return [...context.catalog.values()]
    .filter((item) => isControlItem(item) && !item.isExample)
    .sort((a, b) => controlLabel(a).localeCompare(controlLabel(b)) || a.model.localeCompare(b.model));
}

/**
 * A new control in a cabinet. An AC control is fed from the cabinet's circuit; a DC control waits for a
 * supply output (`setControlFeed`). DMX receivers start on universe 1 with automatic addressing. Returns its id.
 */
export function addControl(
  design: Design,
  context: PowerContext,
  cabinetId: string,
  catalogId: string,
  notes?: string,
): string {
  const cabinet = cabinetOf(design, cabinetId);
  const item = context.catalog.get(catalogId);
  const specs = controlSpecs(item);
  if (!item || !specs || item.isExample) throw new Error('Choose a control from the ilLumenate catalog');
  const prefix = specs.kind === 'decoder' ? 'DEC' : 'CTL';
  const number = nextNumber(design, prefix);
  const onCircuit = acInput(specs) && Boolean(cabinet.sourceId);
  const control: Equipment = {
    id: `${prefix}-${number}`,
    tag: `${prefix}-${number}`,
    catalogId,
    category: item.category as Equipment['category'],
    qty: 1,
    location: cabinet.name || cabinet.tag,
    enclosure: cabinet.id,
    fedFrom: { ref: onCircuit ? cabinet.sourceId! : 'unassigned' },
    feedLengthFt: onCircuit ? cabinet.feedLengthFt : PATCH_FT,
    env: cabinet.env,
    ...(receivesDmx(item) ? { dmx: { universe: 1, startAddress: 'auto' as const } } : {}),
    ...(notes ? { notes } : {}),
  };
  while (design.project.equipment.some((other) => other.id === control.id)) control.id += 'x';
  design.project.equipment.push(control);
  return control.id;
}

/** Remove a control: its runs go back to unassigned and zones and links let go of it. */
export const removeControl = removeSupply;

/** Move a control to another cabinet; a supply feed from the old cabinet is dropped. */
export function moveControl(design: Design, controlId: string, cabinetId: string) {
  const control = equipmentOf(design, controlId);
  const cabinet = cabinetOf(design, cabinetId);
  control.enclosure = cabinet.id;
  control.location = cabinet.name || cabinet.tag;
  control.env = cabinet.env;
  if (control.fedFrom.port) {
    const feed = feedOf(design, control);
    if (!feed || feed.supply.enclosure !== cabinet.id) control.fedFrom = { ref: 'unassigned' };
  } else if (design.project.sources.some((source) => source.id === control.fedFrom.ref)) {
    control.fedFrom = { ref: cabinet.sourceId ?? 'unassigned' };
    control.feedLengthFt = cabinet.feedLengthFt;
  }
}

// --- Schedule controls -----------------------------------------------------------------------------

/** The controls the dealer already has on the fixture schedule (accessory lines of catalog controls). */
export function scheduleControlLines(context: PowerContext): ScheduleEquipmentLine[] {
  return scheduleItemLines(context, isControlItem);
}

export function scheduleControlDrift(design: Design, context: PowerContext) {
  return scheduleItemDrift(design, context, isControlItem);
}

/**
 * Bring the schedule's controls into the design: one per unit, in its line's cabinet, else a cabinet in
 * its space, else the cabinet holding most supplies. Units no longer on the schedule are removed.
 */
export function syncScheduleControls(
  design: Design,
  context: PowerContext,
  addCabinetFor: (spaceId: string) => string,
): { added: number; removed: number } {
  return syncScheduleItems(
    design,
    context,
    isControlItem,
    (spaceId) => {
      const counts = new Map<string, number>();
      for (const item of design.project.equipment)
        if (item.enclosure && powerSpecs(context.catalog.get(item.catalogId)))
          counts.set(item.enclosure, (counts.get(item.enclosure) ?? 0) + 1);
      const busiest = [...counts].sort((a, b) => b[1] - a[1])[0]?.[0];
      // A control's own location wins when it names a space; otherwise it joins the supplies.
      if (design.site.cabinets.some((cabinet) => cabinet.spaceId === spaceId) || !busiest) return addCabinetFor(spaceId);
      return busiest;
    },
    (cabinetId, catalogId) => addControl(design, context, cabinetId, catalogId, FROM_SCHEDULE),
  );
}

/**
 * Schedule lines the designer cannot place because their catalog product is incomplete: they stay on the
 * schedule as they are, and the board names them so nothing is lost silently.
 */
export function scheduleIncompleteLines(context: PowerContext): { lineId: string; itemCode: string }[] {
  const incomplete = new Set<string>();
  for (const item of context.catalog.values())
    if (
      item.erpItemCode &&
      item.specs.kind === 'incomplete' &&
      ['psu', 'driver', 'decoder', 'controller'].includes(item.specs.intendedKind)
    )
      incomplete.add(item.erpItemCode);
  return context.lines
    .filter(
      (line) =>
        line.kind === 'accessory' && !line.designLineRole && line.accessoryItem && incomplete.has(line.accessoryItem),
    )
    .map((line) => ({ lineId: line.lineId ?? line.key, itemCode: line.accessoryItem! }));
}

// --- Power for controls ----------------------------------------------------------------------------

export interface FeedOption {
  value: string;
  label: string;
}

/** Where a control can take power: circuits in its AC range, or CV supply outputs in its cabinet in its DC range. */
export function controlFeedOptions(design: Design, context: PowerContext, controlId: string): FeedOption[] {
  const control = equipmentOf(design, controlId);
  const specs = controlSpecs(context.catalog.get(control.catalogId));
  if (!specs) return [];
  const options: FeedOption[] = [];
  const within = (range: [number, number] | undefined, volts: number) =>
    range !== undefined && volts >= range[0] && volts <= range[1];
  if (acInput(specs))
    for (const source of design.project.sources)
      if (within(inputVoltageRange(specs, 'AC'), source.voltage))
        options.push({ value: source.id, label: `${source.panel}/${source.circuit} · ${source.voltage} V` });
  if (dcInput(specs))
    for (const supply of design.project.equipment) {
      if (supply.enclosure !== control.enclosure || supply.id === control.id) continue;
      const power = powerSpecs(context.catalog.get(supply.catalogId));
      if (!power || power.outputType !== 'CV' || power.outputCurrent === 'AC' || !power.outputV) continue;
      if (!within(inputVoltageRange(specs, 'DC'), power.outputV)) continue;
      for (const output of power.outputs)
        options.push({
          value: `${supply.id}::${output.name}`,
          label: `${supply.tag}/${output.name} · ${power.outputV} V DC`,
        });
    }
  return options;
}

const parseValue = (value: string) => {
  const [ref = '', port] = value.split('::');
  return { ref, ...(port ? { port } : {}) };
};

/** Why a control cannot take power from `value` (a circuit id or `supply::output`), or null when it can. */
export function controlFeedProblem(
  design: Design,
  context: PowerContext,
  controlId: string,
  value: string,
): string | null {
  const control = equipmentOf(design, controlId);
  if (!controlFeedOptions(design, context, controlId).some((option) => option.value === value))
    return `${control.tag} cannot take power from there; check its input voltage and cabinet`;
  const target = parseValue(value);
  if (!target.port) return null;
  const supply = design.project.equipment.find((item) => item.id === target.ref)!;
  const zones = new Map(design.zones.map((zone) => [zone.id, zone]));
  const dimmed = design.runs.find(
    (run) =>
      run.assignment?.equipmentId === supply.id &&
      run.assignment.port === target.port &&
      ['phase-forward', 'phase-reverse', '0-10V', 'DALI-2'].includes(zones.get(run.zoneId ?? '')?.method ?? ''),
  );
  if (dimmed)
    return `${supply.tag}/${target.port} is dimmed with ${zones.get(dimmed.zoneId!)!.name}; power ${control.tag} from an undimmed output`;
  const ignore = new Set<string>();
  const before = control.fedFrom;
  control.fedFrom = { ref: 'unassigned' };
  try {
    const specs = powerSpecs(context.catalog.get(supply.catalogId))!;
    const limits = capacity(specs, design.project.settings.psuDeratePct);
    const output = limits.outputs.find((item) => item.name === target.port)!;
    const loads = outputLoads(design, supply.id, ignore, context.catalog);
    const adding = deviceWatts(design, control, ignore, context.catalog);
    const onOutput = (loads.get(target.port) ?? 0) + adding;
    if (onOutput > output.usableW)
      return `${supply.tag}/${target.port} would carry ${Math.round(onOutput * 10) / 10} W of its ${output.usableW} W usable`;
    const total = [...loads.values()].reduce((sum, watts) => sum + watts, 0) + adding;
    if (total > limits.usableW)
      return `${supply.tag} would carry ${Math.round(total * 10) / 10} W of its ${limits.usableW} W usable`;
    return null;
  } finally {
    control.fedFrom = before;
  }
}

/** Power a control from a circuit or a supply output (`undefined`: not fed yet); throws the refusal reason. */
export function setControlFeed(design: Design, context: PowerContext, controlId: string, value: string | undefined) {
  const control = equipmentOf(design, controlId);
  if (!value) {
    control.fedFrom = { ref: 'unassigned' };
    return;
  }
  const problem = controlFeedProblem(design, context, controlId, value);
  if (problem) throw new Error(problem);
  const target = parseValue(value);
  control.fedFrom = target;
  const cabinet = design.site.cabinets.find((item) => item.id === control.enclosure);
  control.feedLengthFt = target.port ? PATCH_FT : (cabinet?.feedLengthFt ?? control.feedLengthFt);
}

/**
 * Power every control not fed yet: its cabinet's circuit when it takes AC from it, else the first supply
 * output in its cabinet that carries it. Returns how many were fed.
 */
export function autoPowerControls(design: Design, context: PowerContext): number {
  let fed = 0;
  for (const control of design.project.equipment) {
    if (control.fedFrom.ref !== 'unassigned' || !isControl(control, context.catalog)) continue;
    const cabinet = design.site.cabinets.find((item) => item.id === control.enclosure);
    const options = controlFeedOptions(design, context, control.id);
    const ordered = [
      ...options.filter((option) => option.value === cabinet?.sourceId),
      ...options.filter((option) => option.value.includes('::')),
    ];
    const pick = ordered.find((option) => !controlFeedProblem(design, context, control.id, option.value));
    if (!pick) continue;
    setControlFeed(design, context, control.id, pick.value);
    fed += 1;
  }
  return fed;
}

// --- Control inputs and zones ------------------------------------------------------------------------

/**
 * Where a control can take its control signal: another control's output port in a protocol it accepts
 * (a DMX controller into a converter, a wireless transmitter into a receiver). Decoders take theirs from
 * the zone they serve.
 */
export function controlInputOptions(design: Design, context: PowerContext, controlId: string): FeedOption[] {
  const control = equipmentOf(design, controlId);
  const specs = controlSpecs(context.catalog.get(control.catalogId));
  if (specs?.kind !== 'controller') return [];
  const accepts = new Set<Protocol>(supportedProtocols(specs, 'in').filter((protocol) => protocol !== 'none'));
  const options: FeedOption[] = [];
  for (const source of design.project.equipment) {
    if (source.id === control.id) continue;
    const sourceSpecs = controlSpecs(context.catalog.get(source.catalogId));
    if (sourceSpecs?.kind !== 'controller') continue;
    for (const port of sourceSpecs.ports)
      if (port.direction !== 'in' && accepts.has(port.protocol))
        options.push({ value: `${source.id}::${port.name}`, label: `${source.tag}/${port.name} · ${port.protocol}` });
  }
  return options;
}

/** Take a control's signal from another control's output (`undefined` clears it); throws when not offered. */
export function setControlInput(design: Design, context: PowerContext, controlId: string, value: string | undefined) {
  const control = equipmentOf(design, controlId);
  if (!value) {
    delete control.controlFrom;
    delete control.controlLengthFt;
    return;
  }
  if (!controlInputOptions(design, context, controlId).some((option) => option.value === value))
    throw new Error(`${control.tag} cannot take its control signal from there`);
  const target = parseValue(value);
  const source = equipmentOf(design, target.ref);
  control.controlFrom = target;
  control.controlLengthFt = source.enclosure === control.enclosure ? PATCH_FT : CROSS_CABINET_FT;
}

/** Change a DMX receiver's universe, start address (a number or `auto`) or end-of-line terminator. */
export function setDmx(
  design: Design,
  controlId: string,
  changes: { universe?: number; startAddress?: number | 'auto'; terminatorPresent?: boolean },
) {
  const control = equipmentOf(design, controlId);
  if (!control.dmx) throw new Error(`${control.tag} does not take a DMX address`);
  const next = { ...control.dmx };
  if (changes.universe !== undefined) {
    if (!Number.isInteger(changes.universe) || changes.universe < 1 || changes.universe > 63999)
      throw new Error('Enter a universe from 1 to 63999');
    next.universe = changes.universe;
  }
  if (changes.startAddress !== undefined) {
    const start = changes.startAddress;
    if (start !== 'auto' && (!Number.isInteger(start) || start < 1 || start > 512))
      throw new Error('Enter a start address from 1 to 512, or auto');
    next.startAddress = start;
  }
  if (changes.terminatorPresent !== undefined) {
    if (changes.terminatorPresent) next.terminatorPresent = true;
    else delete next.terminatorPresent;
  }
  control.dmx = next;
}

/** Control outputs that can dim a zone: controller ports sending the zone's protocol. */
export function zoneControlOptions(design: Design, context: PowerContext, zone: Zone): FeedOption[] {
  const protocol = ZONE_CONTROL_PROTOCOL[zone.method];
  if (!protocol) return [];
  const options: FeedOption[] = [];
  for (const control of design.project.equipment) {
    const specs = controlSpecs(context.catalog.get(control.catalogId));
    if (specs?.kind !== 'controller') continue;
    for (const port of specs.ports)
      if (port.direction !== 'in' && port.protocol === protocol)
        options.push({ value: `${control.id}::${port.name}`, label: `${control.tag}/${port.name} · ${protocol}` });
  }
  return options;
}

/** Name the control output that dims a zone (`undefined` clears it); throws when it cannot. */
export function setZoneControl(design: Design, context: PowerContext, zoneId: string, value: string | undefined) {
  const zone = design.zones.find((item) => item.id === zoneId);
  if (!zone) throw new Error(`Unknown zone: ${zoneId}`);
  if (!value) {
    delete zone.control;
    return;
  }
  if (!ZONE_CONTROL_PROTOCOL[zone.method])
    throw new Error(`${zone.name} is ${methodLabel(zone.method)}; it has no control output to choose`);
  if (!zoneControlOptions(design, context, zone).some((option) => option.value === value))
    throw new Error(`That output does not send ${ZONE_CONTROL_PROTOCOL[zone.method]}`);
  const target = parseValue(value);
  zone.control = { equipmentId: target.ref, port: target.port! };
}

const methodLabel = (method: Zone['method']) => ZONE_METHODS.find((item) => item.id === method)?.label ?? method;

/** What a zone's control reaches: decoders for DMX zones, supplies (or DMX-capable supplies) otherwise. */
function zoneReceivers(design: Design, catalog: ReadonlyMap<string, CatalogItem>, zone: Zone, protocol: Protocol) {
  const receivers: Equipment[] = [];
  const strays: string[] = [];
  const byId = new Map(design.project.equipment.map((item) => [item.id, item]));
  for (const run of design.runs) {
    if (run.zoneId !== zone.id || !run.assignment) continue;
    const target = byId.get(run.assignment.equipmentId);
    if (!target) continue; // a panel circuit
    const specs = catalog.get(target.catalogId)?.specs;
    const accepts =
      specs?.kind === 'decoder'
        ? protocol === 'DMX512' && specs.protocolIn.includes('DMX512')
        : specs?.kind === 'psu' || specs?.kind === 'driver'
          ? DECODER_METHODS.has(zone.method)
            ? specs.dimming.includes('DMX512')
            : true // the engine reports a supply that does not accept the protocol
          : false;
    if (accepts) {
      if (!receivers.includes(target)) receivers.push(target);
    } else strays.push(runLabel(run));
  }
  return { receivers, strays };
}

const linkLength = (from: Equipment, to: Equipment) =>
  from.enclosure && from.enclosure === to.enclosure ? PATCH_FT : CROSS_CABINET_FT;

/**
 * The control links a design implies (plan §10.4): each zone's control output to what dims its runs. DMX
 * is daisy-chained through the decoders of every zone on that output (in chain order, then tag); other
 * protocols run from the output to each supply. A receiver an engineering-mode link already reaches in
 * that protocol keeps that link instead.
 */
export function deriveControlLinks(design: Design, catalog: ReadonlyMap<string, CatalogItem>): ControlLink[] {
  const byId = new Map(design.project.equipment.map((item) => [item.id, item]));
  const resolve = (ref: string) => byId.get(ref)?.id ?? design.project.equipment.find((item) => item.tag === ref)?.id;
  const manual = new Set(design.project.controlLinks.map((link) => `${resolve(link.to.ref)}|${link.protocol}`));
  const groups = new Map<string, { control: Equipment; port: string; protocol: Protocol; receivers: Equipment[] }>();
  for (const zone of design.zones) {
    const protocol = ZONE_CONTROL_PROTOCOL[zone.method];
    const control = zone.control ? byId.get(zone.control.equipmentId) : undefined;
    if (!protocol || !control) continue;
    const key = `${control.id}::${zone.control!.port}`;
    const group = groups.get(key) ?? { control, port: zone.control!.port, protocol, receivers: [] };
    groups.set(key, group);
    for (const receiver of zoneReceivers(design, catalog, zone, protocol).receivers)
      if (!group.receivers.includes(receiver) && !manual.has(`${receiver.id}|${protocol}`))
        group.receivers.push(receiver);
  }
  const links: ControlLink[] = [];
  for (const { control, port, protocol, receivers } of groups.values()) {
    const base = `zone-${control.id}-${port}`.replace(/[^A-Za-z0-9_-]/g, '_');
    if (protocol === 'DMX512') {
      const chain = [...receivers].sort(
        (a, b) => (a.chainOrder ?? Infinity) - (b.chainOrder ?? Infinity) || a.tag.localeCompare(b.tag, undefined, { numeric: true }),
      );
      let from: { equipment: Equipment; port: string } = { equipment: control, port };
      chain.forEach((receiver, index) => {
        const decoder = catalog.get(receiver.catalogId)?.specs.kind === 'decoder';
        links.push({
          id: `${base}-${index + 1}`,
          from: { ref: from.equipment.id, port: from.port },
          to: { ref: receiver.id, ...(decoder ? { port: 'DATA-IN' } : {}) },
          protocol,
          lengthFt: linkLength(from.equipment, receiver),
          env: receiver.env,
        });
        from = { equipment: receiver, port: 'DATA-OUT' };
      });
    } else
      receivers.forEach((receiver, index) =>
        links.push({
          id: `${base}-${index + 1}`,
          from: { ref: control.id, port },
          to: { ref: receiver.id },
          protocol,
          lengthFt: linkLength(control, receiver),
          env: receiver.env,
        }),
      );
  }
  return links;
}

/** The design with its derived control links added to the engineering ones. */
export function withDerivedControlLinks<T extends Pick<Design, 'runs' | 'zones' | 'project'>>(
  design: T,
  catalog: ReadonlyMap<string, CatalogItem>,
): T {
  const derived = deriveControlLinks(design as unknown as Design, catalog);
  return derived.length
    ? { ...design, project: { ...design.project, controlLinks: [...design.project.controlLinks, ...derived] } }
    : design;
}

/**
 * The designer's control checks (Appendix C): zones nothing dims, DMX runs on supplies DMX cannot dim, and
 * controls that are not connected to anything yet.
 */
export function controlChecks(design: Design, catalog: ReadonlyMap<string, CatalogItem>): ValidationMessage[] {
  const messages: ValidationMessage[] = [];
  for (const zone of design.zones) {
    const protocol = ZONE_CONTROL_PROTOCOL[zone.method];
    const runs = design.runs.filter((run) => run.zoneId === zone.id);
    if (!protocol || !runs.length) continue;
    if (!zone.control || !design.project.equipment.some((item) => item.id === zone.control!.equipmentId))
      messages.push(
        message(
          'ZONE_NO_CONTROL',
          'warning',
          zone.id,
          `${zone.name} dims by ${methodLabel(zone.method)}; choose the control output that dims it on the Power step.`,
        ),
      );
    if (DECODER_METHODS.has(zone.method)) {
      const { strays } = zoneReceivers(design, catalog, zone, protocol);
      if (strays.length)
        messages.push(
          message(
            'DMX_RUN_NO_DECODER',
            'warning',
            zone.id,
            `${zone.name} dims by DMX, but ${strays.length === 1 ? `${strays[0]} is` : `${strays.length} runs are`} on a supply DMX cannot dim${strays.length > 1 ? ` (${strays.slice(0, 4).join(', ')}${strays.length > 4 ? ', …' : ''})` : ''}. Put ${strays.length === 1 ? 'it' : 'them'} on a decoder channel.`,
          ),
        );
    }
  }
  const used = new Set<string>();
  for (const run of design.runs) if (run.assignment) used.add(run.assignment.equipmentId);
  for (const zone of design.zones) if (zone.control) used.add(zone.control.equipmentId);
  for (const item of design.project.equipment) {
    if (item.controlFrom) used.add(item.controlFrom.ref);
    if (item.fedFrom.port) used.add(item.fedFrom.ref);
  }
  for (const link of design.project.controlLinks) {
    used.add(link.from.ref);
    used.add(link.to.ref);
  }
  for (const item of design.project.equipment) {
    if (!isControl(item, catalog) || used.has(item.id) || used.has(item.tag)) continue;
    const decoder = catalog.get(item.catalogId)?.specs.kind === 'decoder';
    messages.push(
      message(
        'CONTROL_UNUSED',
        'info',
        item.id,
        `${item.tag} (${controlLabel(catalog.get(item.catalogId))}${item.scheduleLine ? ', on the schedule' : ''}) ${decoder ? 'carries no runs' : 'dims no zone'} yet.`,
      ),
    );
  }
  return messages;
}

