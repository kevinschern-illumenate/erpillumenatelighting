import { line, text, SymbolSchema, type LayerName, type SymbolDef } from '../model';

export const SYMBOL_HEIGHT = 1.825;

/** Riser equipment is shown as labeled equipment, rather than pictorial plan symbols. */
export function makeSymbol(
  id: string,
  label: string,
  layer: LayerName,
  glyph: string,
  channels = 5,
): SymbolDef {
  const width = 2.8,
    height = SYMBOL_HEIGHT;
  const attrs = [
    { tag: 'TAG', x: 0.14, y: 1.565, height: 0.125, visible: true },
    { tag: 'MODEL', x: 0.14, y: 0.99, height: 0.09375, visible: false },
    { tag: 'VIN', x: 0.14, y: 0.38, height: 0.09375, visible: true },
    { tag: 'VOUT', x: 1.5, y: 0.38, height: 0.09375, visible: true },
    { tag: 'WATTS', x: 0.14, y: 0.19, height: 0.09375, visible: true },
    { tag: 'LOAD_PCT', x: 1.5, y: 0.19, height: 0.09375, visible: true },
    { tag: 'DMX_ADDR', x: 0.14, y: 0.56, height: 0.09375, visible: true },
    { tag: 'LOCATION', x: 0.14, y: 0.56, height: 0.09375, visible: false },
  ].map((a) => ({ ...a, default: '', hAlign: 'left' as const }));
  return SymbolSchema.parse({
    id,
    label,
    widthIn: width,
    heightIn: height,
    prims: [
      { kind: 'rect', x: 0, y: 0, width, height, layer, lineweightMm: 0.35 },
      text(
        glyph === 'tape' ? `LED TAPE / ${channels} CH` : label.toUpperCase(),
        0.14,
        1.355,
        0.09375,
        layer,
      ),
      { ...line(0, 1.245, width, 1.245, layer), lineweightMm: 0.18 },
    ],
    ports: [
      { name: 'POWER-IN', side: 'W', offset: height / 2 },
      { name: 'POWER-OUT', side: 'E', offset: height / 2 },
      { name: 'DATA-IN', side: 'N', offset: width / 2 },
      { name: 'DATA-OUT', side: 'S', offset: width / 2 },
    ],
    attributes: attrs,
  });
}
