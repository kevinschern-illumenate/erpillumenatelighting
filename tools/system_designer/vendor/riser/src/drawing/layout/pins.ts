import type { Project } from '../../schemas/project';
import type { LayoutNode } from './types';
import { enclosureGroups, ENCLOSURE_HEAD, ENCLOSURE_PAD } from './enclosures';
import { intersects, type Bounds } from './router';

/** Honor absolute pins, then shift colliding automatic groups within their own
 * column. A manual position must not silently turn another symbol into a wire obstacle. */
export function applyPins(
  nodes: LayoutNode[],
  positions: Map<string, Bounds>,
  project: Project,
  area: Bounds,
) {
  const pinned = nodes.filter((n) => project.layoutOverrides[n.id]?.pinned);
  for (const n of pinned) {
    const pin = project.layoutOverrides[n.id]!;
    positions.set(n.id, { ...positions.get(n.id)!, x: pin.x, y: pin.y });
  }
  if (!pinned.length) return;
  for (const group of enclosureGroups(nodes)) {
    if (group.some((n) => project.layoutOverrides[n.id]?.pinned)) continue;
    const ids = new Set(group.map((n) => n.id));
    const boxes = group.map((n) => positions.get(n.id)!);
    const pad = group[0]!.enclosure ? ENCLOSURE_PAD : 0;
    const head = group[0]!.enclosure ? ENCLOSURE_HEAD : 0;
    const x = Math.min(...boxes.map((b) => b.x)) - pad,
      y = Math.min(...boxes.map((b) => b.y)) - pad;
    const bounds = {
      x,
      y,
      width: Math.max(...boxes.map((b) => b.x + b.width)) + pad - x,
      height: Math.max(...boxes.map((b) => b.y + b.height)) + head - y,
    };
    if (!pinned.some((n) => intersects(bounds, positions.get(n.id)!, 0.45))) continue;
    const others = [...positions].filter(([id]) => !ids.has(id)).map(([, b]) => b);
    const vertical = project.settings.sheet.flow === 'TB';
    const offsets = others
      .flatMap((b) =>
        vertical
          ? [b.x - bounds.x - bounds.width - 0.8, b.x + b.width + 0.8 - bounds.x]
          : [b.y - bounds.y - bounds.height - 0.8, b.y + b.height + 0.8 - bounds.y],
      )
      .sort((a, b) => Math.abs(a) - Math.abs(b));
    for (const delta of offsets) {
      const candidate = {
        ...bounds,
        x: bounds.x + (vertical ? delta : 0),
        y: bounds.y + (vertical ? 0 : delta),
      };
      if (
        candidate.x < area.x ||
        candidate.y < area.y ||
        candidate.x + candidate.width > area.x + area.width ||
        candidate.y + candidate.height > area.y + area.height
      )
        continue;
      if (others.some((b) => intersects(candidate, b, 0.45))) continue;
      for (const n of group) {
        const b = positions.get(n.id)!;
        positions.set(n.id, {
          ...b,
          x: b.x + (vertical ? delta : 0),
          y: b.y + (vertical ? 0 : delta),
        });
      }
      break;
    }
  }
}
