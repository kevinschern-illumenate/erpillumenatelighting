import { seedLayers } from '@ill/data/seeds';
import archC from '@ill/data/titleblocks/arch-c.json';
import archD from '@ill/data/titleblocks/arch-d.json';
import ansiA from '@ill/data/titleblocks/ansi-a.json';
import ansiB from '@ill/data/titleblocks/ansi-b.json';
import ansiD from '@ill/data/titleblocks/ansi-d.json';
import type { Primitive, SymbolDef } from './model';
import { symbols } from './symbols';

/**
 * The AutoCAD toolkit's drawing assets (draw-to-quote plan 1.6, 3.3, 3.4), generated from the riser's
 * own sources so the plan and the riser read the same: the layer standard (riser layers plus the
 * plan-view layers), the riser equipment symbols, plan symbols, and the title blocks.
 *
 * The output is AutoLISP *data* (`tools/cad_toolkit/lisp/il-assets.lsp`); `il-blocks.lsp` turns it into
 * layers and block definitions with `entmake`, which works on full AutoCAD, LT 2024+ and Mac without a
 * DWG library. A test keeps the committed file equal to this output.
 */

type Item =
  | ['LINE', number, number, number, number, string]
  | ['PLINE', number[], boolean, string]
  | ['CIRCLE', number, number, number, string]
  | ['ARC', number, number, number, number, number, string]
  | ['TEXT', number, number, number, string, string, string]
  | ['ATTDEF', string, number, number, number, string, boolean, string];

interface BlockData {
  name: string;
  description: string;
  items: Item[];
}

/** Riser symbols reused on the plan, by riser id → block name. */
export const PLAN_FROM_RISER: Record<string, string> = {
  psu: 'IL-PSU',
  'cc-driver': 'IL-DRIVER',
  decoder: 'IL-DECODER',
  console: 'IL-CONTROLLER',
  junction: 'IL-JBOX',
};

const round = (value: number) => Math.round(value * 10000) / 10000;

function primitiveItems(prim: Primitive): Item[] {
  switch (prim.kind) {
    case 'line':
      return [['LINE', prim.from.x, prim.from.y, prim.to.x, prim.to.y, prim.layer]];
    case 'rect':
      return [
        ['PLINE', [prim.x, prim.y, prim.x + prim.width, prim.y, prim.x + prim.width, prim.y + prim.height, prim.x, prim.y + prim.height], true, prim.layer],
      ];
    case 'polyline':
      return [['PLINE', prim.points.flatMap((point) => [point.x, point.y]), Boolean(prim.closed), prim.layer]];
    case 'circle':
      return [['CIRCLE', prim.x, prim.y, prim.radius, prim.layer]];
    case 'arc':
      return [['ARC', prim.x, prim.y, prim.radius, prim.startDeg ?? 0, prim.endDeg ?? 360, prim.layer]];
    case 'text':
      return [['TEXT', prim.x, prim.y, prim.heightIn, prim.value, prim.hAlign, prim.layer]];
    default:
      return []; // hatches and filled paths stay riser-only
  }
}

export function riserBlock(symbol: SymbolDef, name: string): BlockData {
  const items: Item[] = symbol.prims.flatMap(primitiveItems);
  const layer = symbol.prims[0]?.layer ?? 'E-POWR-EQPM';
  for (const attribute of symbol.attributes)
    items.push(['ATTDEF', attribute.tag, attribute.x, attribute.y, attribute.height, attribute.default, attribute.visible, layer]);
  return { name, description: `${symbol.label} (riser symbol ${symbol.id})`, items };
}

const tag = (name: string, x: number, y: number, height: number, layer: string, visible = true): Item =>
  ['ATTDEF', name, x, y, height, '', visible, layer];

