import type { Project } from '@ill/core-schemas/project';
import type { LibrarySnapshot } from '@ill/core-schemas/library';
import type { EngineResult } from '@ill/engine/model';
import { seedLayers, seedTitleBlocks } from '@ill/data/seeds';
import { flattenSheet, line, text, type Sheet, type Primitive } from '../model';
import { paragraph, wrapText } from '../text';
import { titleBlockLogo } from '../brand';
import { powerTypes } from '@ill/engine/wireSelect';

const BODY = 3 / 32;
const LEADING = BODY * 1.45;
const labels: Record<string, string> = {
  brandLogo: '',
  project: 'PROJECT',
  number: 'PROJECT NUMBER',
  client: 'CLIENT',
  address: 'SITE ADDRESS',
  sheetTitle: 'SHEET TITLE',
  sheetNumber: 'SHEET',
  date: 'DATE',
  scale: 'SCALE',
  drawnBy: 'DRAWN BY',
  checkedBy: 'CHECKED BY',
  revisions: 'LATEST REVISION',
  stamp: 'ISSUE STATUS',
};
export function frameSheet(sheet: Sheet, project: Project, total: number) {
  const template = seedTitleBlocks.find((s) => s.sheetSize === sheet.size)!;
  const rect = (r: { x: number; y: number; width: number; height: number }): Primitive => ({
    kind: 'rect',
    ...r,
    layer: 'E-ANNO-TTLB',
  });
  sheet.prims.push(
    rect(template.border),
    rect(template.titleBlock),
    rect(template.referenceSquare),
  );
  const ref = template.referenceSquare;
  sheet.prims.push(
    paragraph('1.000 in\nREF. SQUARE', ref.x + 0.1, ref.y + 0.6, 0.8),
    text(
      `${sheet.number} / ${total}  ·  ALL LENGTHS ARE ONE-WAY UNLESS NOTED`,
      ref.x + 1.3,
      ref.y + 0.3,
    ),
  );
  const revision = project.revisions.at(-1);
  const values: Record<string, string> = {
    brandLogo: project.meta.brand === '206' ? '206 LIGHTING' : 'ilLumenate Lighting',
    project: project.meta.name,
    number: project.meta.number,
    client: project.meta.client,
    address: project.meta.siteAddress,
    sheetTitle: sheet.title,
    sheetNumber: sheet.number,
    date: project.meta.date,
    scale: 'NOT TO SCALE',
    drawnBy: project.meta.designer,
    checkedBy: project.meta.checker,
    revisions: revision
      ? `${revision.rev} · ${revision.date}\n${revision.description}\nBY ${revision.by}`
      : '—',
    stamp: project.meta.stamp === 'NONE' ? '' : project.meta.stamp,
  };
  for (const field of template.fields) {
    const r = field.region;
    const top = r.y + r.height;
    sheet.prims.push(
      line(
        template.titleBlock.x,
        r.y,
        template.titleBlock.x + template.titleBlock.width,
        r.y,
        'E-ANNO-TTLB',
      ),
    );
    if (labels[field.name])
      sheet.prims.push(text(labels[field.name]!, r.x, top - 0.14, BODY, 'E-ANNO-TTLB'));
    if (field.name === 'brandLogo' && project.meta.brand !== '206') {
      sheet.prims.push(...titleBlockLogo(r));
      continue;
    }
    const height =
      field.name === 'brandLogo' ? 0.25 : field.name === 'sheetNumber' ? 0.32 : field.textHeightIn;
    // heightIn is cap height: reserve the gap above the letters, not above their baseline.
    const valueTop = top - (labels[field.name] ? 0.14 + (height >= 0.1875 ? 0.18 : 0.15) : 0.16);
    const baseline = valueTop - height;
    const maxLines = Math.max(1, 1 + Math.floor((baseline - r.y - 0.06) / (height * 1.45)));
    const all = wrapText(values[field.name] ?? '', r.width, height, 'bold');
    // Full revision text and all long project metadata are retained on the schedules.
    const value =
      all.length > maxLines
        ? [...all.slice(0, maxLines - 1), 'SEE PROJECT RECORD'].join('\n')
        : all.join('\n');
    sheet.prims.push({
      ...text(value, r.x, baseline, height, 'E-ANNO-TTLB', 'bold'),
      multiline: true,
    });
  }
}

