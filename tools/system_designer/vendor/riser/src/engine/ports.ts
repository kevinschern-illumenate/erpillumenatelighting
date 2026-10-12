import type { Project } from '../schemas/project';
import type { CatalogItem, CatalogSpecs } from '../schemas/catalog';
import { buildGraph } from './graph';
import type { Protocol } from '../schemas/common';

export function inputVoltageRange(
  spec: CatalogSpecs,
  current: 'AC' | 'DC',
): [number, number] | undefined {
  if (!('inputVMin' in spec)) return undefined;
  if (spec.kind === 'controller' && spec.inputType === 'AC/DC') {
    const min = current === 'AC' ? spec.acInputVMin : spec.dcInputVMin;
    const max = current === 'AC' ? spec.acInputVMax : spec.dcInputVMax;
    if (min !== undefined && max !== undefined) return [min, max];
  }
  return [spec.inputVMin, spec.inputVMax];
}

export function supportedProtocols(
  spec: CatalogSpecs | undefined,
  direction: 'in' | 'out',
): Protocol[] {
  if (!spec) return [];
  if (direction === 'out' && spec.kind === 'decoder') {
    const wired = (p: Protocol) => p === 'DMX512' || p === 'RDM';
    return [
      ...new Set([
        ...(spec.protocolOut ?? []).filter((p) => !wired(p)),
        ...(spec.dmxThru ? spec.protocolIn.filter(wired) : []),
      ]),
    ];
  }
  if (direction === 'in' && 'protocolIn' in spec) return spec.protocolIn;
  if (direction === 'out' && 'protocolOut' in spec) return spec.protocolOut ?? [];
  if (direction === 'in' && 'dimming' in spec) return spec.dimming;
  if (direction === 'in' && spec.kind === 'tape' && spec.pixel) return ['SPI'];
  return [];
}

export function controlPortOptions(
  project: Project,
  products: CatalogItem[],
  direction: 'in' | 'out',
  protocol?: Protocol,
  targetId?: string,
) {
  const graph = buildGraph(project, products);
  const target = targetId ? graph.nodes.get(graph.resolve(targetId) ?? targetId) : undefined;
  const accepted = protocol
    ? [protocol]
    : target
      ? supportedProtocols(target.item?.specs, direction === 'out' ? 'in' : 'out')
      : [];
  const excluded = new Set<string>();
  function exclude(id: string) {
    if (excluded.has(id)) return;
    excluded.add(id);
    for (const edge of graph.control) {
      if (direction === 'out' && edge.from === id) exclude(edge.to);
      if (direction === 'in' && edge.to === id) exclude(edge.from);
    }
  }
  if (target) exclude(target.id);
  return [...graph.nodes.values()].flatMap((node) => {
    if (excluded.has(node.id)) return [];
    const spec = node.item?.specs;
    const protocols = supportedProtocols(spec, direction).filter(
      (p) => p !== 'none' && (!accepted.length || accepted.includes(p)),
    );
    if (!protocols.length) return [];
    if (spec?.kind === 'decoder') {
      const wired = protocols.filter((p) => p === 'DMX512' || p === 'RDM');
      const other = protocols.filter((p) => p !== 'DMX512' && p !== 'RDM');
      return [
        ...(wired.length
          ? [
              {
                value: `${node.tag}::DATA-${direction === 'out' ? 'OUT' : 'IN'}`,
                label: `${node.tag} / ${direction === 'out' ? 'DMX THRU (daisy chain)' : 'DMX IN'} · ${wired.join(', ')}`,
              },
            ]
          : []),
        ...(other.length ? [{ value: node.tag, label: `${node.tag} · ${other.join(', ')}` }] : []),
      ];
    }
    if (spec?.kind === 'controller')
      return spec.ports
        .filter(
          (p) =>
            (p.direction === direction || p.direction === 'bidirectional') &&
            protocols.includes(p.protocol),
        )
        .map((p) => ({
          value: `${node.tag}::${p.name}`,
          label: `${node.tag} / ${p.name} · ${p.protocol}`,
        }));
    const detail =
      node.kind === 'load'
        ? [
            'zone' in node.entity ? node.entity.zone : '',
            node.item?.model,
            project.loads.filter((l) => l.typeTag === node.tag).length > 1
              ? `load row ${project.loads.findIndex((l) => l.id === node.id) + 1}`
              : '',
          ]
            .filter(Boolean)
            .join(' · ')
        : '';
    return [
      {
        value: node.kind === 'load' ? node.id : node.tag,
        label: `${node.tag}${direction === 'in' && protocols.some((p) => p === '0-10V' || p === '1-10V') ? ' / DIM IN' : ''} · ${protocols.join(', ')}${detail ? ` · ${detail}` : ''}`,
      },
    ];
  });
}

