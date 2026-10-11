import type { Sheet } from './model';
import type { DrawingView } from './options';

const RATINGS = ['VIN', 'VOUT', 'WATTS', 'LOAD_PCT'];

/**
 * Leaves off the card and wire details the dealer hid (Views step). Positions stay as laid out,
 * so turning a detail back on never moves the drawing; every serializer then draws the same sheet.
 */
export function applyView(sheets: Sheet[], view: DrawingView = {}): void {
  const cleared = [...(view.dmx === false ? ['DMX_ADDR'] : []), ...(view.ratings === false ? RATINGS : [])];
  const dropped = new Set([
    ...(view.wireLabels === false ? ['wire-tag'] : []),
    ...(view.models === false ? ['model'] : []),
    ...(view.lengths === false ? ['annotation'] : []),
  ]);
  if (!cleared.length && !dropped.size) return;
  for (const sheet of sheets) {
    // Schedule pages carry no layout nodes; their legend symbols keep their labels.
    if (!sheet.nodes.length) continue;
    sheet.prims = sheet.prims.filter((p) => !p.role || !dropped.has(p.role));
    for (const p of sheet.prims)
      if (p.kind === 'block' && p.entityId)
        for (const tag of cleared) if (p.attributes[tag]) p.attributes[tag] = '';
  }
}