type Table = { title: string; heads: string[]; weights: number[]; rows: string[][] };
export function composeSheets(
  diagrams: Sheet[],
  project: Project,
  library: LibrarySnapshot,
  result: EngineResult,
): Sheet[] {
  const sheets = [...diagrams];
  if (!project.settings.showSchedules) {
    sheets.forEach((sheet) => frameSheet(sheet, project, sheets.length));
    return sheets;
  }
  const template = seedTitleBlocks.find((t) => t.sheetSize === project.settings.sheet.size)!;
  const area = template.drawingArea;
  const item = (id: string) => library.products.find((p) => p.id === id);
  const len = (ft: number) => `${(project.settings.units === 'm' ? ft * 0.3048 : ft).toFixed(1)}`;
  const tables: Table[] = [
    {
      title: 'EQUIPMENT SCHEDULE',
      heads: ['TAG', 'QTY', 'SKU / MODEL', 'LOCATION / ENCLOSURE', 'POWER / CONTROL'],
      weights: [1, 0.5, 3, 2, 2.2],
      rows: project.equipment.map((e) => [
        e.tag,
        String(e.qty),
        `${item(e.catalogId)?.sku ?? 'UNRESOLVED'}\n${item(e.catalogId)?.model ?? ''}`,
        `${e.location}\n${e.enclosure ?? ''}`,
        `${e.fedFrom?.ref ?? '—'} ${e.fedFrom?.port ?? ''}\n${
          result.runs
            .filter((r) => r.to.id === e.id && !powerTypes.includes(r.type))
            .map((r) => `${r.from.tag}${r.from.port ? ` / ${r.from.port}` : ''}`)
            .join(', ') || '—'
        }`,
      ]),
    },
    {
      title: 'LOAD SCHEDULE',
      heads: ['TAG', 'SKU / MODEL', 'QTY / LENGTH', 'WATTS', 'FEED / ZONE'],
      weights: [1, 3, 1.4, 1, 2.3],
      rows: project.loads.map((l) => [
        l.typeTag,
        `${item(l.catalogId)?.sku ?? 'UNRESOLVED'}\n${item(l.catalogId)?.model ?? ''}`,
        l.lengthFt !== undefined
          ? `${len(l.lengthFt)} ${project.settings.units}`
          : `${l.qty ?? 1} ea`,
        (result.loadWatts[l.id] ?? 0).toFixed(1),
        `${l.fedFrom.ref} ${l.fedFrom.port ?? ''}\n${l.zone}${l.enclosure ? ` / ${l.enclosure}` : ''}`,
      ]),
    },
    {
      title: 'WIRE SCHEDULE',
      heads: [
        'TAG',
        'WIRE / FROM → TO',
        'LENGTH ' + project.settings.units.toUpperCase(),
        'A',
        'VD %',
        'END V',
        'SETS',
      ],
      weights: [0.8, 3.5, 1, 0.65, 0.7, 0.7, 0.6],
      rows: result.runs.map((r) => [
        r.tag,
        `${library.wires.find((w) => w.id === r.wireTypeId)?.riserLabel ?? 'NO VALID WIRE'}\n${r.from.tag}${r.from.port ? `:${r.from.port}` : ''} → ${r.to.tag}${r.to.port ? `:${r.to.port}` : ''}`,
        len(r.lengthFt),
        r.currentA.toFixed(2),
        r.vdPct?.toFixed(2) ?? '—',
        r.endV?.toFixed(2) ?? '—',
        `${r.parallelSets}${r.parallelCommonConductors > 1 ? ` / ${r.parallelCommonConductors} common` : ''}`,
      ]),
    },
    {
      title: 'LOADING / CAPACITY',
      heads: ['TAG / OUTPUT', 'LOAD', 'RATED', 'LOAD %'],
      weights: [3, 1.3, 1.3, 1],
      rows: result.loading.map((l) => [
        `${l.tag} / ${l.port}`,
        `${(l.units === 'W' ? l.wattsW : l.currentA).toFixed(2)} ${l.units}`,
        `${l.capacity} ${l.units}`,
        l.percent.toFixed(1),
      ]),
    },
    {
      title: 'DMX PATCH',
      heads: ['TAG', 'UNIVERSE', 'START', 'END', 'FOOTPRINT'],
      weights: [2, 1, 1, 1, 1],
      rows: result.patch.map((p) => [
        p.tag,
        String(p.universe),
        String(p.startAddress ?? '—'),
        String(p.endAddress ?? '—'),
        String(p.footprint),
      ]),
    },
    {
      title: 'BILL OF MATERIALS',
      heads: ['SKU', 'DESCRIPTION', 'QUANTITY', 'REELS'],
      weights: [2, 4, 1.2, 0.8],
      rows: result.bom.map((b) => [
        b.sku,
        `${b.description}${b.isExample ? ' [EXAMPLE]' : ''}`,
        `${b.unit === 'ft' ? len(b.quantity) : b.quantity} ${b.unit === 'ft' ? project.settings.units : b.unit}`,
        b.reels === undefined ? '—' : String(b.reels),
      ]),
    },
    {
      title: 'GENERAL NOTES',
      heads: ['NO.', 'NOTE'],
      weights: [0.5, 8],
      rows: project.generalNotes.map((n, i) => [String(i + 1), n]),
    },
    {
      title: 'KEY NOTES',
      heads: ['KEY', 'NOTE'],
      weights: [0.7, 8],
      rows: project.keyNotes.map((n) => [n.id, n.text]),
    },
    {
      title: 'REVISIONS',
      heads: ['REV', 'DATE', 'DESCRIPTION', 'BY'],
      weights: [0.6, 1.2, 4, 1.2],
      rows: project.revisions.map((r) => [r.rev, r.date, r.description, r.by]),
    },
    {
      title: 'PROJECT RECORD',
      heads: ['FIELD', 'VALUE'],
      weights: [1.5, 6],
      rows: [
        ['Project', project.meta.name],
        ['Number', project.meta.number],
        ['Client', project.meta.client],
        ['Site', project.meta.siteAddress],
        ['Designer / checker', `${project.meta.designer} / ${project.meta.checker}`],
        [
          'Basis',
          `NEC ${project.settings.necEdition}; PSU operating target ${project.settings.psuDeratePct}%; line / DC VD targets ${project.settings.vdTargetLineVoltagePct}% / ${project.settings.vdTargetLowVoltagePct}%.`,
        ],
        [
          'Review',
          `${result.messages.filter((m) => m.severity === 'error').length} errors; ${result.messages.filter((m) => m.severity === 'warning').length} warnings. Resolve engineering Review before issue. Example products and wire templates require verification.`,
        ],
      ],
    },
  ];
  const sheetForNode = new Map(
    diagrams.flatMap((s) => s.nodes.map((n) => [n.id, s.number] as const)),
  );
  const references = new Map<string, Set<string>>();
  for (const c of diagrams.flatMap((s) => s.connections ?? []))
    if (c.reference) {
      const ids = references.get(c.reference) ?? new Set<string>();
      ids.add(c.runId);
      references.set(c.reference, ids);
    }
  if (references.size)
    tables.splice(3, 0, {
      title: 'CONTINUATION INDEX',
      heads: ['REF', 'FROM SHEET / EQUIPMENT', 'TO SHEET(S)', 'CABLE TAGS'],
      weights: [0.7, 2.5, 2.5, 4],
      rows: [...references].map(([ref, ids]) => {
        const runs = result.runs.filter((r) => ids.has(r.runId));
        const first = runs[0]!;
        return [
          ref,
          `${sheetForNode.get(first.from.id)} / ${first.from.tag}${first.from.port ? `:${first.from.port}` : ''}`,
          [...new Set(runs.map((r) => sheetForNode.get(r.to.id)))].join(', '),
          runs.map((r) => r.tag).join(', '),
        ];
      }),
    });
  const columns = area.width >= 22 ? 2 : 1;
  const width = (area.width - (columns - 1) * 0.5) / columns;
  let current: Sheet | undefined;
  const bottom = area.y + 0.2;
  let top = 0,
    column = 0,
    y = 0;
  const clearRegions: { sheet: Sheet; top: number }[] = [];
  function newSheet() {
    const region = clearRegions.shift();
    if (region) {
      current = region.sheet;
      top = region.top;
      column = 0;
      y = top;
      return;
    }
    const n = sheets.length + 1;
    current = {
      id: `sheet-${n}`,
      number: `${project.meta.sheetPrefix}${n}`,
      title: 'SCHEDULES, LEGEND & NOTES',
      size: template.sheetSize,
      widthIn: template.widthIn,
      heightIn: template.heightIn,
      prims: [],
      blocks: [],
      nodes: [],
      layoutWarnings: [],
    };
    sheets.push(current);
    top = area.y + area.height - 0.25;
    column = 0;
    y = top;
  }
  // Reuse clear paper below every diagram before adding schedule-only sheets.
  for (const diagram of diagrams.filter((s) => s.nodes.length)) {
    const flat = flattenSheet(diagram);
    const lows = flat.flatMap((p) =>
      p.kind === 'line'
        ? [p.from.y, p.to.y]
        : p.kind === 'polyline' || p.kind === 'hatch'
          ? p.points.map((q) => q.y)
          : p.kind === 'filledPath'
            ? p.contours.flatMap((c) => [
                c.start.y,
                ...c.segments.flatMap((s) =>
                  s.kind === 'line' ? [s.to.y] : [s.to.y, s.control1.y, s.control2.y],
                ),
              ])
            : p.kind === 'text'
              ? [p.y - (p.value.split('\n').length - 1) * p.heightIn * 1.45]
              : [p.y - (p.kind === 'circle' || p.kind === 'arc' ? p.radius : 0)],
    );
    const clearTop = Math.min(...lows) - 0.65;
    if (clearTop - bottom >= 3) clearRegions.push({ sheet: diagram, top: clearTop });
  }
  newSheet();
  const x = () => area.x + column * (width + 0.5);
  function advance() {
    if (column + 1 < columns) {
      column++;
      y = top;
    } else newSheet();
  }
  function need(height: number) {
    if (y - height < bottom) advance();
  }
  function title(value: string) {
    need(0.6);
    current!.prims.push(
      text(value, x(), y, 0.1875, 'E-ANNO-SCHD', 'bold'),
      line(x(), y - 0.12, x() + width, y - 0.12, 'E-ANNO-SCHD'),
    );
    y -= 0.4;
  }
  for (const table of tables) {
    if (!table.rows.length) continue;
    need(1.3);
    title(table.title);
    const sum = table.weights.reduce((a, b) => a + b, 0);
    const widths = table.weights.map((w) => (width * w) / sum);
    function row(values: string[], heading = false) {
      const lines = values.map((v, i) =>
        wrapText(v, Math.max(0.2, widths[i]! - 0.14), BODY, heading ? 'bold' : 'main'),
      );
      const rowHeight = Math.max(0.3, Math.max(...lines.map((l) => l.length)) * LEADING + 0.16);
      // A pathological field is broken into continuation rows, never clipped or reduced below plotted size.
      const maxLines = Math.max(1, Math.floor((top - bottom - 0.9) / LEADING));
      if (lines.some((l) => l.length > maxLines)) {
        const chunks = Math.ceil(Math.max(...lines.map((l) => l.length)) / maxLines);
        for (let n = 0; n < chunks; n++)
          row(
            lines.map((l) => l.slice(n * maxLines, (n + 1) * maxLines).join('\n')),
            heading,
          );
        return;
      }
      if (y - rowHeight < bottom) {
        advance();
        title(`${table.title} (CONTINUED)`);
        if (!heading) row(table.heads, true);
      }
      let xx = x();
      current!.prims.push(
        line(xx, y, xx + width, y, 'E-ANNO-SCHD'),
        line(xx, y - rowHeight, xx + width, y - rowHeight, 'E-ANNO-SCHD'),
      );
      lines.forEach((l, i) => {
        current!.prims.push(line(xx, y, xx, y - rowHeight, 'E-ANNO-SCHD'), {
          ...text(
            l.join('\n'),
            xx + 0.07,
            y - BODY - 0.075,
            BODY,
            'E-ANNO-SCHD',
            heading ? 'bold' : 'main',
          ),
          multiline: l.length > 1,
        });
        xx += widths[i]!;
      });
      current!.prims.push(line(xx, y, xx, y - rowHeight, 'E-ANNO-SCHD'));
      y -= rowHeight;
    }
    row(table.heads, true);
    for (const values of table.rows) row(values);
    y -= 0.45;
  }
  const used = new Map(
    diagrams.flatMap((s) =>
      s.prims
        .filter((p) => p.kind === 'block')
        .map((p) => [p.symbolId, s.blocks.find((b) => b.id === p.symbolId)!] as const),
    ),
  );
  if (used.size) {
    need(3);
    title('SYMBOL LEGEND');
    const list = [...used.values()];
    const across = Math.max(1, Math.floor(width / 3.4));
    for (let i = 0; i < list.length; i += across) {
      const row = list.slice(i, i + across);
      const height = Math.max(...row.map((s) => s.heightIn));
      need(height + 0.4);
      row.forEach((symbol, j) => {
        if (!current!.blocks.some((b) => b.id === symbol.id)) current!.blocks.push(symbol);
        current!.prims.push({
          kind: 'block',
          symbolId: symbol.id,
          x: x() + j * 3.4,
          y: y - height,
          rotation: 0,
          scale: 1,
          layer: symbol.prims[0]!.layer,
          attributes: { TAG: symbol.label },
        });
      });
      y -= height + 0.35;
    }
  }
  title('LINE LEGEND');
  const layers = new Set(diagrams.flatMap((s) => flattenSheet(s).map((p) => p.layer)));
  for (const layer of seedLayers.layers.filter(
    (l) =>
      (layers.has(l.name) && l.export && l.name.includes('WIRE')) ||
      (layers.has(l.name) &&
        l.export &&
        l.name.startsWith('E-LITE-CTRL-') &&
        !l.name.endsWith('EQPM')),
  )) {
    need(0.45);
    current!.prims.push(
      line(x(), y - 0.04, x() + 1.3, y - 0.04, layer.name),
      text(layer.description, x() + 1.5, y - 0.08),
    );
    y -= 0.4;
  }
  need(0.9);
  current!.prims.push(
    line(x(), y, x() + 0.53, y, 'E-ANNO-TEXT'),
    { kind: 'arc', x: x() + 0.6, y, radius: 0.07, startDeg: 0, endDeg: 180, layer: 'E-ANNO-TEXT' },
    line(x() + 0.67, y, x() + 1.3, y, 'E-ANNO-TEXT'),
    line(x() + 0.6, y - 0.18, x() + 0.6, y + 0.22, 'E-ANNO-TEXT'),
    text('Cable crossing / no electrical connection', x() + 1.5, y - 0.04),
    { kind: 'circle', x: x() + 0.6, y: y - 0.45, radius: 0.035, layer: 'E-ANNO-TEXT' },
    line(x(), y - 0.45, x() + 0.6, y - 0.45, 'E-ANNO-TEXT'),
    text(
      'Open circle at equipment outline = cable connection; W-tags refer to wire schedule',
      x() + 1.5,
      y - 0.49,
    ),
  );
  sheets.forEach((s) => frameSheet(s, project, sheets.length));
  return sheets;
}