export function powerPortOptions(
  project: Project,
  products: CatalogItem[],
  targetId: string,
): { value: string; label: string }[] {
  const graph = buildGraph(project, products);
  const target = graph.nodes.get(targetId);
  const spec = target?.item?.specs;
  if (spec?.kind === 'incomplete') return [];
  const excluded = new Set<string>([targetId]);
  function visit(id: string) {
    for (const edge of graph.power.filter((e) => e.from === id))
      if (!excluded.has(edge.to)) {
        excluded.add(edge.to);
        visit(edge.to);
      }
  }
  visit(targetId);
  function volts(id: string, seen = new Set<string>()): number | undefined {
    if (seen.has(id)) return;
    seen.add(id);
    const n = graph.nodes.get(id);
    if (!n) return;
    if ('voltage' in n.entity) return n.entity.voltage;
    const s = n.item?.specs;
    if (s?.kind === 'psu' || s?.kind === 'driver') return s.outputV ?? s.outputVMax;
    const parent = graph.power.find((e) => e.to === id);
    return parent ? volts(parent.from, seen) : undefined;
  }
  function compatible(
    voltage: number | undefined,
    upstream: CatalogSpecs | undefined,
    ac: boolean,
  ) {
    if (!spec) return true;
    const cc =
      upstream &&
      (upstream.kind === 'driver' || upstream.kind === 'psu') &&
      upstream.outputType === 'CC';
    if (spec.kind === 'fixture' && spec.drive === 'CC')
      return !!cc && upstream.outputmA === spec.mA;
    if (cc) return false;
    if (
      'inputType' in spec &&
      spec.inputType &&
      spec.inputType !== 'AC/DC' &&
      (spec.inputType === 'AC') !== ac
    )
      return false;
    if (spec.kind === 'fixture' && spec.voltageClass === 'line' && !ac) return false;
    if (spec.kind === 'tape') return !ac && voltage === spec.voltage;
    if (spec.kind === 'decoder' && (spec.powerType === 'AC') !== ac) return false;
    if (
      upstream?.kind === 'decoder' &&
      upstream.powerType === 'AC' &&
      spec.kind === 'fixture' &&
      (spec.voltageClass !== 'line' ||
        !upstream.outputDimming ||
        !spec.dimming.includes(upstream.outputDimming))
    )
      return false;
    const range = inputVoltageRange(spec, ac ? 'AC' : 'DC');
    if (range) return voltage !== undefined && voltage >= range[0] && voltage <= range[1];
    if (spec.kind === 'fixture') {
      const bounds = Array.isArray(spec.inputV) ? spec.inputV : [spec.inputV, spec.inputV];
      return voltage !== undefined && voltage >= bounds[0]! && voltage <= bounds[1]!;
    }
    return true;
  }
  const options: { value: string; label: string }[] = [];
  function isAc(id: string, seen = new Set<string>()): boolean {
    if (seen.has(id)) return false;
    seen.add(id);
    const n = graph.nodes.get(id);
    if (n?.kind === 'source') return true;
    const s = n?.item?.specs;
    if (s?.kind === 'psu' || s?.kind === 'driver') return s.outputCurrent === 'AC';
    if (s?.kind === 'decoder') return s.powerType === 'AC';
    const edge = graph.power.find((e) => e.to === id);
    return edge ? isAc(edge.from, seen) : false;
  }
  for (const node of graph.nodes.values()) {
    if (excluded.has(node.id) || node.kind === 'load') continue;
    const s = node.item?.specs;
    if (s?.kind === 'incomplete') continue;
    const ac = isAc(node.id);
    if (!compatible(volts(node.id), s, ac)) continue;
    let ports: string[] = [''];
    if (s?.kind === 'psu' || s?.kind === 'driver') ports = s.outputs.map((o) => o.name);
    else if (s?.kind === 'decoder') {
      const channels = spec?.kind === 'tape' ? spec.channels : 1;
      ports = Array.from({ length: Math.max(0, s.channels - channels + 1) }, (_, i) =>
        channels > 1 ? `CH${i + 1}-${i + channels}` : `CH${i + 1}`,
      );
    } else if (
      node.kind === 'equipment' &&
      s?.kind !== 'accessory' &&
      !['relay', '0-10v-dimmer'].includes(node.item?.category ?? '')
    )
      continue;
    for (const port of ports)
      options.push({
        value: `${node.tag}${port ? `::${port}` : ''}`,
        label: `${node.tag}${port ? ` / ${port}` : ''} · ${volts(node.id) ?? '?'} V`,
      });
  }
  return options;
}
export function parsePort(value: string) {
  const [ref = '', port] = value.split('::');
  return { ref, ...(port ? { port } : {}) };
}