/** Plan-only symbols, in paper inches at 1:1 (inserted at the drawing scale). */
export function planBlocks(): BlockData[] {
  const square = (size: number): number[] => [-size, -size, size, -size, size, size, -size, size];
  return [
    {
      name: 'IL-CABINET',
      description: 'Power supply cabinet or location',
      items: [
        ['PLINE', [-0.5, -0.3, 0.5, -0.3, 0.5, 0.3, -0.5, 0.3], true, 'E-POWR-CABN'],
        ['LINE', -0.5, -0.3, 0.5, 0.3, 'E-POWR-CABN'],
        tag('TAG', -0.45, 0.38, 0.125, 'E-ANNO-TAGS'),
        tag('RATING', -0.45, -0.5, 0.09375, 'E-ANNO-TAGS'),
        tag('ACCESS', -0.45, -0.65, 0.09375, 'E-ANNO-TAGS', false),
      ],
    },
    {
      name: 'IL-FEED',
      description: 'Feed point on a run',
      items: [
        ['CIRCLE', 0, 0, 0.08, 'E-LITE-FEED'],
        ['PLINE', [-0.08, 0.12, 0.08, 0.12, 0, 0.26], true, 'E-LITE-FEED'],
      ],
    },
    {
      name: 'IL-END',
      description: 'End of a run (endcap)',
      items: [['LINE', 0, -0.1, 0, 0.1, 'E-LITE-FEED']],
    },
    {
      name: 'IL-JUMPER',
      description: 'Jumper between two segments of a run',
      items: [
        ['CIRCLE', 0, 0, 0.06, 'E-LITE-FEED'],
        ['LINE', -0.1, -0.1, 0.1, 0.1, 'E-LITE-FEED'],
      ],
    },
    {
      name: 'IL-RUNTAG',
      description: 'Run tag: id, style and lengths',
      items: [
        ['PLINE', [-0.3, -0.1, 0.3, -0.1, 0.38, 0, 0.3, 0.1, -0.3, 0.1, -0.38, 0], true, 'E-ANNO-TAGS'],
        tag('TAG', -0.26, -0.047, 0.09375, 'E-ANNO-TAGS'),
        tag('STYLE', -0.38, -0.25, 0.09375, 'E-ANNO-TAGS'),
        tag('LENGTH', -0.38, -0.4, 0.09375, 'E-ANNO-TAGS'),
        tag('PART', -0.38, -0.55, 0.09375, 'E-ANNO-TAGS', false),
      ],
    },
    {
      name: 'IL-PSUTAG',
      description: 'PSU tag with provisional load',
      items: [
        ['PLINE', square(0.18), true, 'E-ANNO-TAGS'],
        tag('TAG', -0.15, -0.047, 0.09375, 'E-ANNO-TAGS'),
        tag('LOAD', -0.18, -0.33, 0.09375, 'E-ANNO-TAGS'),
        tag('MODEL', -0.18, -0.48, 0.09375, 'E-ANNO-TAGS', false),
      ],
    },
    {
      name: 'IL-WIRETAG',
      description: 'Wire tag',
      items: [
        ['CIRCLE', 0, 0, 0.12, 'E-ANNO-TAGS'],
        tag('TAG', -0.09, -0.047, 0.09375, 'E-ANNO-TAGS'),
        tag('LENGTH', 0.16, -0.047, 0.09375, 'E-ANNO-TAGS'),
      ],
    },
    {
      name: 'IL-ROOMTAG',
      description: 'Room tag',
      items: [
        tag('NAME', 0, 0, 0.125, 'E-ANNO-ROOM'),
        tag('ID', 0, -0.18, 0.09375, 'E-ANNO-ROOM'),
        tag('ENV', 0, -0.33, 0.09375, 'E-ANNO-ROOM'),
      ],
    },
    {
      name: 'IL-ISSUE',
      description: 'ILCHECK issue marker (no-plot layer)',
      items: [
        ['CIRCLE', 0, 0, 0.15, 'E-ANNO-ISSU'],
        ['LINE', 0, -0.05, 0, 0.09, 'E-ANNO-ISSU'],
        ['CIRCLE', 0, -0.09, 0.012, 'E-ANNO-ISSU'],
        tag('CODE', 0.2, -0.047, 0.09375, 'E-ANNO-ISSU'),
      ],
    },
  ];
}

interface TitleBlockJson {
  id: string;
  widthIn: number;
  heightIn: number;
  border: { x: number; y: number; width: number; height: number };
  titleBlock: { x: number; y: number; width: number; height: number };
  fields: { name: string; region: { x: number; y: number; width: number; height: number }; textHeightIn: number }[];
}

const FIELD_LABELS: Record<string, string> = {
  brandLogo: 'ilLumenate',
  project: 'PROJECT',
  number: 'PROJECT NO.',
  client: 'CLIENT',
  address: 'SITE',
  sheetTitle: 'SHEET TITLE',
  sheetNumber: 'SHEET',
  date: 'DATE',
  scale: 'SCALE',
  drawnBy: 'DRAWN BY',
  checkedBy: 'CHECKED BY',
  revision: 'REV',
  stamp: 'STATUS',
};

