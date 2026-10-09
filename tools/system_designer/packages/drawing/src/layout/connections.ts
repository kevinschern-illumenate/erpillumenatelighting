import type { Project } from '@ill/core-schemas/project';
import type { LibrarySnapshot } from '@ill/core-schemas/library';
import type { EngineResult, RunResult } from '@ill/engine/model';
import { powerTypes } from '@ill/engine/wireSelect';
import { text, type Point, type Sheet, type TextPrim, type LayerName } from '../model';
import { paragraph, textBounds, textWidth } from '../text';
import {
  placeContinuation,
  sheetReferences,
  controlName,
  continuationLabel,
  continuationLabelWidth,
  type ContinuationMarker,
} from './continuations';
import {
  crossing,
  intersects,
  routeOrthogonal,
  segmentsOf,
  simplifyRoute,
  segmentBlocked,
  parallelConflict,
  ENCLOSURE_WIRE_CLEARANCE,
  type Bounds,
  type Segment,
} from './router';
import { WIRE_COLORS, wireFamily } from '../client';
import { clientWireLabels, riserWireLabel } from '../wires';

/** How cables are drawn: the client diagram colours them and uses plain callouts. */
export interface WireStyle {
  client: boolean;
  /** The runs each drawn line stands for (parallel low-voltage runs share one line). */
  members: Map<string, RunResult[]>;
}

export type Continuation = { ref: string; runs: RunResult[] };
type Side = 'W' | 'E' | 'N' | 'S';
type Terminal = {
  point: Point;
  stub: Point;
  side: Side;
  name: string;
  escape?: Point;
  marker?: ContinuationMarker;
  inlineMarker?: boolean;
};
type Cable = {
  run: RunResult;
  fromLocal: boolean;
  toLocal: boolean;
  continuation?: Continuation;
  start: Terminal;
  end: Terminal;
  points: Point[];
  layer: LayerName;
};
const outward = (p: Point, side: Side, length: number): Point => ({
  x: p.x + (side === 'E' ? length : side === 'W' ? -length : 0),
  y: p.y + (side === 'N' ? length : side === 'S' ? -length : 0),
});

