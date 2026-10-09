import type { Project } from '@ill/core-schemas/project';
import type { LibrarySnapshot } from '@ill/core-schemas/library';
import type { RunResult } from '@ill/engine/model';
import { buildGraph } from '@ill/engine/graph';
import { powerTypes } from '@ill/engine/wireSelect';
import { seedTitleBlocks } from '@ill/data/seeds';
import { symbolFor, symbols } from '../symbols';
import { makeSymbol, SYMBOL_HEIGHT } from '../symbols/factory';
import { text, translate, type LayerName, type Sheet } from '../model';
import { paragraph, wrapText } from '../text';
import { type LayoutNode, type LayoutResult } from './types';
import { ROW_GAP, STAGE_GAP } from './columns';
import {
  enclosureLayout,
  enclosureGroups,
  enclosureRanks,
  unitId,
  ENCLOSURE_PAD,
  ENCLOSURE_HEAD,
} from './enclosures';
import { drawConnections } from './connections';
import { applyPins } from './pins';
import { intersects, type Bounds } from './router';
import { modelLabel } from '../labels';
import type { DrawingOptions } from '../options';
import { clientSymbol, productFamily } from '../client';
import type { DrawnRuns } from '../wires';

export const layerForRun = (run: RunResult): LayerName =>
  run.type.startsWith('lv-')
    ? 'E-POWR-WIRE-LV'
    : ['class2-dc', 'class2-dc-multichannel', 'landscape-ac'].includes(run.type)
      ? 'E-LITE-WIRE-CL2'
      : ['dmx', 'ethernet'].includes(run.type)
        ? 'E-LITE-CTRL-DMX'
        : run.type === 'wireless'
          ? 'E-LITE-CTRL-WRLS'
          : run.type === 'spi-data'
            ? 'E-LITE-CTRL-SPI'
            : run.type.startsWith('lutron')
              ? 'E-LITE-CTRL-LUTR'
              : 'E-LITE-CTRL-SIGL';
