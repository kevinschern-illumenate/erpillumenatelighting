import logoData from '../data/brand/illumenate-main.json';
import { ContourSchema, type Primitive, type Point, type Contour } from './model';

// Original supplied PDF outlines, retaining compound counters and cubic curves.
const paths = logoData.paths.map((p) => p.contours.map((c) => ContourSchema.parse(c)));
export function titleBlockLogo(region: {
  x: number;
  y: number;
  width: number;
  height: number;
}): Primitive[] {
  const { width, height, clearSpace } = logoData;
  // Include the documented 30-unit clear space and a paper margin on every side.
  const scale = Math.min(
    (region.width - 0.08) / (width + clearSpace * 2),
    (region.height - 0.12) / (height + clearSpace * 2),
    2.3 / width,
  );
  const x = region.x + (region.width - width * scale) / 2;
  const y = region.y + (region.height - height * scale) / 2;
  const at = (p: Point): Point => ({ x: x + p.x * scale, y: y + p.y * scale });
  return paths.map((contours) => ({
    kind: 'filledPath',
    layer: 'E-ANNO-TTLB',
    color: '#000000',
    contours: contours.map((c) => ({
      start: at(c.start),
      segments: c.segments.map((s) =>
        s.kind === 'line'
          ? { ...s, to: at(s.to) }
          : { ...s, control1: at(s.control1), control2: at(s.control2), to: at(s.to) },
      ),
    })),
  }));
}

/** Closed CAD hatch boundaries; subdivision error is <= 0.0001 paper inch. */
export function flattenContour(contour: Contour, tolerance = 0.0001): Point[] {
  const points: Point[] = [contour.start];
  const midpoint = (a: Point, b: Point): Point => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 });
  const distanceToSegment = (p: Point, a: Point, b: Point) => {
    const dx = b.x - a.x,
      dy = b.y - a.y;
    const t =
      dx || dy
        ? Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / (dx * dx + dy * dy)))
        : 0;
    return Math.hypot(p.x - a.x - t * dx, p.y - a.y - t * dy);
  };
  function cubic(a: Point, b: Point, c: Point, d: Point, depth = 0) {
    if (
      depth >= 20 ||
      Math.max(distanceToSegment(b, a, d), distanceToSegment(c, a, d)) <= tolerance
    ) {
      points.push(d);
      return;
    }
    const ab = midpoint(a, b),
      bc = midpoint(b, c),
      cd = midpoint(c, d);
    const abc = midpoint(ab, bc),
      bcd = midpoint(bc, cd),
      mid = midpoint(abc, bcd);
    cubic(a, ab, abc, mid, depth + 1);
    cubic(mid, bcd, cd, d, depth + 1);
  }
  for (const segment of contour.segments) {
    if (segment.kind === 'line') points.push(segment.to);
    else cubic(points.at(-1)!, segment.control1, segment.control2, segment.to);
  }
  const last = points.at(-1)!;
  if (Math.hypot(last.x - contour.start.x, last.y - contour.start.y) < 1e-8) points.pop();
  return points;
}
