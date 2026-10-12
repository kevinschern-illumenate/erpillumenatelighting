import { current, isDraft, type Draft as Mutable } from 'immer';
import type { CatalogItem } from '@ill/core-schemas/catalog';
import type { Design } from '@ill/core-schemas/design';
import {
  ControlLinkSchema,
  EquipmentSchema,
  ProjectSettingsSchema,
  SourceSchema,
  type ControlLink,
  type Equipment,
  type Load,
  type ProjectSettings,
  type Source,
} from '@ill/core-schemas/project';
import { deriveLoads } from '@ill/engine/derive';
import { parsePort } from '@ill/engine/ports';
import { removeSupply } from '@ill/engine/power';
import { addCircuit, removeCircuit } from '@ill/engine/site';

/**
 * Engineering mode (plan §7, WP-3.8): the riser's tables bound to the design. Sources, equipment and
 * control links edit the design's project; loads come from the runs and are read-only here. Every edit
 * is checked against the project schema before it lands, and removals use the same helpers as the
 * guided steps so runs and cabinets stay consistent.
 */

export type GridKey = 'sources' | 'equipment' | 'loads' | 'controlLinks';
export type GridRow = Source | Equipment | Load | ControlLink;

export const GRIDS: { key: GridKey; label: string; editable: boolean }[] = [
  { key: 'sources', label: 'Circuits', editable: true },
  { key: 'equipment', label: 'Equipment', editable: true },
  { key: 'loads', label: 'Loads', editable: false },
  { key: 'controlLinks', label: 'Control links', editable: true },
];

export const GRID_FIELDS: Record<GridKey, string[]> = {
  sources: ['tag', 'panel', 'circuit', 'voltage', 'phase', 'breakerA', 'poles', 'switching', 'notes'],
  equipment: [
    'tag',
    'catalogId',
    'qty',
    'location',
    'enclosure',
    'fedFrom',
    'feedLengthFt',
    'controlFrom',
    'controlLengthFt',
    'chainOrder',
    'universe',
    'startAddress',
    'terminatorPresent',
    'env',
    'notes',
  ],
  loads: [
    'typeTag',
    'catalogId',
    'zone',
    'qty',
    'lengthFt',
    'fedFrom',
    'homeRunLengthFt',
    'feedMethod',
    'feeds',
    'env',
    'notes',
  ],
  controlLinks: ['protocol', 'from', 'to', 'lengthFt', 'env', 'universe', 'notes'],
};

const NUMERIC = new Set([
  'voltage',
  'breakerA',
  'poles',
  'qty',
  'lengthFt',
  'feedLengthFt',
  'controlLengthFt',
  'chainOrder',
  'universe',
  'homeRunLengthFt',
  'feeds',
]);
const PORTS = new Set(['fedFrom', 'controlFrom', 'from', 'to']);
const DMX = new Set(['universe', 'startAddress', 'terminatorPresent']);
const SUPPLY_KINDS = new Set(['tape', 'fixture', 'incomplete']);
const copy = <T>(value: T): T => structuredClone(isDraft(value) ? (current(value as Mutable<T>) as T) : value);

export function gridRows(design: Design, key: GridKey): GridRow[] {
  return key === 'loads' ? deriveLoads(design) : design.project[key];
}

/** A cell's value as the grid shows it; ports read `REF::PORT`. */
export function readCell(row: GridRow, field: string): unknown {
  if (DMX.has(field) && 'dmx' in row) return row.dmx?.[field as keyof NonNullable<typeof row.dmx>] ?? '';
  const value = (row as unknown as Record<string, unknown>)[field];
  if (value && typeof value === 'object' && 'ref' in value) {
    const port = value as { ref: string; port?: string };
    return `${port.ref}${port.port ? `::${port.port}` : ''}`;
  }
  return value ?? '';
}

const label = (field: string) =>
  field
    .replace(/Ft$/, ' (ft)')
    .replace(/([A-Z])/g, ' $1')
    .toLowerCase();

function number(field: string, raw: unknown): number | undefined {
  if (raw === '' || raw === undefined || raw === null) return undefined;
  const value = Number(raw);
  if (!Number.isFinite(value)) throw new Error(`Enter a number for ${label(field)}.`);
  return value;
}

function firstIssue(error: { issues: { path: PropertyKey[]; message: string }[] }) {
  const issue = error.issues[0]!;
  return `${issue.path.length ? `${label(String(issue.path[0]))}: ` : ''}${issue.message}`;
}

