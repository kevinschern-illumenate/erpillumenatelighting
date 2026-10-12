import type { RunResult } from '../../engine/model';
import { powerTypes } from '../../engine/wireSelect';
import type { LayoutNode, LayoutResult } from './types';

export const ROW_GAP = 0.8;
export const STAGE_GAP = 1.8;
const compare = new Intl.Collator(undefined, { numeric: true }).compare;

/** Invisible functional columns. Rows pack independently, then align to their
 * neighbors: a large load fanout never reserves empty rows in every column. */
export function columnLayout(
  nodes: LayoutNode[],
  runs: RunResult[],
  flow: 'LR' | 'TB',
  available?: { width: number; height: number },
  minimumRowGap = 0,
): LayoutResult {
  if (!nodes.length) return { width: 0, height: 0, nodes: new Map() };
  const vertical = flow === 'TB';
  const acrossSize = (n: LayoutNode) => (vertical ? n.symbol.widthIn : n.symbol.heightIn);
  const alongSize = (n: LayoutNode) => (vertical ? n.symbol.heightIn : n.symbol.widthIn);
  const gap = Math.max(vertical ? 1.05 : ROW_GAP, minimumRowGap);
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const local = runs.filter((r) => byId.has(r.from.id) && byId.has(r.to.id));
  const stages = [...new Set(nodes.map((n) => n.partition))].sort((a, b) => a - b);
  const order = new Map<string, string>();
  const controlOrder = new Map<string, number>();
  function controlDepth(id: string, seen = new Set<string>()): number {
    if (controlOrder.has(id)) return controlOrder.get(id)!;
    if (seen.has(id)) return 0;
    seen.add(id);
    const inputs = local.filter((r) => r.to.id === id && !powerTypes.includes(r.type));
    const value = Math.max(0, ...inputs.map((r) => 1 + controlDepth(r.from.id, new Set(seen))));
    controlOrder.set(id, value);
    return value;
  }
  function path(n: LayoutNode, seen = new Set<string>()): string {
    if (order.has(n.id)) return order.get(n.id)!;
    if (seen.has(n.id)) return n.tag;
    seen.add(n.id);
    const feed = local.find((r) => r.to.id === n.id && powerTypes.includes(r.type));
    const upstream = feed && feed.from.port !== 'AC-THRU' && byId.get(feed.from.id);
    const key =
      (upstream ? path(upstream, seen) + '/' + (feed?.from.port ?? '') : n.circuit) +
      '/' +
      n.tag +
      '/' +
      n.id;
    order.set(n.id, key);
    return key;
  }
  const columns: LayoutNode[][] = [];
  for (const stage of stages) {
    const members = nodes
      .filter((n) => n.partition === stage)
      .sort(
        (a, b) =>
          (a.control && b.control ? controlDepth(a.id) - controlDepth(b.id) : 0) ||
          compare(path(a), path(b)),
      );
    // Only parallel terminal banks may wrap. Supplies and controls keep their
    // functional column, including on continuation sheets.
    const room = available && (vertical ? available.width : available.height);
    const canWrap =
      members.every((m) => m.terminal) &&
      !local.some((r) => members.some((m) => m.id === r.to.id) && powerTypes.includes(r.type));
    let column: LayoutNode[] = [],
      used = 0;
    for (const n of members) {
      if (
        room &&
        stage === stages.at(-1) &&
        canWrap &&
        column.length &&
        used + gap + acrossSize(n) > room
      ) {
        columns.push(column);
        column = [];
        used = 0;
      }
      used += (column.length ? gap : 0) + acrossSize(n);
      column.push(n);
    }
    if (column.length) columns.push(column);
  }
  const stackSize = (col: LayoutNode[]) =>
    col.reduce((s, n) => s + acrossSize(n), 0) + (col.length - 1) * gap;
  const cross = Math.max(...columns.map(stackSize));
  const centers = new Map<string, number>();
  const columnOf = new Map(columns.flatMap((col, i) => col.map((n) => [n.id, i] as const)));
  for (const col of columns) {
    let cursor = 0;
    for (const n of col) {
      centers.set(n.id, cursor + acrossSize(n) / 2);
      cursor += acrossSize(n) + gap;
    }
  }
  // Stable row order, alternating neighbor alignment, hard minimum clearances.
  for (const reverse of [true, false, true]) {
    for (const col of reverse ? [...columns].reverse() : columns) {
      const targets = col.map((n) => {
        const neighbors = local.flatMap((r) => {
          const other = r.from.id === n.id ? r.to.id : r.to.id === n.id ? r.from.id : undefined;
          if (!other || columnOf.get(other) === columnOf.get(n.id)) return [];
          return [{ center: centers.get(other)!, weight: powerTypes.includes(r.type) ? 3 : 1 }];
        });
        return neighbors.length
          ? neighbors.reduce((s, v) => s + v.center * v.weight, 0) /
              neighbors.reduce((s, v) => s + v.weight, 0)
          : centers.get(n.id)!;
      });
      let cursor = 0;
      const starts = col.map((n, i) => {
        const start = Math.max(cursor, targets[i]! - acrossSize(n) / 2);
        cursor = start + acrossSize(n) + gap;
        return start;
      });
      cursor = cross;
      for (let i = col.length - 1; i >= 0; i--) {
        const n = col[i]!;
        starts[i] = Math.min(starts[i]!, cursor - acrossSize(n));
        cursor = starts[i]! - gap;
      }
      col.forEach((n, i) => centers.set(n.id, starts[i]! + acrossSize(n) / 2));
    }
  }
  const positions = new Map<string, { x: number; y: number; width: number; height: number }>();
  let along = 0;
  for (const col of columns) {
    const size = Math.max(...col.map(alongSize));
    for (const n of col)
      positions.set(n.id, {
        x: vertical ? centers.get(n.id)! - acrossSize(n) / 2 : along,
        y: vertical ? along : cross - centers.get(n.id)! - acrossSize(n) / 2,
        width: n.symbol.widthIn,
        height: n.symbol.heightIn,
      });
    const ports = Math.max(
      0,
      ...col.map(
        (n) =>
          new Set(runs.filter((r) => r.from.id === n.id).map((r) => r.from.port + ':' + r.type))
            .size,
      ),
    );
    along += size + Math.max(STAGE_GAP, Math.min(3.2, 0.9 + ports * 0.2));
  }
  const extent = Math.max(
    ...columns.at(-1)!.map((n) => positions.get(n.id)![vertical ? 'y' : 'x'] + alongSize(n)),
  );
  if (vertical) for (const p of positions.values()) p.y = extent - p.y - p.height;
  return { width: vertical ? cross : extent, height: vertical ? extent : cross, nodes: positions };
}
