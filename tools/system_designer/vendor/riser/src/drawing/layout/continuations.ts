import { text, type Point, type TextPrim } from '../model';
import { paragraph, textWidth } from '../text';
import { intersects, segmentBlocked, type Bounds, type Segment } from './router';
import type { RunResult } from '../../engine/model';
import { powerTypes } from '../../engine/wireSelect';

export const controlName = (run: RunResult): string =>
  run.protocol ??
  (
    {
      dmx: 'DMX512',
      ethernet: 'ETHERNET',
      '0-10v': '0-10V',
      dali: 'DALI-2',
      'spi-data': 'SPI',
      'lutron-qs': 'Lutron-QS',
      'lutron-ecosystem': 'Lutron-EcoSystem',
      wireless: 'WIRELESS',
    } as Record<string, string>
  )[run.type] ??
  run.type;
export const continuationLabelWidth = (run: RunResult) =>
  powerTypes.includes(run.type) ? 0.97 : 1.6;
export function continuationLabel(
  run: RunResult,
  outgoing: boolean,
  runs: RunResult[],
  heading: string,
) {
  if (powerTypes.includes(run.type))
    return `${heading}\n${outgoing && runs.length > 1 ? `${runs.length} CABLES` : run.tag}`;
  const remote = outgoing ? run.to : run.from;
  return `${heading}\n${controlName(run)} · ${run.tag}\n${remote.tag}${remote.port ? ` / ${remote.port}` : ''}`;
}

export type ContinuationMarker = {
  center: Point;
  radius: number;
  bounds: Bounds;
  label: TextPrim;
  reference: TextPrim;
  point: Point;
  stub: Point;
};

export function sheetReferences(indices: number[], prefix: string): string {
  const sorted = [...new Set(indices)].sort((a, b) => a - b);
  const groups: string[] = [];
  for (let i = 0; i < sorted.length; i++) {
    const first = sorted[i]!;
    let last = first;
    while (sorted[i + 1] === last + 1) last = sorted[++i]!;
    groups.push(
      first === last ? `${prefix}${first + 1}` : `${prefix}${first + 1}–${prefix}${last + 1}`,
    );
  }
  return groups.join(', ');
}

/** Allocate the whole bubble + sheet-reference label before any cable is routed. */
export function placeContinuation(
  reference: string,
  label: string,
  local: Point,
  side: 'W' | 'E',
  area: Bounds,
  obstacles: Bounds[],
  reservedLeads: Segment[],
  inline = false,
  labelWidth = 0.97,
): ContinuationMarker {
  const radius = Math.max(0.18, (textWidth(reference, 3 / 32, 'bold') + 0.12) / 2);
  const width = Math.max(labelWidth + 0.08, radius * 2 + 0.1);
  const sample = paragraph(label, 0, 0, width - 0.08);
  const labelHeight = sample.value.split('\n').length * sample.heightIn * 1.45;
  const height = inline
    ? Math.max(radius * 2 + 0.1, labelHeight + 0.1)
    : radius * 2 + 0.2 + labelHeight;
  const direction = side === 'W' ? -1 : 1;
  const desiredX = local.x + direction * (inline ? 1.3 : width / 2 + 0.5);
  const candidates: Point[] = [];
  // Prefer a nearby gutter, then search clear paper. All positions are measured
  // in plotted inches, so reference type and circle size remain readable.
  for (const dx of [0, 0.5, 1, 1.5])
    for (const dy of [0, -0.8, 0.8, -1.6, 1.6, -2.4, 2.4])
      candidates.push({ x: desiredX + direction * dx, y: local.y + dy });
  for (let x = area.x + width / 2 + 0.1; x <= area.x + area.width - width / 2 - 0.1; x += 0.5)
    for (let y = area.y + radius + 0.1; y <= area.y + area.height - height; y += 0.4)
      candidates.push({ x, y });
  candidates.sort(
    (a, b) =>
      Math.abs(a.x - desiredX) +
      Math.abs(a.y - local.y) * 1.4 -
      (Math.abs(b.x - desiredX) + Math.abs(b.y - local.y) * 1.4),
  );
  for (const center of candidates) {
    const totalWidth = inline ? radius * 2 + 0.2 + width : width;
    const bounds = inline
      ? {
          x: side === 'E' ? center.x - radius - 0.05 : center.x + radius + 0.05 - totalWidth,
          y: center.y - height / 2,
          width: totalWidth,
          height,
        }
      : { x: center.x - width / 2, y: center.y - radius - 0.06, width, height };
    const point = { x: center.x - direction * radius, y: center.y };
    const stub = {
      x: center.x - direction * (inline ? radius + 0.22 : width / 2 + 0.14),
      y: center.y,
    };
    if (
      bounds.x < area.x + 0.06 ||
      bounds.y < area.y + 0.06 ||
      bounds.x + bounds.width > area.x + area.width - 0.06 ||
      bounds.y + height > area.y + area.height - 0.06 ||
      stub.x < area.x + 0.12 ||
      stub.x > area.x + area.width - 0.12 ||
      obstacles.some((b) => intersects(bounds, b, inline ? 0.07 : 0.1)) ||
      segmentBlocked(point, stub, obstacles) ||
      reservedLeads.some((s) => segmentBlocked(s.a, s.b, [bounds]))
    )
      continue;
    return {
      center,
      radius,
      bounds,
      point,
      stub,
      label: {
        ...sample,
        x: inline ? center.x + direction * (radius + 0.15) : center.x,
        y: inline
          ? center.y + (labelHeight - sample.heightIn * 1.45) / 2 - 0.02
          : center.y + radius + 0.12 + labelHeight - sample.heightIn * 1.45,
        hAlign: inline ? (side === 'E' ? 'left' : 'right') : 'center',
        role: 'continuation-label',
      },
      reference: {
        ...text(reference, center.x, center.y - 3 / 64, 3 / 32, 'E-ANNO-TAGS', 'bold'),
        hAlign: 'center',
        role: 'continuation',
      },
    };
  }
  throw new Error(
    `No clear space for continuation ${reference}. Move a pinned device or use a larger sheet.`,
  );
}