export function drawConnections(
  sheet: Sheet,
  project: Project,
  library: LibrarySnapshot,
  result: EngineResult,
  positions: Map<string, Bounds>,
  area: Bounds,
  pageOf: Map<string, number>,
  continuationFor: Map<string, Continuation>,
  layerForRun: (run: RunResult) => LayerName,
  denseMarkersFirst = false,
  wires: WireStyle = { client: false, members: new Map() },
) {
  /** Colour and weight of a client cable; the riser keeps its layer's. */
  const paint = (run: RunResult) =>
    wires.client
      ? {
          color: WIRE_COLORS[wireFamily(run)].color,
          lineweightMm: powerTypes.includes(run.type) ? 0.5 : 0.35,
        }
      : {};
  const vertical = project.settings.sheet.flow === 'TB';
  const runs = result.runs.filter(
    (r) =>
      (positions.has(r.from.id) || positions.has(r.to.id)) &&
      !(
        positions.has(r.from.id) &&
        !positions.has(r.to.id) &&
        continuationFor.get(r.runId)?.runs[0]?.runId !== r.runId
      ),
  );
  const ends = new Map<
    string,
    { run: RunResult; which: 'from' | 'to'; side: Side; name: string; other: number }[]
  >();
  for (const run of runs) {
    const power = powerTypes.includes(run.type);
    for (const which of ['from', 'to'] as const) {
      const p = positions.get(run[which].id);
      if (!p) continue;
      const other = positions.get(run[which === 'from' ? 'to' : 'from'].id);
      const feedThrough = run.from.port === 'AC-THRU';
      let side: Side = power
        ? vertical
          ? which === 'from'
            ? 'S'
            : 'N'
          : which === 'from'
            ? 'E'
            : 'W'
        : vertical
          ? which === 'from'
            ? 'E'
            : 'W'
          : which === 'from'
            ? 'S'
            : 'N';
      if (feedThrough)
        side = vertical ? (which === 'from' ? 'E' : 'W') : which === 'from' ? 'S' : 'N';
      if (feedThrough && other)
        side = vertical ? (other.x >= p.x ? 'E' : 'W') : other.y >= p.y ? 'N' : 'S';
      if (other) {
        // Follow the functional columns. A same-column daisy chain uses the
        // facing top/bottom terminals; inter-column cables use facing sides.
        side = vertical
          ? other.y + other.height < p.y - 0.1
            ? 'S'
            : other.y > p.y + p.height + 0.1
              ? 'N'
              : other.x >= p.x
                ? 'E'
                : 'W'
          : other.x > p.x + p.width + 0.1
            ? 'E'
            : other.x + other.width < p.x - 0.1
              ? 'W'
              : other.y >= p.y
                ? 'N'
                : 'S';
      }
      if (!other) {
        // Small signal chains enter above and leave below the symbol. Large
        // remote banks use the tall side so their individual references fit.
        const bank = runs.filter(
          (r) =>
            r[which].id === run[which].id &&
            !positions.has(r[which === 'from' ? 'to' : 'from'].id) &&
            !powerTypes.includes(r.type),
        ).length;
        side =
          !power && !vertical && bank <= 2
            ? which === 'from'
              ? 'S'
              : 'N'
            : which === 'from'
              ? 'E'
              : 'W';
      }
      if (!other && power && !vertical && which === 'from') {
        // An interior PSU exits below the cabinet rather than threading its
        // off-sheet feeder through the neighboring controls' terminal bank.
        const cabinet = sheet.prims.find(
          (b) =>
            b.kind === 'rect' &&
            b.layer === 'E-ANNO-ENCL' &&
            p.x > b.x &&
            p.y > b.y &&
            p.x + p.width < b.x + b.width &&
            p.y + p.height < b.y + b.height,
        );
        if (cabinet?.kind === 'rect' && p.x + p.width < cabinet.x + cabinet.width - 0.56)
          side = 'S';
      }
      const name =
        run[which].port ??
        (power
          ? (run.type.startsWith('lv-') || run.type === 'landscape-ac' ? 'AC' : 'DC') +
            (which === 'from' ? ' OUT' : ' IN')
          : run.type.toUpperCase() + (which === 'from' ? ' OUT' : ' IN'));
      const key = `${run[which].id}:${side}`;
      ends.set(key, [
        ...(ends.get(key) ?? []),
        {
          run,
          which,
          side,
          name,
          other: other ? (side === 'N' || side === 'S' ? other.x : -other.y) : 1e3,
        },
      ]);
    }
  }
  const terminals = new Map<string, Terminal>();
  for (const list of ends.values()) {
    list.sort(
      (a, b) =>
        a.other - b.other ||
        a.name.localeCompare(b.name, undefined, { numeric: true }) ||
        a.run.tag.localeCompare(b.run.tag, undefined, { numeric: true }),
    );
    const offSheetCount = list.filter(
      (end) => !positions.has(end.run[end.which === 'from' ? 'to' : 'from'].id),
    ).length;
    list.forEach((end, i) => {
      const p = positions.get(end.run[end.which].id)!;
      const horizontal = end.side === 'W' || end.side === 'E';
      const extent = horizontal ? p.height : p.width;
      const step = Math.min(
        offSheetCount >= 3 ? 0.56 : 0.32,
        (extent - 0.3) / Math.max(1, list.length - 1),
      );
      const offset = extent / 2 + (i - (list.length - 1) / 2) * step * (horizontal ? -1 : 1);
      const point = {
        x: p.x + (end.side === 'W' ? 0 : end.side === 'E' ? p.width : offset),
        y: p.y + (end.side === 'S' ? 0 : end.side === 'N' ? p.height : offset),
      };
      terminals.set(`${end.run.runId}:${end.which}`, {
        point,
        side: end.side,
        stub: outward(point, end.side, 0.34),
        escape: outward(point, end.side, Math.max(0.34, (list.length - 1) * 0.2)),
        name: end.name,
        inlineMarker: offSheetCount >= 3,
      });
    });
  }
  const markerBounds: Bounds[] = [];
  const markerLeads: Segment[] = [];
  const enclosureBounds = sheet.prims.flatMap((p): Bounds[] =>
    p.kind === 'rect' && p.layer === 'E-ANNO-ENCL' ? [p] : [],
  );
  const enclosureEdges = sheet.prims.flatMap((p): Segment[] =>
    p.kind === 'rect' && p.layer === 'E-ANNO-ENCL'
      ? segmentsOf([
          { x: p.x, y: p.y },
          { x: p.x + p.width, y: p.y },
          { x: p.x + p.width, y: p.y + p.height },
          { x: p.x, y: p.y + p.height },
          { x: p.x, y: p.y },
        ])
      : [],
  );
  const existingText = sheet.prims.filter((p): p is TextPrim => p.kind === 'text').map(textBounds);
  const enclosureText = sheet.prims
    .filter((p): p is TextPrim => p.kind === 'text' && p.layer === 'E-ANNO-ENCL')
    .map((p) => {
      const b = textBounds(p);
      return { x: b.x - 0.08, y: b.y - 0.08, width: b.width + 0.16, height: b.height + 0.16 };
    });
  const equipmentObstacles = [...positions.values()].map((p) => ({
    x: p.x - 0.12,
    y: p.y - 0.12,
    width: p.width + 0.24,
    height: p.height + 0.24,
  }));
  // Allocate references in terminal order. A retry can reserve dense output
  // banks first, so long signal callouts do not consume their straight lanes.
  const orderedRuns = [...runs].sort((a, b) => {
    const local = (r: RunResult) =>
      terminals.get(`${r.runId}:${positions.has(r.from.id) ? 'from' : 'to'}`)!;
    const aa = local(a),
      bb = local(b);
    return (
      (denseMarkersFirst ? Number(!!bb.inlineMarker) - Number(!!aa.inlineMarker) : 0) ||
      aa.point.x - bb.point.x ||
      bb.point.y - aa.point.y ||
      a.tag.localeCompare(b.tag)
    );
  });
  const cables: Cable[] = orderedRuns.map((run) => {
    const fromLocal = positions.has(run.from.id),
      toLocal = positions.has(run.to.id);
    let start = terminals.get(`${run.runId}:from`),
      end = terminals.get(`${run.runId}:to`);
    if (!start || !end) {
      const local = (start ?? end)!;
      const continuation = continuationFor.get(run.runId);
      const pages = (fromLocal ? (continuation?.runs ?? [run]) : [run]).map(
        (r) => pageOf.get(fromLocal ? r.to.id : r.from.id) ?? 0,
      );
      const marker = placeContinuation(
        continuation?.ref ?? run.tag,
        continuationLabel(
          run,
          fromLocal,
          continuation?.runs ?? [run],
          `${fromLocal ? 'TO' : 'FROM'} ${sheetReferences(pages, project.meta.sheetPrefix)}`,
        ),
        local.point,
        fromLocal ? 'E' : 'W',
        area,
        [...equipmentObstacles, ...enclosureBounds, ...existingText, ...markerBounds],
        [...terminals.values()]
          .map((t) => ({ a: t.point, b: t === local ? t.stub : (t.escape ?? t.stub) }))
          .concat(markerLeads, enclosureEdges),
        local.inlineMarker,
        continuationLabelWidth(run),
      );
      markerBounds.push(marker.bounds);
      markerLeads.push({ a: marker.point, b: marker.stub });
      const terminal = {
        point: marker.point,
        stub: marker.stub,
        side: local.side,
        name: '',
        marker,
      };
      if (!start) start = terminal;
      else end = terminal;
    }
    return {
      run,
      fromLocal,
      toLocal,
      continuation: continuationFor.get(run.runId),
      start: start!,
      end: end!,
      points: [],
      layer: layerForRun(run),
    };
  });
  // Short local connections reserve their lanes first. Long branches must route around them.
  cables.sort(
    (a, b) =>
      Math.abs(a.start.point.x - a.end.point.x) +
        Math.abs(a.start.point.y - a.end.point.y) -
        (Math.abs(b.start.point.x - b.end.point.x) + Math.abs(b.start.point.y - b.end.point.y)) ||
      a.run.tag.localeCompare(b.run.tag),
  );
  const occupied: Segment[] = [];
  const obstacles = [...equipmentObstacles, ...markerBounds, ...enclosureText];
  const routeArea = {
    x: area.x + 0.12,
    y: area.y + 0.12,
    width: area.width - 0.24,
    height: area.height - 0.24,
  };
  for (const cable of cables) {
    const otherLeads = cables.filter((c) => c !== cable).flatMap((c) => [c.start, c.end]);
    const leadObstacles = otherLeads.map((t) => ({
      x: Math.min(t.point.x, t.stub.x) - 0.07,
      y: Math.min(t.point.y, t.stub.y) - 0.07,
      width: Math.abs(t.point.x - t.stub.x) + 0.14,
      height: Math.abs(t.point.y - t.stub.y) + 0.14,
    }));
    try {
      cable.points = simplifyRoute([
        cable.start.point,
        ...routeOrthogonal(
          cable.start.stub,
          cable.end.stub,
          [...obstacles, ...leadObstacles],
          routeArea,
          [
            ...occupied,
            ...cables
              .filter((c) => c !== cable)
              .flatMap((c) => [
                { a: c.start.point, b: c.start.stub },
                { a: c.end.point, b: c.end.stub },
              ]),
          ],
          enclosureEdges,
        ),
        cable.end.point,
      ]);
      if (
        segmentsOf(cable.points).some(
          (s) =>
            enclosureEdges.some((edge) => parallelConflict(s, edge, ENCLOSURE_WIRE_CLEARANCE)) ||
            occupied.some((other) => parallelConflict(s, other)),
        )
      )
        throw new Error(
          'Cable terminal or continuation lead is too close to an enclosure outline.',
        );
    } catch (e) {
      throw new Error(
        `${cable.run.tag} (${cable.run.from.tag} → ${cable.run.to.tag}): no clear cable lane. Move the overlapping device or reset its pin.`,
        { cause: e },
      );
    }
    occupied.push(...segmentsOf(cable.points));
  }
  const labelBounds: Bounds[] = sheet.prims
    .filter((p): p is TextPrim => p.kind === 'text')
    .map(textBounds);
  sheet.connections = cables.map((c) => ({
    runId: c.run.runId,
    fromId: c.run.from.id,
    toId: c.run.to.id,
    points: c.points,
    fromPort: c.start.name,
    toPort: c.end.name,
    reference: c.continuation?.ref,
    fromContinuation: !c.fromLocal,
    toContinuation: !c.toLocal,
  }));
  const bounds = [...positions.values(), ...markerBounds];
  const freeLabel = (p: TextPrim) => {
    const box = textBounds(p);
    return (
      box.x >= area.x &&
      box.y >= area.y &&
      box.x + box.width <= area.x + area.width &&
      box.y + box.height <= area.y + area.height &&
      ![...bounds, ...labelBounds].some((b) => intersects(box, b, 0.06)) &&
      ![...occupied, ...enclosureEdges].some((s) =>
        segmentBlocked(s.a, s.b, [
          {
            x: box.x - 0.055,
            y: box.y - 0.055,
            width: box.width + 0.11,
            height: box.height + 0.11,
          },
        ]),
      )
    );
  };
  const addLabel = (p: TextPrim) => {
    sheet.prims.push(p);
    labelBounds.push(textBounds(p));
  };
  const terminalLabels: TextPrim[] = [];
  // Reserve readable control identification before optional power-cable details.
  for (const cable of [...cables].sort(
    (a, b) => Number(powerTypes.includes(a.run.type)) - Number(powerTypes.includes(b.run.type)),
  )) {
    const { run, layer, points, start, end, fromLocal, toLocal } = cable;
    // Horizontal bridges explicitly show crossings without an electrical junction.
    for (const seg of segmentsOf(points)) {
      const horizontal = Math.abs(seg.a.y - seg.b.y) < 1e-6;
      const crosses = horizontal
        ? occupied
            .map((s) => crossing(seg, s))
            .filter((p): p is Point => !!p)
            .filter((p) => Math.min(Math.abs(p.x - seg.a.x), Math.abs(p.x - seg.b.x)) > 0.09)
        : [];
      const xs = [...new Set(crosses.map((p) => p.x))].sort((a, b) => a - b);
      if (!xs.length)
        sheet.prims.push({
          kind: 'polyline',
          points: [seg.a, seg.b],
          layer,
          entityId: run.entityRef,
          role: 'wire',
          runId: run.runId,
          ...paint(run),
        });
      else {
        let x = Math.min(seg.a.x, seg.b.x);
        for (const cx of xs) {
          sheet.prims.push(
            {
              kind: 'polyline',
              points: [
                { x, y: seg.a.y },
                { x: cx - 0.07, y: seg.a.y },
              ],
              layer,
              entityId: run.entityRef,
              role: 'wire',
              runId: run.runId,
              ...paint(run),
            },
            {
              kind: 'arc',
              x: cx,
              y: seg.a.y,
              radius: 0.07,
              startDeg: 0,
              endDeg: 180,
              layer,
              linetype: 'Continuous',
              entityId: run.entityRef,
              role: 'wire',
              runId: run.runId,
              ...paint(run),
            },
          );
          x = cx + 0.07;
        }
        sheet.prims.push({
          kind: 'polyline',
          points: [
            { x, y: seg.a.y },
            { x: Math.max(seg.a.x, seg.b.x), y: seg.a.y },
          ],
          layer,
          entityId: run.entityRef,
          role: 'wire',
          runId: run.runId,
          ...paint(run),
        });
      }
    }
    for (const [terminal, local] of [
      [start, fromLocal],
      [end, toLocal],
    ] as const) {
      if (local) {
        sheet.prims.push({
          kind: 'circle',
          x: terminal.point.x,
          y: terminal.point.y,
          radius: 0.035,
          layer,
          linetype: 'Continuous',
          lineweightMm: 0.18,
          entityId: run.entityRef,
          role: 'terminal',
          runId: run.runId,
          ...(wires.client ? { color: paint(run).color } : {}),
        });
        const p = text(
          terminal.name,
          terminal.point.x + 0.09,
          terminal.point.y + 0.1,
          3 / 32,
          'E-ANNO-TAGS',
        );
        p.runId = run.runId;
        if (terminal.side === 'W') p.x = terminal.point.x - textWidth(terminal.name) - 0.09;
        if (terminal.inlineMarker && terminal.side === 'E') p.x = terminal.point.x + 0.42;
        if (terminal.inlineMarker && terminal.side === 'W')
          p.x = terminal.point.x - textWidth(terminal.name) - 0.42;
        if (terminal.side === 'S') p.y = terminal.point.y - 0.19;
        // Terminal names are installer detail; the client diagram leaves them out.
        if (!wires.client) terminalLabels.push(p);
      } else {
        const marker = terminal.marker!;
        sheet.prims.push(
          {
            kind: 'circle',
            x: marker.center.x,
            y: marker.center.y,
            radius: marker.radius,
            layer: 'E-ANNO-TAGS',
            role: 'continuation',
            runId: run.runId,
          },
          { ...marker.reference, runId: run.runId },
          { ...marker.label, runId: run.runId },
        );
      }
    }
    // The reserved continuation callout already carries the cable identity.
    if (!fromLocal || !toLocal) continue;
    const members = wires.members.get(run.runId) ?? [run];
    const label = project.settings.wireLabelTemplate
      .replaceAll('{tag}', `${run.tag}${run.from.port ? ` / ${run.from.port}` : ''}`)
      .replaceAll('{wireLabel}', riserWireLabel(library, members))
      .replaceAll('{lengthFt}', run.lengthFt.toFixed(1))
      .replaceAll('{vdPct}', run.vdPct?.toFixed(1) ?? '—');
    let placed = false;
    const segs = segmentsOf(points).sort(
      (a, b) =>
        Math.abs(b.a.x - b.b.x) +
        Math.abs(b.a.y - b.b.y) -
        (Math.abs(a.a.x - a.b.x) + Math.abs(a.a.y - a.b.y)),
    );
    const control = !powerTypes.includes(run.type);
    for (const value of wires.client
      ? clientWireLabels(library, members)
      : control
        ? [
            `${controlName(run)} · ${label}`,
            `${controlName(run)} · ${run.tag}`,
            `${controlName(run)}\n${run.tag}`,
          ]
        : [label, `${run.tag} / ${run.from.port ?? 'POWER'}`, run.tag]) {
      placement: for (const seg of segs) {
        const horizontal = Math.abs(seg.a.y - seg.b.y) < 1e-6;
        const length = horizontal ? Math.abs(seg.a.x - seg.b.x) : Math.abs(seg.a.y - seg.b.y);
        if (length < 0.45) continue;
        for (const side of [1, -1]) {
          for (const along of [0.5, 0.25, 0.75, 0.1, 0.9, 0.35, 0.65]) {
            const width = horizontal ? Math.min(2.05, length - 0.15) : 1.8;
            if (control && width < Math.max(textWidth(controlName(run)), textWidth(run.tag)))
              continue;
            const p = paragraph(
              value,
              horizontal
                ? (seg.a.x + seg.b.x) / 2 - width / 2
                : seg.a.x + (side > 0 ? 0.13 : -width - 0.13),
              horizontal ? seg.a.y + 0.12 : seg.a.y + (seg.b.y - seg.a.y) * along,
              width,
            );
            const rows = p.value.split('\n').length;
            if (horizontal) p.x = seg.a.x + (seg.b.x - seg.a.x) * along - textWidth(p.value) / 2;
            else if (side < 0) p.x = seg.a.x - textWidth(p.value) - 0.13;
            if (horizontal)
              p.y = side > 0 ? seg.a.y + 0.12 + (rows - 1) * p.heightIn * 1.45 : seg.a.y - 0.22;
            p.role = 'wire-tag';
            p.runId = run.runId;
            if (freeLabel(p)) {
              addLabel(p);
              placed = true;
              break placement;
            }
          }
        }
      }
      if (placed) break;
    }
    if (!placed && control)
      throw new Error(`${run.tag}: no clear control label. Move the device or reset its pin.`);
    if (!placed)
      sheet.layoutWarnings.push(
        `${run.tag}: callout moved to wire schedule; no clear label region.`,
      );
  }
  // The signal and cable identity take priority over optional terminal captions.
  for (const p of terminalLabels) if (freeLabel(p)) addLabel(p);
}
