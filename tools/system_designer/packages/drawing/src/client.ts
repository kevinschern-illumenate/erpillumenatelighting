import type { CatalogItem } from '@ill/core-schemas/catalog';
import type { RunResult } from '@ill/engine/model';
import type { Primitive, SymbolDef } from './model';
import type { ClientProductType } from './options';
import { LOW_VOLTAGE_TYPES } from './wires';

/**
 * The client diagram's colour key (plan §12.2): one colour per product family and per wire family.
 * Colours print legibly on white and in greyscale (distinct lightness), and every colour also has a
 * name in the key on the schedule page, so nothing depends on colour alone.
 */
export type ClientFamily = ClientProductType | 'power' | 'control' | 'panel';

export const PRODUCT_COLORS: Record<
  ClientFamily,
  { label: string; heading: string; stroke: string; fill: string }
> = {
  linear: {
    label: 'Linear fixtures',
    heading: 'LINEAR FIXTURE',
    stroke: '#0F766E',
    fill: '#DDF1EE',
  },
  tape: { label: 'LED tape', heading: 'LED TAPE', stroke: '#15803D', fill: '#E3F4E8' },
  neon: { label: 'LED neon', heading: 'LED NEON', stroke: '#BE185D', fill: '#FBE7F1' },
  sheet: { label: 'LED sheets', heading: 'LED SHEET', stroke: '#0369A1', fill: '#E0F0FA' },
  fixture: { label: 'Other fixtures', heading: 'FIXTURE', stroke: '#4338CA', fill: '#E8E8FB' },
  power: { label: 'Power supplies', heading: 'POWER SUPPLY', stroke: '#B45309', fill: '#FDF0E0' },
  control: { label: 'Controls', heading: 'CONTROL', stroke: '#7E22CE', fill: '#F3E8FD' },
  panel: { label: 'Panel circuits', heading: 'PANEL CIRCUIT', stroke: '#475569', fill: '#EEF2F6' },
};

export type WireFamily = 'lv' | 'line' | 'landscape' | 'signal' | 'data' | 'lutron' | 'wireless';

export const WIRE_COLORS: Record<WireFamily, { label: string; color: string }> = {
  lv: { label: 'LV Wire (low-voltage power)', color: '#DC2626' },
  line: { label: 'Line voltage (by electrician)', color: '#1F2937' },
  landscape: { label: 'Landscape wire', color: '#92400E' },
  signal: { label: '0-10V and DALI control wire', color: '#7C3AED' },
  data: { label: 'DMX, Ethernet and pixel data', color: '#2563EB' },
  lutron: { label: 'Lutron control wire', color: '#4D7C0F' },
  wireless: { label: 'Wireless link', color: '#DB2777' },
};

export function wireFamily(run: Pick<RunResult, 'type'>): WireFamily {
  if (LOW_VOLTAGE_TYPES.includes(run.type)) return 'lv';
  if (run.type === 'landscape-ac') return 'landscape';
  if (run.type.startsWith('lv-')) return 'line';
  if (['dmx', 'ethernet', 'spi-data'].includes(run.type)) return 'data';
  if (run.type.startsWith('lutron')) return 'lutron';
  if (run.type === 'wireless') return 'wireless';
  return 'signal';
}

const LOAD_CATEGORIES = new Set(['tape', 'fixture']);

/** The family of a node: its load entry when the app named one, else its catalog category. */
export function productFamily(
  item: CatalogItem | undefined,
  source: boolean,
  control: boolean,
  load?: ClientProductType,
): ClientFamily {
  if (source) return 'panel';
  if (load) return load;
  if (['psu', 'driver'].includes(item?.category ?? '')) return 'power';
  if (control) return 'control';
  if (item?.specs.kind === 'tape') return 'tape';
  if (LOAD_CATEGORIES.has(item?.category ?? '')) return 'fixture';
  return 'control';
}

/**
 * A symbol drawn in a family's colours: a tinted body behind the outline, the heading replaced by the
 * family's name. The hatch is first so every serializer paints it below the outline and text.
 */
export function clientSymbol(symbol: SymbolDef, family: ClientFamily): SymbolDef {
  const colors = PRODUCT_COLORS[family];
  const body = symbol.prims.find((p) => p.kind === 'rect');
  const tint: Primitive[] =
    body?.kind === 'rect'
      ? [
          {
            kind: 'hatch',
            layer: body.layer,
            color: colors.fill,
            points: [
              { x: body.x, y: body.y },
              { x: body.x + body.width, y: body.y },
              { x: body.x + body.width, y: body.y + body.height },
              { x: body.x, y: body.y + body.height },
            ],
          },
        ]
      : [];
  let headed = false;
  return {
    ...symbol,
    id: `${symbol.id}-client-${family}`,
    prims: [
      ...tint,
      ...symbol.prims.map((p): Primitive => {
        if (p.kind === 'text' && !headed) {
          headed = true;
          return { ...p, value: colors.heading, font: 'bold', color: colors.stroke };
        }
        return p.kind === 'text' ? p : { ...p, color: colors.stroke };
      }),
    ],
  };
}
