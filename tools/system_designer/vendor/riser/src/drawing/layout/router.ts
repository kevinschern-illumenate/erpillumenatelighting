import type { Point } from '../model';

export type Bounds = { x: number; y: number; width: number; height: number };
export type Segment = { a: Point; b: Point };
export const ENCLOSURE_WIRE_CLEARANCE = 0.2;
export const segmentsOf = (points: Point[]): Segment[] =>
  points.slice(1).map((b, i) => ({ a: points[i]!, b }));
export function simplifyRoute(points: Point[]): Point[] {
  const out: Point[] = [];
  for (const p of points) {
    const last = out.at(-1),
      prev = out.at(-2);
    if (last && Math.abs(last.x - p.x) + Math.abs(last.y - p.y) < 1e-6) continue;
    if (
      last &&
      prev &&
      ((Math.abs(prev.x - last.x) < 1e-6 && Math.abs(last.x - p.x) < 1e-6) ||
        (Math.abs(prev.y - last.y) < 1e-6 && Math.abs(last.y - p.y) < 1e-6))
    )
      out.pop();
    out.push(p);
  }
  return out;
}
const between = (v: number, a: number, b: number, margin = 0) =>
  v > Math.min(a, b) + margin && v < Math.max(a, b) - margin;
export function crossing(a: Segment, b: Segment): Point | undefined {
  const ah = Math.abs(a.a.y - a.b.y) < 1e-6,
    bh = Math.abs(b.a.y - b.b.y) < 1e-6;
  if (ah === bh) return;
  const h = ah ? a : b,
    v = ah ? b : a;
  if (between(v.a.x, h.a.x, h.b.x) && between(h.a.y, v.a.y, v.b.y)) return { x: v.a.x, y: h.a.y };
}
/** Independent cables may cross, but may never share a lane or nearly touch. */
export function parallelConflict(a: Segment, b: Segment, clearance = 0.125): boolean {
  const ah = Math.abs(a.a.y - a.b.y) < 1e-6,
    bh = Math.abs(b.a.y - b.b.y) < 1e-6;
  if (ah !== bh) return false;
  const separation = ah ? Math.abs(a.a.y - b.a.y) : Math.abs(a.a.x - b.a.x);
  const overlap = ah
    ? Math.min(Math.max(a.a.x, a.b.x), Math.max(b.a.x, b.b.x)) -
      Math.max(Math.min(a.a.x, a.b.x), Math.min(b.a.x, b.b.x))
    : Math.min(Math.max(a.a.y, a.b.y), Math.max(b.a.y, b.b.y)) -
      Math.max(Math.min(a.a.y, a.b.y), Math.min(b.a.y, b.b.y));
  return separation < clearance - 1e-6 && overlap > 1e-6;
}
export const intersects = (a: Bounds, b: Bounds, pad = 0) =>
  a.x < b.x + b.width + pad &&
  a.x + a.width + pad > b.x &&
  a.y < b.y + b.height + pad &&
  a.y + a.height + pad > b.y;