export function titleBlock(json: TitleBlockJson): BlockData {
  const rect = (r: { x: number; y: number; width: number; height: number }): number[] => [
    r.x, r.y, r.x + r.width, r.y, r.x + r.width, r.y + r.height, r.x, r.y + r.height,
  ];
  const items: Item[] = [
    ['PLINE', rect(json.border), true, 'E-ANNO-TTLB'],
    ['PLINE', rect(json.titleBlock), true, 'E-ANNO-TTLB'],
  ];
  for (const field of json.fields) {
    const { x, y, width, height } = field.region;
    items.push(['PLINE', rect(field.region), true, 'E-ANNO-TTLB']);
    const label = FIELD_LABELS[field.name] ?? field.name.toUpperCase();
    if (field.name === 'brandLogo') {
      items.push(['TEXT', x + 0.08, y + height / 2, 0.25, label, 'left', 'E-ANNO-TTLB']);
      continue;
    }
    items.push(['TEXT', x + 0.06, y + height - 0.16, 0.0625 > field.textHeightIn ? 0.0625 : field.textHeightIn * 0.8, label, 'left', 'E-ANNO-TTLB']);
    items.push(['ATTDEF', field.name.replace(/([A-Z])/g, '_$1').toUpperCase(), x + 0.06, y + Math.min(height / 2, 0.3), field.textHeightIn * 1.33, '', true, 'E-ANNO-TEXT']);
    void width;
  }
  return { name: `IL-TB-${json.id.toUpperCase()}`, description: `${json.id.toUpperCase()} title block (${json.widthIn} x ${json.heightIn} in)`, items };
}

// --- AutoLISP text -------------------------------------------------------------------------------

/** AutoLISP files are read in the drawing's code page: keep strings ASCII (en dash → hyphen, and so on). */
const ascii = (value: string) =>
  value
    .replace(/[\u2012-\u2015]/g, '-')
    .replace(/[\u2018\u2019]/g, "'")
    .replace(/[\u201C\u201D]/g, '"')
    .replace(/\u00D7/g, 'x')
    .normalize('NFKD')
    .replace(/[^\x20-\x7E]/g, '');
const lispString = (value: string) => `"${ascii(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"')}"`;
const lispNumber = (value: number) => {
  const rounded = round(value);
  return Number.isInteger(rounded) ? `${rounded}.0` : String(rounded);
};
const lispValue = (value: unknown): string =>
  typeof value === 'string'
    ? lispString(value)
    : typeof value === 'number'
      ? lispNumber(value)
      : typeof value === 'boolean'
        ? value
          ? 'T'
          : 'nil'
        : Array.isArray(value)
          ? `(${value.map(lispValue).join(' ')})`
          : 'nil';

function blockLisp(block: BlockData): string {
  const items = block.items.map((item) => `   ${lispValue(item)}`).join('\n');
  return `  (${lispString(block.name)} ${lispString(block.description)}\n${items})`;
}

export function cadAssets() {
  const riser = symbols.filter((symbol) => PLAN_FROM_RISER[symbol.id]).map((symbol) => riserBlock(symbol, PLAN_FROM_RISER[symbol.id]!));
  const titleBlocks = [archC, archD, ansiA, ansiB, ansiD].map((json) => titleBlock(json as unknown as TitleBlockJson));
  const layers = [
    ...seedLayers.layers.map((layer) => ({ ...layer, plot: layer.export })),
    ...seedLayers.planLayers,
  ];
  return { riser, plan: planBlocks(), titleBlocks, layers, linetypes: seedLayers.linetypes };
}

/** The committed `il-assets.lsp`: data only, no commands. */
export function cadAssetsLisp(): string {
  const { riser, plan, titleBlocks, layers, linetypes } = cadAssets();
  const layerRows = layers
    .map(
      (layer) =>
        `  (${lispString(layer.name)} ${layer.aciColor} ${[layer.linetype, layer.lineweightMm, layer.plot, layer.description].map(lispValue).join(' ')})`,
    )
    .join('\n');
  const linetypeRows = linetypes
    .map((linetype) => `  (${[linetype.name, linetype.description, linetype.patternIn].map(lispValue).join(' ')})`)
    .join('\n');
  const blocks = [...riser, ...plan, ...titleBlocks].map(blockLisp).join('\n');
  return [
    ';;; il-assets.lsp: GENERATED by tools/system_designer/scripts/export-cad-assets.mjs. Do not edit.',
    ';;; Layers, linetypes and blocks of the ilLumenate CAD toolkit (draw-to-quote plan 1.6, 3.3, 3.4),',
    ';;; from the riser layer standard, symbols and title blocks. il-blocks.lsp builds them with entmake.',
    ';;; Layer row: (name aci linetype lineweight-mm plot description). Block item kinds: LINE, PLINE,',
    ';;; CIRCLE, ARC, TEXT and ATTDEF, in paper inches at 1:1.',
    '',
    '(setq *il-asset-layers* (quote (',
    layerRows,
    ')))',
    '',
    '(setq *il-asset-linetypes* (quote (',
    linetypeRows,
    ')))',
    '',
    '(setq *il-asset-blocks* (quote (',
    blocks,
    ')))',
    '',
  ].join('\n');
}
