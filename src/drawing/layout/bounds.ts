import type { Primitive } from '../model';
import { textBounds } from '../text';
import type { Bounds } from './router';

export function primitiveBounds(p: Primitive): Bounds {
  if (p.kind === 'text') return textBounds(p);
  if (p.kind === 'rect') return p;
  if (p.kind === 'circle' || p.kind === 'arc')
    return { x: p.x - p.radius, y: p.y - p.radius, width: p.radius * 2, height: p.radius * 2 };
  const points =
    p.kind === 'line'
      ? [p.from, p.to]
      : p.kind === 'filledPath'
        ? p.contours.flatMap((c) => [
            c.start,
            ...c.segments.flatMap((s) =>
              s.kind === 'line' ? [s.to] : [s.to, s.control1, s.control2],
            ),
          ])
        : p.points;
  const x = Math.min(...points.map((p) => p.x)),
    y = Math.min(...points.map((p) => p.y));
  return {
    x,
    y,
    width: Math.max(...points.map((p) => p.x)) - x,
    height: Math.max(...points.map((p) => p.y)) - y,
  };
}
