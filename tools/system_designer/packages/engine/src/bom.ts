import type { Project } from '@ill/core-schemas/project';
import type { CatalogItem } from '@ill/core-schemas/catalog';
import type { WireType } from '@ill/core-schemas/wire';
import type { BomItem, RunResult, DmxSegment } from './model';
import { round } from './messages';

export function buildBom(
  project: Project,
  products: CatalogItem[],
  wires: WireType[],
  runs: RunResult[],
  segments: DmxSegment[],
): BomItem[] {
  const rows = new Map<string, BomItem>();
  for (const entity of [...project.equipment, ...project.loads]) {
    const item = products.find((p) => p.id === entity.catalogId);
    if (!item) continue;
    const isTape = item.specs.kind === 'tape';
    const qty =
      isTape && 'lengthFt' in entity
        ? (entity.lengthFt ?? 0) * (1 + project.settings.tapeLengthMarginPct / 100)
        : (entity.qty ?? 0);
    const key = `product:${item.sku}`;
    const current = rows.get(key);
    rows.set(key, {
      key,
      sku: item.sku,
      description: item.model,
      quantity: (current?.quantity ?? 0) + qty,
      unit: isTape ? 'ft' : 'ea',
      isExample: item.isExample,
    });
  }
  for (const row of rows.values()) {
    const item = products.find((p) => p.sku === row.sku);
    if (item?.specs.kind === 'tape' && item.specs.reelLengthFt)
      row.reels = Math.ceil(row.quantity / item.specs.reelLengthFt);
  }
  for (const run of runs) {
    const wire = wires.find((w) => w.id === run.wireTypeId);
    if (!wire || run.type === 'wireless') continue;
    const conductors =
      wire.category === 'building-wire' ? wire.conductors.reduce((sum, c) => sum + c.count, 0) : 1;
    const quantity =
      run.lengthFt * run.parallelSets * conductors * (1 + project.settings.wireWastePct / 100);
    const key = `wire:${wire.id}`;
    const previous = rows.get(key);
    rows.set(key, {
      key,
      sku: wire.id,
      description: `${wire.riserLabel}${conductors > 1 ? ' (individual conductor feet)' : ''}`,
      quantity: (previous?.quantity ?? 0) + quantity,
      unit: 'ft',
      isExample: wire.isExample,
    });
  }
  const terminators = segments.reduce((sum, s) => sum + s.ends.length, 0);
  if (terminators)
    rows.set('accessory:terminator', {
      key: 'accessory:terminator',
      sku: 'VERIFY-DMX-TERMINATOR',
      description: 'DMX end-of-segment terminator — verify equipment requirements',
      quantity: terminators,
      unit: 'ea',
      isExample: true,
    });
  return [...rows.values()]
    .map((r) => ({ ...r, quantity: round(r.quantity) }))
    .sort((a, b) => a.key.localeCompare(b.key));
}