/** Change one cell. Throws a message for the user when the value does not fit the row. */
export function editCell(
  design: Mutable<Design>,
  key: GridKey,
  rowId: string,
  field: string,
  raw: unknown,
  catalog: readonly CatalogItem[],
) {
  if (key === 'loads') throw new Error('Loads come from the runs. Change them on the Runs step.');
  const rows = design.project[key] as GridRow[];
  const index = rows.findIndex((row) => row.id === rowId);
  if (index < 0) throw new Error('That row no longer exists.');
  const next = copy(rows[index]) as unknown as Record<string, unknown>;
  const text = typeof raw === 'string' ? raw.trim() : raw;
  if (PORTS.has(field)) {
    if (!text && field === 'controlFrom') {
      delete next.controlFrom;
      delete next.controlLengthFt;
    } else {
      if (!text) throw new Error(`Choose a ${label(field)}.`);
      next[field] = parsePort(String(text));
      if (field === 'controlFrom' && next.controlLengthFt === undefined) next.controlLengthFt = 0;
    }
  } else if (DMX.has(field) && key === 'equipment') {
    next.dmx = {
      universe: 1,
      startAddress: 'auto',
      ...((next.dmx as object | undefined) ?? {}),
      [field]:
        field === 'startAddress'
          ? text === 'auto' || text === ''
            ? 'auto'
            : number(field, text)
          : field === 'terminatorPresent'
            ? text === true || text === 'true'
            : number(field, text),
    };
  } else if (field === 'enclosure' || field === 'notes' || field === 'switching' || field === 'chainOrder') {
    const value = field === 'chainOrder' ? number(field, text) : text;
    if (value === '' || value === undefined) delete next[field];
    else next[field] = value;
  } else if (NUMERIC.has(field)) {
    const value = number(field, text);
    if (value === undefined) delete next[field];
    else next[field] = value;
  } else next[field] = text;
  if (field === 'catalogId') {
    const item = catalog.find((product) => product.id === text || product.sku === text);
    if (!item) throw new Error('Choose a product from the ilLumenate catalog.');
    if (item.specs.kind === 'incomplete') throw new Error(`${item.sku} needs specifications before it can be used.`);
    if (SUPPLY_KINDS.has(item.specs.kind)) throw new Error('Choose equipment, not tape or a fixture.');
    next.catalogId = item.id;
    next.category = item.category;
    if (item.category === 'dmx-0-10v-converter') next.dmx ??= { universe: 1, startAddress: 'auto' };
  }
  if (field === 'tag') {
    const taken = [...design.project.sources, ...design.project.equipment].some(
      (row) => row.id !== rowId && row.tag === next.tag,
    );
    if (taken) throw new Error(`${String(next.tag)} is already used.`);
  }
  const schema = key === 'sources' ? SourceSchema : key === 'equipment' ? EquipmentSchema : ControlLinkSchema;
  const parsed = schema.safeParse(next);
  if (!parsed.success) throw new Error(firstIssue(parsed.error));
  rows[index] = parsed.data;
}

function nextNumber(tags: string[], prefix: string) {
  let n = 1;
  while (tags.includes(`${prefix}${n}`)) n += 1;
  return n;
}

/** Add a row; returns its id. */
export function addRow(design: Mutable<Design>, key: GridKey, catalog: readonly CatalogItem[]): string {
  if (key === 'loads') throw new Error('Loads come from the runs. Change them on the Runs step.');
  if (key === 'sources') return addCircuit(design as Design);
  if (key === 'equipment') {
    const item =
      catalog.find((product) => product.specs.kind === 'psu') ??
      catalog.find((product) => !SUPPLY_KINDS.has(product.specs.kind));
    if (!item) throw new Error('The catalog has no equipment to add.');
    const tags = [...design.project.sources, ...design.project.equipment].map((row) => row.tag);
    const tag = `PS-${nextNumber(tags, 'PS-')}`;
    const row = EquipmentSchema.parse({
      id: tag,
      tag,
      catalogId: item.id,
      category: item.category,
      qty: 1,
      location: 'Unassigned',
      fedFrom: { ref: 'unassigned' },
      feedLengthFt: 0,
      env: 'dry-concealed',
    });
    while (design.project.equipment.some((other) => other.id === row.id)) row.id += 'x';
    design.project.equipment.push(row);
    return row.id;
  }
  const ids = design.project.controlLinks.map((link) => link.id);
  const id = `CL-${nextNumber(ids, 'CL-')}`;
  const [from, to] = design.project.equipment;
  design.project.controlLinks.push(
    ControlLinkSchema.parse({
      id,
      from: { ref: from?.id ?? 'unassigned' },
      to: { ref: to?.id ?? 'unassigned' },
      protocol: 'DMX512',
      lengthFt: 0,
      env: 'dry-concealed',
    }),
  );
  return id;
}