type PreparedPage = {
  nodes: LayoutNode[];
  layout: LayoutResult;
  extraGap: number;
  denseMarkersFirst?: boolean;
};
export async function layoutProject(
  project: Project,
  library: LibrarySnapshot,
  drawn: DrawnRuns,
  options: DrawingOptions = {},
): Promise<Sheet[]> {
  const { result } = drawn;
  const client = options.style === 'client';
  const template = seedTitleBlocks.find((s) => s.sheetSize === project.settings.sheet.size)!;
  const area = { ...template.drawingArea };
  const gutter = 1.65;
  const width = area.width - gutter * 2;
  const height =
    area.height - 0.65 - (project.settings.showSchedules ? Math.min(4, area.height * 0.22) : 0);
  const graph = buildGraph(project, library.products);
  const controllers = new Set([
    'dmx-controller',
    'dmx-decoder',
    'relay',
    '0-10v-dimmer',
    'dmx-0-10v-converter',
    'sacn-gateway',
    'network-switch',
    'wireless-tx',
    'wireless-rx',
    'opto-splitter',
    'pixel-controller',
    'keypad',
    'lutron-module',
  ]);
  const controlNode = (category: string | undefined) => controllers.has(category ?? '');
  /** The model line on a symbol; the client diagram shows a configured fixture's own part number. */
  const modelText = (node: { id: string; item?: (typeof library.products)[number] }) => {
    if (!node.item) return '';
    if (!client) return modelLabel(node.item);
    const own = options.loads?.[node.id]?.partNumber;
    if (own) return own;
    return modelLabel(node.item).replace(/ · DATA BY DEALER$/, '');
  };
  const nodes: LayoutNode[] = [...graph.nodes.values()].map((node) => {
    let symbol = symbolFor(node.item, node.kind === 'source');
    if (node.item?.specs.kind === 'tape') {
      const count = node.item.specs.channels;
      symbol = makeSymbol(
        `led-tape-${count}ch`,
        `LED TAPE · ${count} CH`,
        'E-LITE-FIXT',
        'tape',
        count,
      );
    }
    const modelLines = wrapText(modelText(node), symbol.widthIn - 0.28).length;
    const outputs = result.runs.filter((r) => r.from.id === node.id);
    const outputPorts = Math.max(
      ...[true, false].map(
        (power) =>
          new Set(
            outputs
              .filter((r) => powerTypes.includes(r.type) === power)
              .map((r) => `${r.type}:${r.from.port ?? ''}`),
          ).size,
      ),
    );
    const naturalHeight = symbol.heightIn + (Math.max(2, modelLines) - 3) * 0.14;
    const fittedHeight = Math.max(
      naturalHeight,
      outputPorts >= 4 ? (outputPorts - 1) * 0.56 + 0.6 : 0,
    );
    const extra = fittedHeight - symbol.heightIn;
    if (Math.abs(extra) > 0.001) {
      symbol = {
        ...symbol,
        id: `${symbol.id}-h${fittedHeight.toFixed(3)}`,
        heightIn: symbol.heightIn + extra,
        prims: symbol.prims.map((p) =>
          p.kind === 'rect' ? { ...p, height: p.height + extra } : translate(p, 0, extra),
        ),
        attributes: symbol.attributes.map((a) =>
          ['TAG', 'MODEL'].includes(a.tag) ? { ...a, y: a.y + extra } : a,
        ),
        ports: symbol.ports.map((p) =>
          p.side === 'W' || p.side === 'E' ? { ...p, offset: p.offset + extra / 2 } : p,
        ),
      };
    }
    if (client)
      symbol = clientSymbol(
        symbol,
        productFamily(
          node.item,
          node.kind === 'source',
          controlNode(node.item?.category),
          node.kind === 'load' ? options.loads?.[node.id]?.type : undefined,
        ),
      );
    let root = node;
    let psu = '';
    const seen = new Set<string>();
    while (!seen.has(root.id)) {
      seen.add(root.id);
      if (['psu', 'driver'].includes(root.item?.category ?? '')) psu = root.id;
      const edge = graph.power.find((e) => e.to === root.id);
      if (!edge) break;
      root = graph.nodes.get(edge.from)!;
    }
    const source = root.kind === 'source' && 'panel' in root.entity ? root.entity : undefined;
    const category = node.item?.category;
    const control = controlNode(category);
    return {
      id: node.id,
      tag: node.tag,
      symbol,
      control,
      terminal: node.kind === 'load',
      partition:
        node.kind === 'source'
          ? 0
          : ['psu', 'driver'].includes(category ?? '')
            ? 1
            : node.kind === 'load' || !control
              ? 4
              : 2,
      enclosure: 'enclosure' in node.entity ? (node.entity.enclosure ?? '').trim() : '',
      panel: source?.panel ?? 'Unresolved',
      circuit: source?.id ?? root.id,
      psu: psu || node.id,
    };
  });
  const maxHeight = Math.max(SYMBOL_HEIGHT, ...nodes.map((n) => n.symbol.heightIn));
  const ranks = enclosureRanks(nodes, result.runs);
  async function prepare(group: LayoutNode[], extraGap = 0): Promise<PreparedPage> {
    return {
      nodes: group,
      extraGap,
      layout: enclosureLayout(
        group,
        result.runs,
        project.settings.sheet.flow,
        { width, height },
        ranks,
        extraGap,
      ),
    };
  }
  const fits = (p: PreparedPage) => p.layout.width <= width && p.layout.height <= height;
  const pages: PreparedPage[] = [];
  async function split(group: LayoutNode[], depth = 0): Promise<void> {
    if (!group.length) return;
    const p = await prepare(group);
    if (fits(p)) {
      pages.push(p);
      return;
    }
    const atoms = enclosureGroups(group);
    // Keep named enclosures intact even when their contents use different circuits.
    const chunks = atoms.length > 1 ? atoms : group.map((n) => [n]);
    const key = depth === 0 ? 'panel' : depth === 1 ? 'circuit' : depth === 2 ? 'psu' : null;
    if (key) {
      const grouped = new Map<string, LayoutNode[]>();
      for (const chunk of chunks) {
        const value = chunk[0]![key];
        grouped.set(value, [...(grouped.get(value) ?? []), ...chunk]);
      }
      if (grouped.size > 1) {
        for (const g of grouped.values()) await split(g, depth + 1);
        return;
      }
      await split(group, depth + 1);
      return;
    }
    if (group.length === 1)
      throw new Error('A symbol does not fit at true plotted size. Use a larger sheet.');
    // The final subdivision keeps columns and row stacks intact; all crossing runs get paired connectors.
    const columns = Math.max(1, Math.floor((width + STAGE_GAP) / (2.8 + STAGE_GAP)));
    const rows = Math.max(
      1,
      Math.floor(
        (height - (group.some((n) => n.control) ? maxHeight + 0.85 : 0)) / (maxHeight + ROW_GAP),
      ),
    );
    const stageOf = (chunk: LayoutNode[]) => Math.min(...chunk.map((n) => n.partition));
    const stages = [...new Set(chunks.map(stageOf))].sort((a, b) => a - b);
    if (stages.length > 1) {
      for (const stage of stages) await split(chunks.filter((c) => stageOf(c) === stage).flat(), 4);
      return;
    }
    const buckets = new Map<string, LayoutNode[]>();
    for (const stage of stages) {
      const members = chunks
        .filter((c) => stageOf(c) === stage)
        .sort(
          (a, b) =>
            a[0]!.enclosure.localeCompare(b[0]!.enclosure, undefined, { numeric: true }) ||
            a[0]!.tag.localeCompare(b[0]!.tag, undefined, { numeric: true }),
        );
      members.forEach((chunk, i) => {
        const key = `${Math.floor(i / (rows * columns))}`;
        buckets.set(key, [...(buckets.get(key) ?? []), ...chunk]);
      });
    }
    if (buckets.size === 1) {
      const middle = Math.ceil(chunks.length / 2);
      await split(chunks.slice(0, middle).flat(), 4);
      await split(chunks.slice(middle).flat(), 4);
    } else for (const g of buckets.values()) await split(g, 4);
  }
  await split(nodes);
  // Recombine small panel/circuit groups when they fit, instead of allocating a
  // mostly-empty sheet for every group boundary.
  for (let i = 0; i < pages.length; i++) {
    for (let j = i + 1; j < pages.length;) {
      const leftIds = new Set(pages[i]!.nodes.map((n) => n.id));
      const rightIds = new Set(pages[j]!.nodes.map((n) => n.id));
      const linked = result.runs.some(
        (r) =>
          (leftIds.has(r.from.id) && rightIds.has(r.to.id)) ||
          (rightIds.has(r.from.id) && leftIds.has(r.to.id)),
      );
      const sameStage = pages[i]!.nodes.some((a) =>
        pages[j]!.nodes.some((b) => ranks.get(unitId(a)) === ranks.get(unitId(b))),
      );
      if (!linked && !sameStage) {
        j++;
        continue;
      }
      const merged = await prepare([...pages[i]!.nodes, ...pages[j]!.nodes]);
      if (fits(merged)) {
        pages[i] = merged;
        pages.splice(j, 1);
      } else {
        // Bring a fitting prefix of terminal receivers beside their source.
        // Re-route after placement; never move already-drawn continuation stubs.
        const receivers = pages[j]!.nodes.filter(
          (n) =>
            n.terminal &&
            !n.enclosure &&
            (pages[i]!.nodes.every((a) => a.terminal && !a.enclosure) ||
              result.runs.some(
                (r) => r.to.id === n.id && leftIds.has(r.from.id) && powerTypes.includes(r.type),
              )),
        );
        let moved = false;
        for (const receiver of receivers) {
          const candidate = await prepare([...pages[i]!.nodes, receiver]);
          if (!fits(candidate)) break;
          pages[i] = candidate;
          pages[j] = await prepare(pages[j]!.nodes.filter((n) => n.id !== receiver.id));
          moved = true;
        }
        if (moved && !pages[j]!.nodes.length) pages.splice(j, 1);
        else j++;
      }
    }
  }
  if (!pages.length) pages.push(await prepare([]));
  let renderingPage = 0;
  function renderPages(): Sheet[] {
    pages.sort(
      (a, b) =>
        Math.min(...a.nodes.map((n) => ranks.get(unitId(n))!)) -
        Math.min(...b.nodes.map((n) => ranks.get(unitId(n))!)),
    );
    const pageOf = new Map(pages.flatMap((p, i) => p.nodes.map((n) => [n.id, i] as const)));
    // Power cables from one output may share an outgoing continuation trunk.
    // Each control cable keeps an individual reference on both ends.
    const continuations = new Map<string, { ref: string; runs: RunResult[] }>();
    const continuationFor = new Map<string, { ref: string; runs: RunResult[] }>();
    for (const run of [...result.runs].sort(
      (a, b) =>
        a.from.tag.localeCompare(b.from.tag, undefined, { numeric: true }) ||
        (a.from.port ?? '').localeCompare(b.from.port ?? '', undefined, { numeric: true }) ||
        a.type.localeCompare(b.type) ||
        a.to.tag.localeCompare(b.to.tag, undefined, { numeric: true }),
    )) {
      if (pageOf.get(run.from.id) === pageOf.get(run.to.id)) continue;
      // Control links are individually traceable physical connections, including
      // links from different outputs and links which cross the same sheet boundary.
      const key = powerTypes.includes(run.type)
        ? `${run.from.id}:${run.from.port ?? ''}:${run.type}`
        : run.runId;
      let group = continuations.get(key);
      if (!group) {
        group = { ref: `X${continuations.size + 1}`, runs: [] };
        continuations.set(key, group);
      }
      group.runs.push(run);
      continuationFor.set(run.runId, group);
    }
    return pages.map((prepared, pageIndex) => {
      renderingPage = pageIndex;
      const number = `${project.meta.sheetPrefix}${pageIndex + 1}`;
      const sheet: Sheet = {
        id: `sheet-${pageIndex + 1}`,
        number,
        title: client ? 'LIGHTING SYSTEM OVERVIEW' : 'LIGHTING SYSTEM RISER',
        ...(client ? { colored: true } : {}),
        size: template.sheetSize,
        widthIn: template.widthIn,
        heightIn: template.heightIn,
        prims: [],
        blocks: [
          ...new Map([...symbols, ...nodes.map((n) => n.symbol)].map((s) => [s.id, s])).values(),
        ],
        nodes: [],
        layoutWarnings: [],
      };
      const origin = {
        x: area.x + gutter,
        y: area.y + area.height - prepared.layout.height - 0.5,
      };
      const positions = new Map<string, Bounds>();
      for (const [id, p] of prepared.layout.nodes)
        positions.set(id, { ...p, x: p.x + origin.x, y: p.y + origin.y });
      applyPins(prepared.nodes, positions, project, area);
      for (const n of prepared.nodes) {
        const pin = project.layoutOverrides[n.id];
        const p = positions.get(n.id)!;
        if (
          p.x < area.x ||
          p.y < area.y ||
          p.x + p.width > area.x + area.width ||
          p.y + p.height > area.y + area.height
        )
          sheet.layoutWarnings.push(
            `${n.tag} lies outside the drawing area. Move it or reset layout.`,
          );
        const node = graph.nodes.get(n.id)!;
        const input = result.runs.find((r) => r.to.id === n.id && powerTypes.includes(r.type));
        const output = result.loading.find((l) => l.entityId === n.id && l.kind === 'psu');
        const dmx = result.patch.find((p) => p.entityId === n.id);
        const item = node.item;
        const attrs = {
          TAG: `${n.tag}${'qty' in node.entity && (node.entity.qty ?? 1) > 1 ? ` (x${node.entity.qty})` : ''}`,
          MODEL: item?.model ?? 'Panel / circuit',
          VIN: input
            ? `${input.voltageV.toFixed(0)} V${item?.category === 'dmx-0-10v-converter' ? (input.type === 'landscape-ac' || input.type.startsWith('lv-') ? ' AC' : ' DC') : ''} IN`
            : 'voltage' in node.entity
              ? `${node.entity.voltage} V`
              : '',
          VOUT: output
            ? `${item?.specs.kind === 'psu' || item?.specs.kind === 'driver' ? (item.specs.outputV ?? item.specs.outputmA ?? '') : ''} ${item?.specs.kind === 'driver' && item.specs.outputType === 'CC' ? 'mA' : 'V'} OUT`
            : item?.specs.kind === 'decoder' && input
              ? `${input.voltageV.toFixed(0)} V ${item.specs.powerType === 'AC' ? 'AC DIM' : 'DC PWM'} OUT`
              : item?.category === 'dmx-0-10v-converter'
                ? '0-10 V CTRL'
                : '',
          WATTS:
            result.loadWatts[n.id] !== undefined
              ? `${result.loadWatts[n.id]!.toFixed(1)} W`
              : output
                ? `${output.wattsW.toFixed(1)} W`
                : item?.category === 'dmx-0-10v-converter' && item.specs.kind === 'controller'
                  ? `${item.specs.ownPowerW.toFixed(1)} W / UNIT`
                  : '',
          LOAD_PCT: output ? `${output.percent.toFixed(1)}%` : '',
          DMX_ADDR: dmx
            ? `DMX U${dmx.universe} / ${dmx.startAddress ?? '?'}-${dmx.endAddress ?? '?'}${result.segments.some((s) => s.ends.includes(n.id)) ? (project.equipment.find((e) => e.id === n.id)?.dmx?.terminatorPresent ? ' / TERM' : ' / TERM REQ.') : ''}`
            : '',
          LOCATION:
            'location' in node.entity
              ? node.entity.location
              : 'zone' in node.entity
                ? node.entity.zone
                : '',
        };
        // The client diagram leaves out the electrical figures; the riser carries them.
        if (client)
          for (const tag of ['VIN', 'VOUT', 'WATTS', 'LOAD_PCT', 'DMX_ADDR'] as const)
            attrs[tag] = '';
        sheet.prims.push({
          kind: 'block',
          layer: n.symbol.prims[0]!.layer,
          symbolId: n.symbol.id,
          x: p.x,
          y: p.y,
          rotation: 0,
          scale: 1,
          entityId: n.id,
          attributes: attrs,
        });
        const extra = n.symbol.heightIn - SYMBOL_HEIGHT;
        if (item?.specs.kind === 'tape' && 'lengthFt' in node.entity) {
          const length =
            project.settings.units === 'm'
              ? (node.entity.lengthFt ?? 0) * 0.3048
              : (node.entity.lengthFt ?? 0);
          sheet.prims.push({
            ...text(
              `${length.toFixed(1)} ${project.settings.units} / ${attrs.LOCATION}`,
              p.x + 0.14,
              p.y + 0.56,
              3 / 32,
              'E-LITE-FIXT',
            ),
            entityId: n.id,
            role: 'annotation',
          });
        }
        sheet.prims.push({
          ...paragraph(
            item
              ? modelText({ id: n.id, item })
              : 'panel' in node.entity
                ? `${node.entity.panel} / circuit ${node.entity.circuit}`
                : '',
            p.x + 0.14,
            p.y + 0.99 + extra,
            p.width - 0.28,
          ),
          entityId: n.id,
          role: 'model',
        });
        sheet.nodes.push({ id: n.id, ...p, pinned: !!pin?.pinned });
        const issues = result.messages.filter((m) => m.entityRef === n.id && m.severity !== 'info');
        if (issues.length)
          sheet.prims.push({
            ...text(
              `${issues.some((m) => m.severity === 'error') ? 'ERROR' : 'VERIFY'} ${issues.length}`,
              p.x + p.width,
              p.y + p.height + 0.13,
              0.09375,
              'E-ANNO-QAFL',
              'bold',
            ),
            entityId: n.id,
            hAlign: 'right',
          });
      }

      for (let i = 0; i < sheet.nodes.length; i++)
        for (let j = i + 1; j < sheet.nodes.length; j++)
          if (intersects(sheet.nodes[i]!, sheet.nodes[j]!, 0.05))
            sheet.layoutWarnings.push(
              `Nodes ${sheet.nodes[i]!.id} and ${sheet.nodes[j]!.id} overlap.`,
            );
      const grouped = new Map<string, Bounds[]>();
      for (const n of prepared.nodes)
        if (n.enclosure)
          grouped.set(n.enclosure, [...(grouped.get(n.enclosure) ?? []), positions.get(n.id)!]);
      for (const [name, boxes] of grouped) {
        const minX = Math.min(...boxes.map((b) => b.x)) - ENCLOSURE_PAD,
          minY = Math.min(...boxes.map((b) => b.y)) - ENCLOSURE_PAD;
        const maxX = Math.max(...boxes.map((b) => b.x + b.width)) + ENCLOSURE_PAD,
          maxY = Math.max(...boxes.map((b) => b.y + b.height)) + ENCLOSURE_HEAD;
        const group = { x: minX, y: minY, width: maxX - minX, height: maxY - minY };
        const foreign = prepared.nodes.some(
          (n) => n.enclosure !== name && intersects(group, positions.get(n.id)!),
        );
        const rects = foreign
          ? boxes.map((b) => ({
              x: b.x - ENCLOSURE_PAD,
              y: b.y - ENCLOSURE_PAD,
              width: b.width + ENCLOSURE_PAD * 2,
              height: b.height + ENCLOSURE_PAD + ENCLOSURE_HEAD,
            }))
          : [group];
        for (const r of rects)
          sheet.prims.push(
            { kind: 'rect', ...r, layer: 'E-ANNO-ENCL' },
            text(
              `${name}${foreign || pages.some((page, i) => i !== pageIndex && page.nodes.some((n) => n.enclosure === name)) ? ' · continued' : ''}`,
              r.x + 0.06,
              r.y + r.height - 0.18,
              0.09375,
              'E-ANNO-ENCL',
            ),
          );
        if (foreign)
          sheet.layoutWarnings.push(
            `${name} enclosure outline split to avoid enclosing unrelated devices.`,
          );
      }
      drawConnections(
        sheet,
        project,
        library,
        result,
        positions,
        area,
        pageOf,
        continuationFor,
        layerForRun,
        prepared.denseMarkersFirst,
        { client, members: drawn.members },
      );
      return sheet;
    });
  }
  // Fitting equipment alone cannot guarantee enough cable lanes. If an automatic
  // page is too congested, subdivide it and rebuild every paired sheet reference.
  for (;;) {
    try {
      return renderPages();
    } catch (error) {
      const group = pages[renderingPage]!.nodes;
      if (
        !(error instanceof Error) ||
        !/no clear cable lane|no clear control label|No clear space for continuation/.test(
          error.message,
        ) ||
        group.length < 2 ||
        group.some((n) => project.layoutOverrides[n.id]?.pinned)
      )
        throw error;
      // Try reserving dense reference banks first, then wider row channels,
      // before introducing another sheet boundary.
      const current = pages[renderingPage]!;
      if (!current.denseMarkersFirst) {
        current.denseMarkersFirst = true;
        continue;
      }
      if (current.extraGap < 0.9) {
        const relaxed = await prepare(group, current.extraGap + 0.3);
        if (fits(relaxed)) {
          pages[renderingPage] = relaxed;
          continue;
        }
      }
      const before = pages.length;
      const atoms = enclosureGroups(group);
      const chunks = atoms.length > 1 ? atoms : group.map((n) => [n]);
      const middle = Math.ceil(chunks.length / 2);
      await split(chunks.slice(0, middle).flat(), 4);
      await split(chunks.slice(middle).flat(), 4);
      const subdivisions = pages.splice(before);
      pages.splice(renderingPage, 1, ...subdivisions);
    }
  }
}