export function segmentBlocked(a: Point, b: Point, obstacles: Bounds[]): boolean {
  return obstacles.some((r) => {
    const inset = 0.001;
    return Math.abs(a.x - b.x) < 1e-6
      ? a.x > r.x + inset &&
          a.x < r.x + r.width - inset &&
          Math.max(a.y, b.y) > r.y + inset &&
          Math.min(a.y, b.y) < r.y + r.height - inset
      : Math.abs(a.y - b.y) < 1e-6
        ? a.y > r.y + inset &&
          a.y < r.y + r.height - inset &&
          Math.max(a.x, b.x) > r.x + inset &&
          Math.min(a.x, b.x) < r.x + r.width - inset
        : true;
  });
}
export function routeOrthogonal(
  start: Point,
  end: Point,
  obstacles: Bounds[],
  area: Bounds,
  occupied: Segment[] = [],
  guides: Segment[] = [],
): Point[] {
  const cost = (a: Point, b: Point) => {
    if (segmentBlocked(a, b, obstacles)) return Infinity;
    const s = { a, b };
    if (occupied.some((o) => parallelConflict(s, o))) return Infinity;
    // Crossing an enclosure boundary is allowed; tracking its dashed outline is not.
    if (guides.some((o) => parallelConflict(s, o, ENCLOSURE_WIRE_CLEARANCE))) return Infinity;
    const length = Math.abs(a.x - b.x) + Math.abs(a.y - b.y);
    return length + occupied.filter((o) => crossing(s, o)).length * 6;
  };
  const valid = (points: Point[]) =>
    points.slice(1).every((p, i) => Number.isFinite(cost(points[i]!, p)));
  // Most continuation leads are short and aligned; avoid building the full
  // visibility grid when the direct lane is already clear and uncrossed.
  if (
    (Math.abs(start.x - end.x) < 1e-6 || Math.abs(start.y - end.y) < 1e-6) &&
    valid([start, end]) &&
    !occupied.some((s) => crossing({ a: start, b: end }, s))
  )
    return [start, end];
  const xs = [
    (start.x + end.x) / 2,
    start.x + 0.25,
    end.x - 0.25,
    area.x,
    area.x + area.width,
    ...obstacles.flatMap((r) => [r.x - 0.125, r.x + r.width + 0.125]),
    ...occupied.flatMap((s) => [s.a.x - 0.18, s.a.x + 0.18, s.b.x - 0.18, s.b.x + 0.18]),
    ...guides.flatMap((s) => [s.a.x - 0.22, s.a.x + 0.22, s.b.x - 0.22, s.b.x + 0.22]),
  ].filter((x) => x >= area.x && x <= area.x + area.width);
  const candidates: Point[][] = [];
  for (const x of xs) {
    const p = [start, { x, y: start.y }, { x, y: end.y }, end];
    if (valid(p)) candidates.push(simplifyRoute(p));
  }
  const ys = [
    (start.y + end.y) / 2,
    area.y,
    area.y + area.height,
    ...obstacles.flatMap((r) => [r.y - 0.125, r.y + r.height + 0.125]),
    ...occupied.flatMap((s) => [s.a.y - 0.18, s.a.y + 0.18, s.b.y - 0.18, s.b.y + 0.18]),
    ...guides.flatMap((s) => [s.a.y - 0.22, s.a.y + 0.22, s.b.y - 0.22, s.b.y + 0.22]),
  ].filter((y) => y >= area.y && y <= area.y + area.height);
  for (const y of ys) {
    const p = [start, { x: start.x, y }, { x: end.x, y }, end];
    if (valid(p)) candidates.push(simplifyRoute(p));
  }
  if (candidates.length) {
    const score = (p: Point[]) =>
      segmentsOf(p).reduce((sum, s) => sum + cost(s.a, s.b), 0) + p.length * 0.3;
    candidates.sort((a, b) => score(a) - score(b));
    return candidates[0]!;
  }
  // A visibility grid is used only for difficult reroutes after pinning.
  const xValues = [...new Set([start.x, end.x, ...xs].map((v) => Math.round(v * 1e6) / 1e6))].sort(
    (a, b) => a - b,
  );
  const yValues = [...new Set([start.y, end.y, ...ys].map((v) => Math.round(v * 1e6) / 1e6))].sort(
    (a, b) => a - b,
  );
  const id = (x: number, y: number) => y * xValues.length + x;
  const startX = xValues.findIndex((x) => Math.abs(x - start.x) < 1e-6),
    startY = yValues.findIndex((y) => Math.abs(y - start.y) < 1e-6),
    endX = xValues.findIndex((x) => Math.abs(x - end.x) < 1e-6),
    endY = yValues.findIndex((y) => Math.abs(y - end.y) < 1e-6);
  const open = [id(startX, startY)];
  const distance = new Map<number, number>([[open[0]!, 0]]);
  const previous = new Map<number, number>();
  const closed = new Set<number>();
  const point = (index: number) => ({
    x: xValues[index % xValues.length]!,
    y: yValues[Math.floor(index / xValues.length)]!,
  });
  const endId = id(endX, endY);
  while (open.length) {
    open.sort(
      (a, b) =>
        distance.get(a)! +
        Math.abs(point(a).x - end.x) +
        Math.abs(point(a).y - end.y) -
        (distance.get(b)! + Math.abs(point(b).x - end.x) + Math.abs(point(b).y - end.y)),
    );
    const current = open.shift()!;
    if (current === endId) {
      const route = [end];
      let cursor = current;
      while (previous.has(cursor)) {
        cursor = previous.get(cursor)!;
        route.unshift(point(cursor));
      }
      return simplifyRoute(route);
    }
    if (closed.has(current)) continue;
    closed.add(current);
    const x = current % xValues.length,
      y = Math.floor(current / xValues.length);
    const from = point(current);
    for (const [nx, ny] of [
      [x - 1, y],
      [x + 1, y],
      [x, y - 1],
      [x, y + 1],
    ]) {
      if (nx! < 0 || ny! < 0 || nx! >= xValues.length || ny! >= yValues.length) continue;
      const next = id(nx!, ny!);
      const to = point(next);
      if (closed.has(next)) continue;
      const segmentCost = cost(from, to);
      if (!Number.isFinite(segmentCost)) continue;
      const prev = previous.has(current) ? point(previous.get(current)!) : undefined;
      const turn =
        prev && Math.abs(prev.x - from.x) < 1e-6 !== Math.abs(from.x - to.x) < 1e-6 ? 0.3 : 0;
      const d = distance.get(current)! + segmentCost + turn;
      if (d < (distance.get(next) ?? Infinity)) {
        distance.set(next, d);
        previous.set(next, current);
        open.push(next);
      }
    }
  }
  throw new Error(
    'Pinned positions leave no clear orthogonal route. Move a node or reset the layout.',
  );
}
