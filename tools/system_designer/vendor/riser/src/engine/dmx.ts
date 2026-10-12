import type { Project, ValidationMessage } from '../schemas/project';
import type { Graph, Edge } from './graph';
import type { DmxPatch, DmxSegment } from './model';
import { message } from './messages';

export function patchDmx(
  project: Project,
  graph: Graph,
): { patch: DmxPatch[]; messages: ValidationMessage[] } {
  const messages: ValidationMessage[] = [];
  const patch: DmxPatch[] = [];
  const ordered = [...project.equipment]
    .filter((e) => e.dmx)
    .sort(
      (a, b) =>
        (a.chainOrder ?? Infinity) - (b.chainOrder ?? Infinity) || a.tag.localeCompare(b.tag),
    );
  const occupied = new Map<number, Map<number, string>>();
  const footprint = (id: string) => {
    const s = graph.nodes.get(id)?.item?.specs;
    return s && 'dmxFootprint' in s ? (s.dmxFootprint ?? 0) : 0;
  };
  for (const e of ordered.filter((e) => typeof e.dmx!.startAddress === 'number')) {
    const d = e.dmx!;
    const start = d.startAddress as number;
    const count = footprint(e.id);
    const cells = occupied.get(d.universe) ?? new Map<number, string>();
    occupied.set(d.universe, cells);
    if (start + count - 1 > 512)
      messages.push(
        message(
          'DMX_ADDRESS_OVERFLOW',
          'error',
          e.id,
          `${e.tag}: address ${start} + footprint ${count} exceeds 512.`,
        ),
      );
    for (let address = start; address < start + count && address <= 512; address++) {
      if (cells.has(address))
        messages.push(
          message(
            'DMX_ADDRESS_OVERLAP',
            'error',
            e.id,
            `${e.tag} overlaps ${cells.get(address)} in universe ${d.universe} at ${address}.`,
          ),
        );
      cells.set(address, e.tag);
    }
  }
  for (const e of ordered) {
    const d = e.dmx!;
    const count = footprint(e.id);
    let start: number | null = d.startAddress === 'auto' ? 1 : d.startAddress;
    if (d.startAddress === 'auto') {
      const cells = occupied.get(d.universe) ?? new Map<number, string>();
      occupied.set(d.universe, cells);
      const step = project.settings.dmxAutoPatchRoundTo;
      while (
        start + count - 1 <= 512 &&
        Array.from({ length: count }, (_, i) => cells.has(start! + i)).some(Boolean)
      )
        start += step;
      if (start + count - 1 > 512) {
        messages.push(
          message(
            'DMX_ADDRESS_OVERFLOW',
            'error',
            e.id,
            `${e.tag}: no ${count}-address space remains in universe ${d.universe}.`,
          ),
        );
        start = null;
      } else for (let i = 0; i < count; i++) cells.set(start + i, e.tag);
    }
    patch.push({
      entityId: e.id,
      tag: e.tag,
      universe: d.universe,
      startAddress: start,
      footprint: count,
      endAddress: start === null ? null : start + count - 1,
      auto: d.startAddress === 'auto',
    });
  }
  return { patch, messages };
}
export function dmxSegments(
  project: Project,
  graph: Graph,
): { segments: DmxSegment[]; messages: ValidationMessage[] } {
  const edges = graph.control.filter((e) => ['DMX512', 'RDM'].includes(e.protocol ?? ''));
  const messages: ValidationMessage[] = [];
  const segments: DmxSegment[] = [];
  for (const id of new Set(edges.map((e) => e.to))) {
    const inputs = edges.filter((e) => e.to === id);
    if (inputs.length > 1)
      messages.push(
        message(
          'DMX_TOPOLOGY',
          'error',
          id,
          `${graph.nodes.get(id)?.tag}: multiple incoming DMX links. A daisy-chain receiver must have one upstream device.`,
        ),
      );
  }
  const resets = (id: string) => {
    const n = graph.nodes.get(id);
    const s = n?.item?.specs;
    return s?.kind === 'controller' && s.startsNewSegment;
  };
  const roots = edges.filter((e) => resets(e.from) || !edges.some((i) => i.to === e.from));
  const rootGroups = new Map<string, Edge[]>();
  for (const edge of roots) {
    const key = `${edge.from}:${resets(edge.from) ? (edge.fromPort ?? 'OUT') : 'BUS'}`;
    rootGroups.set(key, [...(rootGroups.get(key) ?? []), edge]);
  }
  for (const [key, initial] of rootGroups) {
    const visited = new Set<string>();
    const members = new Set<string>();
    const ends = new Set<string>();
    let lengthFt = 0;
    function walk(edge: Edge) {
      if (visited.has(edge.id)) return;
      visited.add(edge.id);
      members.add(edge.to);
      lengthFt += edge.lengthFt;
      const outgoing = resets(edge.to) ? [] : edges.filter((e) => e.from === edge.to);
      if (!outgoing.length) ends.add(edge.to);
      if (outgoing.length > 1)
        messages.push(
          message(
            'DMX_TOPOLOGY',
            'warning',
            edge.to,
            'Wired DMX branches without a segment-resetting opto-splitter. Use daisy-chain wiring or an opto-splitter.',
          ),
        );
      outgoing.forEach(walk);
    }
    if (initial.length > 1)
      messages.push(
        message(
          'DMX_TOPOLOGY',
          'warning',
          initial[0]!.from,
          'Multiple wired DMX branches share one source port. Use separate isolated outputs.',
        ),
      );
    initial.forEach(walk);
    const unitLoads = [...members].reduce((sum, id) => {
      const node = graph.nodes.get(id)!;
      const spec = node.item?.specs;
      return (
        sum +
        (spec && 'unitLoad' in spec ? (spec.unitLoad ?? 1) : 1) *
          ('qty' in node.entity ? (node.entity.qty ?? 1) : 1)
      );
    }, 0);
    const root = initial[0]!.from;
    if (unitLoads > project.settings.dmxMaxUnitLoads)
      messages.push(
        message(
          'DMX_UNIT_LOADS',
          'warning',
          root,
          `${unitLoads} unit loads exceeds ${project.settings.dmxMaxUnitLoads} on wired segment ${key}. Add an opto-splitter.`,
        ),
      );
    if (lengthFt > project.settings.dmxMaxLengthFt)
      messages.push(
        message(
          'DMX_LENGTH',
          'warning',
          root,
          `${lengthFt} ft exceeds ${project.settings.dmxMaxLengthFt} on wired segment ${key}. Split the physical segment.`,
        ),
      );
    for (const id of ends) {
      const equipment = project.equipment.find((e) => e.id === id);
      if (equipment?.dmx?.terminatorPresent !== true)
        messages.push(
          message(
            'DMX_NO_TERMINATOR',
            'warning',
            id,
            `Provide and verify the terminator at ${graph.nodes.get(id)?.tag}, the end of wired DMX segment ${key}.`,
          ),
        );
    }
    const universes = new Set(
      [...members]
        .map((id) => project.equipment.find((e) => e.id === id)?.dmx?.universe)
        .filter((u) => u !== undefined),
    );
    if (universes.size > 1)
      messages.push(
        message(
          'DMX_TOPOLOGY',
          'error',
          root,
          'One physical DMX segment contains receivers assigned to different universes.',
        ),
      );
    segments.push({ id: key, root, members: [...members], ends: [...ends], lengthFt, unitLoads });
  }
  for (const e of project.equipment.filter((e) => e.dmx))
    if (!edges.some((link) => link.to === e.id))
      messages.push(
        message(
          'DMX_TOPOLOGY',
          'warning',
          e.id,
          `${e.tag} has a DMX address but no resolved wired DMX input link.`,
        ),
      );
  return { segments, messages };
}