/** Remove rows; supplies and circuits release their runs, cabinets and control links. */
export function removeRows(design: Mutable<Design>, key: GridKey, ids: readonly string[]) {
  if (key === 'loads') throw new Error('Loads come from the runs. Change them on the Runs step.');
  const gone = new Set(ids);
  if (key === 'sources') for (const id of ids) removeCircuit(design as Design, id);
  else if (key === 'equipment') {
    const tags = new Set(design.project.equipment.filter((row) => gone.has(row.id)).map((row) => row.tag));
    for (const id of ids) removeSupply(design as Design, id);
    design.project.controlLinks = design.project.controlLinks.filter(
      (link) => ![link.from.ref, link.to.ref].some((ref) => gone.has(ref) || tags.has(ref)),
    );
    for (const row of design.project.equipment)
      if (row.controlFrom && (gone.has(row.controlFrom.ref) || tags.has(row.controlFrom.ref))) {
        delete row.controlFrom;
        delete row.controlLengthFt;
      }
  } else design.project.controlLinks = design.project.controlLinks.filter((link) => !gone.has(link.id));
}

// --- Project settings -------------------------------------------------------------------------------

export interface SettingField {
  key: keyof ProjectSettings | 'sheetFlow';
  label: string;
  options?: readonly (string | number)[];
  kind: 'select' | 'number' | 'boolean';
  /** Settings that can make a design less conservative: ilLumenate staff only. */
  staffOnly: boolean;
}

/** Voltage-drop targets stay on the Check step, which applies the Settings limits (D5). */
export const SETTING_FIELDS: SettingField[] = [
  { key: 'necEdition', label: 'NEC edition', kind: 'select', options: ['2020', '2023', '2026'], staffOnly: false },
  { key: 'units', label: 'Units', kind: 'select', options: ['ft', 'm'], staffOnly: false },
  {
    key: 'drawingFont',
    label: 'Drawing font',
    kind: 'select',
    options: ['Arimo', 'RobotoCondensed'],
    staffOnly: false,
  },
  { key: 'showSchedules', label: 'Schedules on the riser', kind: 'boolean', staffOnly: false },
  { key: 'sheetFlow', label: 'Riser flow', kind: 'select', options: ['LR', 'TB'], staffOnly: false },
  { key: 'wireWastePct', label: 'Wire waste (%)', kind: 'number', staffOnly: false },
  { key: 'dmxAutoPatchRoundTo', label: 'DMX patch rounding', kind: 'number', staffOnly: false },
  { key: 'psuDeratePct', label: 'Supply operating target (%)', kind: 'number', staffOnly: true },
  { key: 'continuousLoadFactor', label: 'Continuous load factor', kind: 'number', staffOnly: true },
  { key: 'breakerLoadLimitPct', label: 'Breaker load limit (%)', kind: 'number', staffOnly: true },
  { key: 'tapeLengthMarginPct', label: 'Tape length margin (%)', kind: 'number', staffOnly: true },
  { key: 'terminationTempC', label: 'Termination rating (°C)', kind: 'select', options: [60, 75, 90], staffOnly: true },
  {
    key: 'minAwgLineVoltage',
    label: 'Smallest line-voltage wire (AWG)',
    kind: 'select',
    options: ['14', '12', '10'],
    staffOnly: true,
  },
  {
    key: 'vdMethod',
    label: 'DC voltage-drop method',
    kind: 'select',
    options: ['lumped-at-end', 'distributed'],
    staffOnly: true,
  },
  {
    key: 'acVdMethod',
    label: 'AC voltage-drop method',
    kind: 'select',
    options: ['dc-resistance', 'effective-z'],
    staffOnly: true,
  },
  { key: 'dmxMaxUnitLoads', label: 'DMX unit loads per segment', kind: 'number', staffOnly: true },
  { key: 'dmxMaxLengthFt', label: 'DMX segment length (ft)', kind: 'number', staffOnly: true },
  { key: 'spiMaxDataFt', label: 'SPI data run (ft)', kind: 'number', staffOnly: true },
];

export function readSetting(settings: ProjectSettings, key: SettingField['key']): string | number | boolean {
  return key === 'sheetFlow' ? settings.sheet.flow : (settings[key] as string | number | boolean);
}

/** Change one project setting; staff-only settings refuse dealers. */
export function editSetting(design: Mutable<Design>, key: SettingField['key'], raw: unknown, staff: boolean) {
  const field = SETTING_FIELDS.find((item) => item.key === key);
  if (!field) throw new Error('Unknown setting.');
  if (field.staffOnly && !staff) throw new Error(`${field.label} is set by ilLumenate.`);
  const value =
    field.kind === 'number' || (field.options && typeof field.options[0] === 'number')
      ? Number(raw)
      : field.kind === 'boolean'
        ? raw === true || raw === 'true'
        : String(raw);
  const settings = copy(design.project.settings) as ProjectSettings;
  if (key === 'sheetFlow') settings.sheet = { ...settings.sheet, flow: value as 'LR' | 'TB' };
  else (settings as Record<string, unknown>)[key] = value;
  const parsed = ProjectSettingsSchema.safeParse(settings);
  if (!parsed.success) throw new Error(`${field.label}: ${parsed.error.issues[0]!.message}`);
  design.project.settings = parsed.data;
}
