import type { RunResult } from '../../engine/model';
import { powerTypes } from '../../engine/wireSelect';
import { columnLayout } from './columns';
import type { LayoutNode, LayoutResult } from './types';

export const ENCLOSURE_PAD = 0.55;
export const ENCLOSURE_HEAD = 0.75;
export const unitId = (n: LayoutNode) => (n.enclosure ? 'enclosure:' + n.enclosure : n.id);

/** Named enclosures remain indivisible until the enclosure itself cannot fit. */
export function enclosureGroups(nodes: LayoutNode[]): LayoutNode[][] {
  const groups = new Map<string, LayoutNode[]>();
  for (const node of nodes) {
    const key = unitId(node);
    groups.set(key, [...(groups.get(key) ?? []), node]);
  }
  return [...groups.values()];
}

/** Rank the entire project once. Power-fed cabinets advance; DMX chains may
 * connect cabinets in the same column. AC feed-through retains the supply column. */
export function enclosureRanks(nodes: LayoutNode[], runs: RunResult[]): Map<string, number> {
  const groups = enclosureGroups(nodes);
  const unitOf = new Map(nodes.map((n) => [n.id, unitId(n)]));
  const feeds = runs
    .filter((r) => powerTypes.includes(r.type) && unitOf.has(r.from.id) && unitOf.has(r.to.id))
    .map((r) => ({
      from: unitOf.get(r.from.id)!,
      to: unitOf.get(r.to.id)!,
      through: r.from.port === 'AC-THRU',
    }))
    .filter((r) => r.from !== r.to);
  const ancestors = new Set(groups.filter((g) => g[0]!.enclosure).map((g) => unitId(g[0]!)));
  for (let i = 0; i < groups.length; i++) {
    let changed = false;
    for (const r of feeds)
      if (ancestors.has(r.to) && !ancestors.has(r.from)) {
        ancestors.add(r.from);
        changed = true;
      }
    if (!changed) break;
  }
  const ranks = new Map(
    groups.map((g) => {
      const n = g[0]!,
        id = unitId(n);
      return [
        id,
        n.enclosure ? 2 : n.partition === 0 ? 0 : ancestors.has(id) ? 1 : n.partition + 2,
      ] as const;
    }),
  );
  // Condense feedback between cabinets before ranking. Different circuits can
  // legitimately cross in both directions between the same two enclosures.
  const edges = new Map(groups.map((g) => [unitId(g[0]!), [] as string[]]));
  for (const r of feeds) edges.get(r.from)!.push(r.to);
  const index = new Map<string, number>(),
    low = new Map<string, number>(),
    active = new Set<string>(),
    stack: string[] = [],
    component = new Map<string, number>();
  let next = 0,
    count = 0;
  function visit(id: string) {
    index.set(id, next);
    low.set(id, next++);
    stack.push(id);
    active.add(id);
    for (const to of edges.get(id)!) {
      if (!index.has(to)) {
        visit(to);
        low.set(id, Math.min(low.get(id)!, low.get(to)!));
      } else if (active.has(to)) low.set(id, Math.min(low.get(id)!, index.get(to)!));
    }
    if (low.get(id) === index.get(id)) {
      let member: string;
      do {
        member = stack.pop()!;
        active.delete(member);
        component.set(member, count);
      } while (member !== id);
      count++;
    }
  }
  for (const id of edges.keys()) if (!index.has(id)) visit(id);
  function advance() {
    const levels = new Map<number, number>();
    for (const [id, rank] of ranks)
      levels.set(component.get(id)!, Math.max(levels.get(component.get(id)!) ?? 0, rank));
    for (let i = 0; i < count; i++) {
      let changed = false;
      for (const r of feeds) {
        const a = component.get(r.from)!,
          b = component.get(r.to)!;
        if (a === b) continue;
        const value = levels.get(a)! + (r.through ? 0 : 1);
        if (levels.get(b)! < value) {
          levels.set(b, value);
          changed = true;
        }
      }
      if (!changed) break;
    }
    for (const id of ranks.keys()) ranks.set(id, levels.get(component.get(id)!)!);
  }
  advance();
  const lastCabinet = Math.max(
    1,
    ...groups.filter((g) => g[0]!.enclosure).map((g) => ranks.get(unitId(g[0]!))!),
  );
  for (const g of groups) {
    const n = g[0]!;
    if (!n.enclosure && n.partition > 0 && !ancestors.has(n.id))
      ranks.set(n.id, Math.max(ranks.get(n.id)!, lastCabinet + n.partition));
  }
  advance();
  return ranks;
}

/** Cabinets occupy outer columns, with supply -> controls -> load columns inside.
 * Equipment is never placed in arbitrary spare space. */
export function enclosureLayout(
  nodes: LayoutNode[],
  runs: RunResult[],
  flow: 'LR' | 'TB',
  available: { width: number; height: number },
  ranks: Map<string, number>,
  extraGap = 0,
): LayoutResult {
  const inside = new Map<string, LayoutResult>();
  const unitOf = new Map(nodes.map((n) => [n.id, unitId(n)]));
  const units = enclosureGroups(nodes).map((members): LayoutNode => {
    const first = members[0]!,
      id = unitId(first);
    if (!first.enclosure) return { ...first, partition: ranks.get(id)! };
    const content = columnLayout(
      members,
      runs,
      flow,
      {
        width: available.width - ENCLOSURE_PAD * 2,
        height: available.height - ENCLOSURE_PAD - ENCLOSURE_HEAD,
      },
      1.05 + extraGap,
    );
    inside.set(id, content);
    return {
      ...first,
      id,
      terminal: false,
      tag: first.enclosure,
      partition: ranks.get(id)!,
      symbol: {
        ...first.symbol,
        widthIn: content.width + ENCLOSURE_PAD * 2,
        heightIn: content.height + ENCLOSURE_PAD + ENCLOSURE_HEAD,
      },
    };
  });
  const external = runs
    .map((r) => ({
      ...r,
      from: { ...r.from, id: unitOf.get(r.from.id) ?? r.from.id },
      to: { ...r.to, id: unitOf.get(r.to.id) ?? r.to.id },
    }))
    .filter((r) => r.from.id !== r.to.id);
  const outer = columnLayout(units, external, flow, available, 0.8 + extraGap);
  const expanded = new Map<string, { x: number; y: number; width: number; height: number }>();
  for (const [id, p] of outer.nodes) {
    const content = inside.get(id);
    if (!content) expanded.set(id, p);
    else
      for (const [member, b] of content.nodes)
        expanded.set(member, { ...b, x: p.x + ENCLOSURE_PAD + b.x, y: p.y + ENCLOSURE_PAD + b.y });
  }
  return { ...outer, nodes: expanded };
}
