import type { LibrarySnapshot } from '../schemas/library';
import type { Project, Equipment, Load, ValidationMessage } from '../schemas/project';
import type { Protocol, RunType, AWG } from '../schemas/common';
import { buildGraph, type Edge, type GraphNode } from './graph';
import { loadProfile, inputCurrent, suggestedFeeds } from './loads';
import { selectWire } from './wireSelect';
import { dmxSegments, patchDmx } from './dmx';
import { buildBom } from './bom';
import { message, round, uniqueMessages } from './messages';
import { EngineResultSchema, type EngineResult, type Loading, type RunInput } from './model';
import { supportedProtocols, inputVoltageRange } from './ports';

export function controlRunType(protocol: Protocol): RunType {
  switch (protocol) {
    case 'CRMX-wireless':
      return 'wireless';
    case 'sACN':
    case 'Art-Net':
      return 'ethernet';
    case 'SPI':
      return 'spi-data';
    case '0-10V':
    case '1-10V':
      return '0-10v';
    case 'DALI-2':
      return 'dali';
    case 'Lutron-QS':
      return 'lutron-qs';
    case 'Lutron-EcoSystem':
      return 'lutron-ecosystem';
    default:
      return 'dmx';
  }
}
export function assignWireTags(
  runs: RunInput[],
  saved: Record<string, string>,
): Record<string, string> {
  const tags = { ...saved };
  const used = new Set(Object.values(tags));
  let n = 1;
  for (const run of [...runs].sort(
    (a, b) =>
      a.from.tag.localeCompare(b.from.tag) ||
      a.to.tag.localeCompare(b.to.tag) ||
      a.runId.localeCompare(b.runId),
  )) {
    if (tags[run.runId]) continue;
    while (used.has(`W-${String(n).padStart(2, '0')}`)) n++;
    const tag = `W-${String(n++).padStart(2, '0')}`;
    tags[run.runId] = tag;
    used.add(tag);
  }
  return tags;
}
export function calculate(project: Project, library: LibrarySnapshot): EngineResult {
  const graph = buildGraph(project, library.products);
  const messages: ValidationMessage[] = [...graph.messages];
  const invalidConverterFeeds = graph.power.filter(
    (e) => graph.nodes.get(e.from)?.item?.category === 'dmx-0-10v-converter',
  );
  for (const edge of invalidConverterFeeds)
    messages.push(
      message(
        'INVALID_PORT',
        'error',
        edge.entityRef,
        'A DMX to 0–10 V converter provides control signals only. Give the fixture or driver its own power feed and connect a 0–10 V Control Link.',
      ),
    );
  // A saved/imported project can reference a draft even though the picker excludes it.
  // Do not size upstream cables or show zero-load capacity results for an unknown demand.
  if (
    invalidConverterFeeds.length ||
    [...graph.nodes.values()].some((n) => n.item?.specs.kind === 'incomplete')
  )
    return EngineResultSchema.parse({
      runs: [],
      loading: [],
      patch: [],
      segments: [],
      messages: uniqueMessages(messages),
      bom: [],
      wireTagMap: project.wireTagMap,
      loadWatts: {},
      splits: [],
    });
  const loading: Loading[] = [];
  const inputs: RunInput[] = [];
  const splits: EngineResult['splits'] = [];
  const children = (id: string) => graph.power.filter((e) => e.from === id);
  const parent = (id: string) => graph.power.find((e) => e.to === id);
  function outputVoltage(id: string, seen = new Set<string>()): number {
    if (seen.has(id)) return 0;
    seen.add(id);
    const node = graph.nodes.get(id);
    if (!node) return 0;
    if (node.kind === 'source') return 'voltage' in node.entity ? node.entity.voltage : 0;
    const spec = node.item?.specs;
    if (spec?.kind === 'psu' || spec?.kind === 'driver')
      return spec.outputType === 'CV' ? (spec.outputV ?? 0) : (spec.outputVMax ?? 0);
    const upstream = parent(id);
    return upstream ? outputVoltage(upstream.from, seen) : 0;
  }
  function rootSource(id: string, seen = new Set<string>()): GraphNode | undefined {
    if (seen.has(id)) return;
    seen.add(id);
    const node = graph.nodes.get(id);
    if (node?.kind === 'source') return node;
    const edge = parent(id);
    return edge ? rootSource(edge.from, seen) : undefined;
  }
  function currentType(id: string, seen = new Set<string>()): 'AC' | 'DC' | undefined {
    if (seen.has(id)) return;
    seen.add(id);
    const n = graph.nodes.get(id);
    if (n?.kind === 'source') return 'AC';
    const s = n?.item?.specs;
    if (s?.kind === 'psu' || s?.kind === 'driver') return s.outputCurrent ?? 'DC';
    if (s?.kind === 'decoder') return s.powerType;
    const edge = parent(id);
    return edge ? currentType(edge.from, seen) : undefined;
  }
  function outputPhase(id: string, seen = new Set<string>()): '1PH' | '3PH' {
    if (seen.has(id)) return '1PH';
    seen.add(id);
    const n = graph.nodes.get(id);
    if (n?.kind === 'source' && 'phase' in n.entity) return n.entity.phase;
    const s = n?.item?.specs;
    if (s?.kind === 'psu' || s?.kind === 'driver' || s?.kind === 'decoder') return '1PH';
    const edge = parent(id);
    return edge ? outputPhase(edge.from, seen) : '1PH';
  }
  const demands = new Map<string, { watts: number; amps: number; channels: number[] }>();
  function demand(
    id: string,
    stack = new Set<string>(),
  ): { watts: number; amps: number; channels: number[] } {
    if (demands.has(id)) return demands.get(id)!;
    if (stack.has(id)) return { watts: 0, amps: 0, channels: [] };
    stack.add(id);
    const node = graph.nodes.get(id)!;
    const spec = node.item?.specs;
    const edge = parent(id);
    const voltage = edge ? outputVoltage(edge.from) : outputVoltage(id);
    let watts: number;
    let amps: number;
    let channels: number[] = [];
    if (node.kind === 'load' && spec) {
      const profile = loadProfile(node.entity as Load, spec, project.settings);
      watts = profile.watts;
      channels = profile.channelAmps;
      amps =
        spec.kind === 'fixture' && spec.drive === 'CC'
          ? profile.current
          : voltage > 0
            ? watts / voltage
            : profile.current;
      if (spec.kind === 'fixture' && spec.drive !== 'CC') {
        if (spec.maxInputA !== undefined && spec.maxInputAAtV === voltage)
          amps = spec.maxInputA * ((node.entity as Load).qty ?? 1);
        else amps /= (spec.powerFactor ?? 1) * (spec.inputPhase === '3PH' ? Math.sqrt(3) : 1);
      }
    } else {
      const descendants = children(id).map((e) => demand(e.to, new Set(stack)));
      const outputW = descendants.reduce((sum, d) => sum + d.watts, 0);
      const qty = 'qty' in node.entity ? (node.entity.qty ?? 1) : 1;
      if (spec?.kind === 'psu' || spec?.kind === 'driver') {
        watts = outputW / spec.efficiency;
        amps = inputCurrent(outputW, voltage, spec, qty);
      } else if (spec?.kind === 'controller') {
        const supplyType = edge ? currentType(edge.from) : undefined;
        const ac = supplyType === 'AC';
        watts = outputW + spec.ownPowerW * qty;
        amps =
          descendants.reduce((sum, d) => sum + d.amps, 0) +
          (voltage > 0
            ? (spec.ownPowerW * qty) /
              (voltage *
                (ac ? (spec.powerFactor ?? 1) * (spec.inputPhase === '3PH' ? Math.sqrt(3) : 1) : 1))
            : 0);
        if (
          spec.maxInputA !== undefined &&
          spec.maxInputAAtV === voltage &&
          (spec.inputType !== 'AC/DC' || spec.maxInputAType === supplyType)
        )
          amps = Math.max(amps, spec.maxInputA * qty);
      } else {
        watts = outputW;
        amps = descendants.reduce((sum, d) => sum + d.amps, 0);
      }
    }
    const result = { watts, amps, channels };
    demands.set(id, result);
    return result;
  }
  for (const id of graph.nodes.keys()) demand(id);
  function terminal(node: GraphNode): AWG[] {
    const spec = node.item?.specs;
    return spec && 'terminalMaxAwg' in spec && spec.terminalMaxAwg ? [spec.terminalMaxAwg] : [];
  }
  function validateFeed(edge: Edge) {
    const upstream = graph.nodes.get(edge.from)!;
    const down = graph.nodes.get(edge.to)!;
    const spec = down.item?.specs;
    const source = upstream.item?.specs;
    const voltage = outputVoltage(edge.from);
    if (upstream.kind === 'load')
      messages.push(
        message(
          'INVALID_PORT',
          'error',
          down.id,
          'A load cannot serve as an upstream power source.',
        ),
      );
    if (!spec) return;
    if (spec.kind === 'accessory') {
      if (spec.ratedV !== undefined && voltage > spec.ratedV)
        messages.push(
          message(
            'VOLTAGE_MISMATCH',
            'error',
            down.id,
            `${down.tag}: ${voltage} V exceeds the accessory rating of ${spec.ratedV} V.`,
          ),
        );
      if (spec.ratedA !== undefined && demand(down.id).amps > spec.ratedA)
        messages.push(
          message(
            'DEVICE_CAPACITY',
            'error',
            down.id,
            `${down.tag}: connected current exceeds the accessory rating of ${spec.ratedA} A.`,
          ),
        );
    }
    const ac = currentType(upstream.id) === 'AC';
    const expected =
      'inputType' in spec
        ? spec.inputType
        : spec.kind === 'tape'
          ? 'DC'
          : spec.kind === 'decoder'
            ? spec.powerType
            : spec.kind === 'fixture' && spec.voltageClass === 'line'
              ? 'AC'
              : undefined;
    if (expected && expected !== 'AC/DC' && expected !== (ac ? 'AC' : 'DC'))
      messages.push(
        message(
          'DRIVE_MISMATCH',
          'error',
          down.id,
          `${down.tag} requires ${expected} input; the connected supply is ${ac ? 'AC' : 'DC'}.`,
        ),
      );
    if (
      ac &&
      outputPhase(upstream.id) === '3PH' &&
      spec.kind !== 'accessory' &&
      (!('inputPhase' in spec) || spec.inputPhase !== '3PH')
    )
      messages.push(
        message(
          'INVALID_SPEC',
          'error',
          down.id,
          'Three-phase feeding requires a verified 3PH input rating. Model individual line-to-neutral or line-to-line branches as 1PH circuits at their actual voltage.',
        ),
      );
    if (
      ac &&
      (spec.kind === 'fixture' || spec.kind === 'controller') &&
      (spec.maxInputA === undefined ||
        spec.maxInputAAtV !== voltage ||
        (spec.kind === 'controller' &&
          spec.inputType === 'AC/DC' &&
          spec.maxInputAType !== 'AC')) &&
      spec.powerFactor === undefined
    )
      messages.push(
        message(
          'INPUT_CURRENT_ESTIMATED',
          'warning',
          down.id,
          'AC input current uses a unity-power-factor estimate. Supply manufacturer maximum input current at this voltage or a verified power factor before final conductor sizing.',
        ),
      );
    const inputRange = inputVoltageRange(spec, ac ? 'AC' : 'DC');
    if (inputRange && (voltage < inputRange[0] || voltage > inputRange[1]))
      messages.push(
        message(
          'INPUT_V_OUT_OF_RANGE',
          'error',
          down.id,
          `${down.tag}: ${voltage} V supply is outside ${inputRange[0]}–${inputRange[1]} V ${ac ? 'AC' : 'DC'} input range.`,
        ),
      );
    if (spec.kind === 'tape' && voltage !== spec.voltage)
      messages.push(
        message(
          'VOLTAGE_MISMATCH',
          'error',
          down.id,
          `${down.tag}: ${spec.voltage} V tape is supplied from ${voltage} V.`,
        ),
      );
    if (spec.kind === 'fixture') {
      const range = Array.isArray(spec.inputV) ? spec.inputV : [spec.inputV, spec.inputV];
      if (spec.drive !== 'CC' && (voltage < range[0]! || voltage > range[1]!))
        messages.push(
          message(
            'VOLTAGE_MISMATCH',
            'error',
            down.id,
            `${down.tag}: ${voltage} V is outside the fixture input range.`,
          ),
        );
    }
    if (source?.kind === 'decoder' && source.powerType === 'AC' && spec.kind === 'fixture') {
      if (spec.voltageClass !== 'line')
        messages.push(
          message(
            'DRIVE_MISMATCH',
            'error',
            down.id,
            `${down.tag}: a line-voltage fixture is required on ${upstream.tag}'s AC output.`,
          ),
        );
      if (!source.outputDimming || !spec.dimming.includes(source.outputDimming))
        messages.push(
          message(
            'DRIVE_MISMATCH',
            'error',
            down.id,
            `${down.tag}: verify the fixture supports ${source.outputDimming ?? 'the configured'} primary-side dimming from ${upstream.tag}.`,
          ),
        );
    }
    if (source?.kind === 'psu' || source?.kind === 'driver') {
      if (source.outputs.length > 1 && !edge.fromPort)
        messages.push(
          message('INVALID_PORT', 'error', down.id, `Select a named output of ${upstream.tag}.`),
        );
      if (edge.fromPort && !source.outputs.some((o) => o.name === edge.fromPort))
        messages.push(
          message(
            'INVALID_PORT',
            'error',
            down.id,
            `Unknown output ${edge.fromPort} on ${upstream.tag}.`,
          ),
        );
      const ccLoad = spec.kind === 'fixture' && spec.drive === 'CC';
      if ((source.outputType === 'CC') !== ccLoad)
        messages.push(
          message(
            'DRIVE_MISMATCH',
            'error',
            down.id,
            `${upstream.tag} ${source.outputType} output is incompatible with ${down.tag}.`,
          ),
        );
      if (ccLoad && source.outputmA !== spec.mA)
        messages.push(
          message(
            'DRIVE_MISMATCH',
            'error',
            down.id,
            `Driver ${source.outputmA} mA does not match fixture ${spec.mA} mA.`,
          ),
        );
      if (ccLoad && source.outputmA) {
        const requiredV = demand(down.id).watts / (source.outputmA / 1000);
        if (requiredV < (source.outputVMin ?? 0) || requiredV > (source.outputVMax ?? 0))
          messages.push(
            message(
              'CC_COMPLIANCE',
              'error',
              down.id,
              `Series fixture load needs ${round(requiredV)} V, outside driver compliance range.`,
            ),
          );
      }
    } else if (spec.kind === 'fixture' && spec.drive === 'CC')
      messages.push(
        message(
          'DRIVE_MISMATCH',
          'error',
          down.id,
          'CC fixtures require a matching constant-current driver.',
        ),
      );
    if (spec.kind === 'psu' || spec.kind === 'driver') {
      const inputIsAc = ac;
      if (spec.inputType === 'AC' && !inputIsAc)
        messages.push(
          message(
            'DRIVE_MISMATCH',
            'error',
            down.id,
            'AC input supply is connected to a DC output.',
          ),
        );
      if (spec.inputType === 'DC' && ac)
        messages.push(
          message(
            'DRIVE_MISMATCH',
            'error',
            down.id,
            'DC input supply is connected to an AC circuit.',
          ),
        );
      if (spec.maxInputA === undefined || spec.maxInputAAtV !== voltage)
        messages.push(
          message(
            'INPUT_CURRENT_ESTIMATED',
            'warning',
            down.id,
            `Input current calculated from connected load, efficiency and power factor at ${voltage} V; no matching manufacturer maximum-current rating is available.`,
          ),
        );
    }
    if (
      upstream.kind === 'source' &&
      'switching' in upstream.entity &&
      upstream.entity.switching?.startsWith('phase')
    ) {
      if (!('dimming' in spec) || !spec.dimming.includes(upstream.entity.switching as Protocol))
        messages.push(
          message(
            'PHASE_DIMMER_COMPAT_UNKNOWN',
            'warning',
            down.id,
            'Verify phase-dimmer and driver compatibility, minimum load, and inrush.',
          ),
        );
    }
  }
  graph.power.forEach(validateFeed);
  for (const eq of project.equipment) {
    const node = graph.nodes.get(eq.id)!;
    const spec = node.item?.specs;
    if (!spec) continue;
    if (node.item?.category === 'dmx-0-10v-converter' && !eq.dmx)
      messages.push(
        message(
          'INVALID_SPEC',
          'error',
          eq.id,
          `${eq.tag}: enter a DMX universe and start address, or select automatic addressing.`,
        ),
      );
    if (eq.qty > 1)
      messages.push(
        message(
          'QTY_DISTRIBUTION',
          'warning',
          eq.id,
          `${eq.tag} represents ${eq.qty} units. Verify identical load allocation and individual output protection; output ratings below remain per unit.`,
        ),
      );
    if (spec.kind === 'psu' || spec.kind === 'driver') {
      const total = children(eq.id).reduce((sum, e) => sum + demand(e.to).watts, 0);
      if (total > spec.ratedW)
        messages.push(
          message(
            'PSU_OVERLOAD',
            'error',
            eq.id,
            `${eq.tag}: ${round(total)} W exceeds ${spec.ratedW} W rated output.`,
          ),
        );
      for (const output of spec.outputs) {
        const connected = children(eq.id).filter(
          (e) => e.fromPort === output.name || (!e.fromPort && output === spec.outputs[0]),
        );
        const watts = connected.reduce((sum, e) => sum + demand(e.to).watts, 0);
        if (spec.outputType === 'CC' && connected.length > 1)
          messages.push(
            message(
              'INVALID_SPEC',
              'error',
              eq.id,
              `${eq.tag}/${output.name}: multiple parallel CC branches are not supported. Model the series fixture string as one quantity row or use separately rated driver outputs.`,
            ),
          );
        const percent = (watts / output.maxW) * 100;
        loading.push({
          entityId: eq.id,
          tag: eq.tag,
          kind: 'psu',
          port: output.name,
          wattsW: watts,
          currentA:
            spec.outputType === 'CC'
              ? connected.length
                ? (spec.outputmA ?? 0) / 1000
                : 0
              : outputVoltage(eq.id)
                ? watts / outputVoltage(eq.id)
                : 0,
          capacity: output.maxW,
          percent,
          units: 'W',
          count: eq.qty,
        });
        if (percent > 100)
          messages.push(
            message(
              'PSU_OVERLOAD',
              'error',
              eq.id,
              `${eq.tag}/${output.name}: ${round(watts)} W exceeds ${output.maxW} W output limit.`,
            ),
          );
        else if (percent > project.settings.psuDeratePct)
          messages.push(
            message(
              'PSU_ABOVE_DERATE',
              'warning',
              eq.id,
              `${eq.tag}/${output.name}: ${round(percent, 1)}% exceeds the ${project.settings.psuDeratePct}% project operating target.`,
            ),
          );
        if (output.class2 && watts > 100)
          messages.push(
            message(
              'CLASS2_OVER_100VA',
              'warning',
              eq.id,
              `${eq.tag}/${output.name}: Class 2 output load exceeds 100 VA; verify listing and output limits.`,
            ),
          );
      }
    }
    if (spec.kind === 'decoder') {
      const channels = Array<number>(spec.channels).fill(0);
      const channelWatts = Array<number>(spec.channels).fill(0);
      let total = 0;
      let totalWatts = 0;
      for (const edge of children(eq.id)) {
        const d = demand(edge.to);
        total +=
          spec.powerType === 'AC'
            ? d.amps
            : outputVoltage(eq.id)
              ? d.watts / outputVoltage(eq.id)
              : 0;
        totalWatts += d.watts;
        const match = edge.fromPort?.match(/^CH(\d+)(?:-(\d+))?$/);
        const start = match ? Number(match[1]) - 1 : 0;
        if (
          !match ||
          start < 0 ||
          start + Math.max(1, d.channels.length) > spec.channels ||
          (match[2] && Number(match[2]) - start !== d.channels.length)
        )
          messages.push(
            message(
              'INVALID_PORT',
              'error',
              edge.to,
              `Choose a channel or channel range matching the load on ${eq.tag}.`,
            ),
          );
        (d.channels.length ? d.channels : [d.amps]).forEach((amps, i) => {
          if (start + i < channels.length && start >= 0) {
            channels[start + i]! += amps;
            channelWatts[start + i]! +=
              d.channels.length > 0 ? amps * outputVoltage(eq.id) : d.watts;
          }
        });
      }
      channels.forEach((amps, i) => {
        loading.push({
          entityId: eq.id,
          tag: eq.tag,
          kind: 'decoder',
          port: `CH${i + 1}`,
          wattsW: channelWatts[i]!,
          currentA: amps,
          capacity: spec.maxAPerChannel,
          percent: (amps / spec.maxAPerChannel) * 100,
          units: 'A',
          count: eq.qty,
        });
        if (amps > spec.maxAPerChannel)
          messages.push(
            message(
              'CHANNEL_OVERCURRENT',
              'error',
              eq.id,
              `${eq.tag}/CH${i + 1}: ${round(amps)} A exceeds ${spec.maxAPerChannel} A.`,
            ),
          );
        if (spec.maxWPerChannel !== undefined && channelWatts[i]! > spec.maxWPerChannel)
          messages.push(
            message(
              'CHANNEL_OVERCURRENT',
              'error',
              eq.id,
              `${eq.tag}/CH${i + 1}: ${round(channelWatts[i]!)} W exceeds ${spec.maxWPerChannel} W.`,
            ),
          );
      });
      if (total > spec.maxATotal)
        messages.push(
          message(
            'CHANNEL_OVERCURRENT',
            'error',
            eq.id,
            `${eq.tag}: common total ${round(total)} A exceeds ${spec.maxATotal} A.`,
          ),
        );
      if (spec.maxWTotal !== undefined && totalWatts > spec.maxWTotal)
        messages.push(
          message(
            'CHANNEL_OVERCURRENT',
            'error',
            eq.id,
            `${eq.tag}: ${round(totalWatts)} W exceeds ${spec.maxWTotal} W total output limit.`,
          ),
        );
    }
  }
  for (const source of project.sources) {
    if (source.phase === '3PH' && source.poles !== 3)
      messages.push(
        message('INVALID_SPEC', 'error', source.id, 'A three-phase circuit requires three poles.'),
      );
    const amps = demand(source.id).amps;
    const watts = demand(source.id).watts;
    const supplies = project.equipment.filter(
      (e) => rootSource(e.id)?.id === source.id && ['psu', 'driver'].includes(e.category),
    );
    const count = supplies.reduce((sum, e) => sum + e.qty, 0);
    loading.push({
      entityId: source.id,
      tag: source.tag,
      kind: 'circuit',
      port: source.circuit,
      currentA: amps,
      wattsW: watts,
      capacity: source.breakerA,
      percent: (amps / source.breakerA) * 100,
      units: 'A',
      count,
    });
    if (amps * project.settings.continuousLoadFactor > source.breakerA)
      messages.push(
        message(
          'BREAKER_OVERLOAD',
          'error',
          source.id,
          `${source.tag}: ${round(amps)} A × ${project.settings.continuousLoadFactor} = ${round(amps * project.settings.continuousLoadFactor)} A exceeds ${source.breakerA} A.`,
        ),
      );
    else if ((amps / source.breakerA) * 100 > project.settings.breakerLoadLimitPct)
      messages.push(
        message(
          'BREAKER_OVERLOAD',
          'warning',
          source.id,
          `${source.tag}: operating load exceeds ${project.settings.breakerLoadLimitPct}% breaker target.`,
        ),
      );
    if (source.breakerA === 20)
      for (const eq of supplies) {
        const spec = graph.nodes.get(eq.id)?.item?.specs;
        if (
          spec &&
          'maxUnitsPer20ABreaker' in spec &&
          spec.maxUnitsPer20ABreaker !== undefined &&
          count > spec.maxUnitsPer20ABreaker
        )
          messages.push(
            message(
              'INRUSH_LIMIT',
              'warning',
              source.id,
              `${count} supplies exceeds ${eq.tag}'s ${spec.maxUnitsPer20ABreaker}-unit limit on a 20 A breaker. Verify mixed-device inrush.`,
            ),
          );
      }
  }
  function baseRun(edge: Edge): RunInput {
    const from = graph.nodes.get(edge.from)!;
    const to = graph.nodes.get(edge.to)!;
    const d = demand(to.id);
    const volts = outputVoltage(from.id);
    const low =
      from.item?.specs.kind === 'psu' || from.item?.specs.kind === 'driver' || volts <= 60;
    const source = rootSource(from.id);
    const sourceEntity = source?.entity;
    const phase = !low ? outputPhase(from.id) : '1PH';
    return {
      runId: edge.id,
      type: low
        ? currentType(from.id) === 'AC'
          ? 'landscape-ac'
          : d.channels.length > 1
            ? 'class2-dc-multichannel'
            : 'class2-dc'
        : from.kind === 'source'
          ? 'lv-branch'
          : from.item?.specs.kind === 'decoder' && from.item.specs.powerType === 'AC'
            ? 'lv-branch'
            : to.kind === 'load'
              ? 'lv-fixture-whip'
              : 'lv-branch',
      from: { id: from.id, tag: from.tag, port: edge.fromPort },
      to: { id: to.id, tag: to.tag, port: edge.toPort },
      entityRef: edge.entityRef,
      lengthFt: edge.lengthFt,
      currentA: d.amps,
      wattsW: d.watts,
      voltageV: volts,
      channelCurrentsA: d.channels,
      phase,
      env: edge.env,
      breakerA:
        !low && sourceEntity && 'breakerA' in sourceEntity ? sourceEntity.breakerA : undefined,
      terminalMaxAwg: [...terminal(from), ...terminal(to)],
      required: {
        power: phase === '3PH' ? 3 : d.channels.length > 1 && low ? 1 : 2,
        channel: d.channels.length > 1 && low ? d.channels.length : 0,
        ground: low ? 0 : 1,
        signal: 0,
        dataPair: 0,
      },
    };
  }
  const grouped = new Map<string, Edge[]>();
  for (const edge of graph.power) {
    const from = graph.nodes.get(edge.from)!;
    const to = graph.nodes.get(edge.to)!;
    if (from.kind === 'source' && to.kind === 'equipment') {
      const eq = to.entity as Equipment;
      const key = `${from.id}|${eq.location}|${eq.env}`;
      grouped.set(key, [...(grouped.get(key) ?? []), edge]);
    }
  }
  const physical = new Map<string, { from: string; amps: number; watts: number }>();
  for (const group of grouped.values())
    group.forEach((edge, index) => {
      const tail = group.slice(index);
      physical.set(edge.id, {
        from: index ? group[index - 1]!.to : edge.from,
        amps: tail.reduce((sum, e) => sum + demand(e.to).amps, 0),
        watts: tail.reduce((sum, e) => sum + demand(e.to).watts, 0),
      });
    });
  for (const edge of graph.power) {
    const node = graph.nodes.get(edge.to)!;
    const run = baseRun(edge);
    const shared = physical.get(edge.id);
    if (shared) {
      const from = graph.nodes.get(shared.from)!;
      run.from = {
        id: from.id,
        tag: from.tag,
        port: shared.from === edge.from ? edge.fromPort : 'AC-THRU',
      };
      run.currentA = shared.amps;
      run.wattsW = shared.watts;
    }
    if (node.kind === 'load') {
      const load = node.entity as Load;
      const spec = node.item?.specs;
      if (spec?.kind === 'tape') {
        run.minOperatingV = spec.minOperatingV;
        const limit =
          load.feedMethod === 'end'
            ? spec.maxRunFtSingleFeed
            : load.feedMethod === 'multi-feed'
              ? spec.maxRunFtSingleFeed * (load.feeds ?? 1)
              : spec.maxRunFtDoubleFeed;
        if ((load.lengthFt ?? 0) > limit) {
          const feeds = suggestedFeeds(load.lengthFt ?? 0, spec.maxRunFtSingleFeed);
          splits.push({ loadId: load.id, feeds });
          messages.push(
            message(
              'TAPE_RUN_TOO_LONG',
              'warning',
              load.id,
              `${load.typeTag}: ${load.lengthFt} ft exceeds ${limit} ft for ${load.feedMethod} feed.`,
            ),
            message(
              'SUGGEST_SPLIT_FEED',
              'info',
              load.id,
              `Use at least ${feeds} feed sections and verify tape segment lengths.`,
            ),
          );
        }
      }
      const qty = load.qty ?? 1;
      const inter = load.interFixtureLengthFt ?? 0;
      if (qty > 1) {
        run.lengthFt += (qty - 1) * inter;
        if (!(spec?.kind === 'fixture' && spec.drive === 'CC'))
          run.distributed = { qty, homeRunFt: load.homeRunLengthFt, interFixtureFt: inter };
      }
      const cc = spec?.kind === 'fixture' && spec.drive === 'CC';
      if (cc && load.feedMethod !== 'end')
        messages.push(
          message(
            'INVALID_SPEC',
            'error',
            load.id,
            'A CC series string uses one driver feed; split/center feed methods are not supported for CC fixtures.',
          ),
        );
      const feeds = cc
        ? 1
        : load.feedMethod === 'double-end'
          ? 2
          : load.feedMethod === 'multi-feed'
            ? (load.feeds ?? 1)
            : 1;
      for (let i = 0; i < feeds; i++)
        inputs.push({
          ...run,
          runId: feeds > 1 ? `${edge.id}:feed${i + 1}` : edge.id,
          currentA: run.currentA / feeds,
          wattsW: run.wattsW / feeds,
          channelCurrentsA: run.channelCurrentsA.map((a) => a / feeds),
        });
    } else {
      inputs.push(run);
      const qty = 'qty' in node.entity ? (node.entity.qty ?? 1) : 1;
      for (let i = 1; i < qty; i++)
        inputs.push({
          ...run,
          runId: `${edge.id}:jumper${i + 1}`,
          from: { id: node.id, tag: node.tag, port: `UNIT${i}` },
          to: { id: node.id, tag: node.tag, port: `UNIT${i + 1}` },
          currentA: (demand(node.id).amps * (qty - i)) / qty,
          wattsW: (demand(node.id).watts * (qty - i)) / qty,
        });
    }
  }
  for (const edge of graph.control) {
    const from = graph.nodes.get(edge.from)!;
    const to = graph.nodes.get(edge.to)!;
    const protocol = edge.protocol ?? 'DMX512';
    const type = controlRunType(protocol);
    if (
      !supportedProtocols(from.item?.specs, 'out').includes(protocol) ||
      !supportedProtocols(to.item?.specs, 'in').includes(protocol)
    )
      messages.push(
        message(
          'PROTOCOL_MISMATCH',
          'error',
          edge.entityRef,
          `${from.tag} → ${to.tag}: verify ${protocol} source and receiver compatibility.`,
        ),
      );
    for (const [node, port, direction] of [
      [from, edge.fromPort, 'out'],
      [to, edge.toPort, 'in'],
    ] as const) {
      const spec = node.item?.specs;
      if (node.item?.category === 'dmx-0-10v-converter' && !port && direction === 'out')
        messages.push(
          message(
            'INVALID_PORT',
            'error',
            edge.entityRef,
            `${node.tag}: select the named output port for this control link.`,
          ),
        );
      if (
        spec?.kind === 'controller' &&
        port &&
        !spec.ports.some(
          (p) =>
            p.name === port &&
            (p.direction === direction || p.direction === 'bidirectional') &&
            p.protocol === protocol,
        )
      )
        messages.push(
          message(
            'INVALID_PORT',
            'error',
            edge.entityRef,
            `${node.tag}/${port} is not a matching ${protocol} ${direction} port.`,
          ),
        );
    }
    const caps = [from.item?.specs, to.item?.specs].flatMap((s) =>
      s?.kind === 'controller' && s.maxDataLengthFt ? [s.maxDataLengthFt] : [],
    );
    const required = {
      power: type === 'lutron-qs' || type === 'dali' || type === 'lutron-ecosystem' ? 2 : 0,
      ground: type === 'spi-data' ? 1 : 0,
      signal: type === 'spi-data' ? 1 : type === '0-10v' ? 2 : 0,
      dataPair: ['dmx', 'ethernet', 'lutron-qs'].includes(type) ? (type === 'ethernet' ? 8 : 2) : 0,
      channel: 0,
    };
    inputs.push({
      runId: edge.id,
      type,
      protocol,
      from: { id: from.id, tag: from.tag, port: edge.fromPort },
      to: { id: to.id, tag: to.tag, port: edge.toPort },
      entityRef: edge.entityRef,
      lengthFt: type === 'wireless' ? 0 : edge.lengthFt,
      currentA: 0,
      wattsW: 0,
      voltageV: 0,
      channelCurrentsA: [],
      phase: '1PH',
      env: edge.env,
      terminalMaxAwg: [],
      required,
      maxDataLengthFt: caps.length ? Math.min(...caps) : undefined,
    });
  }
  const wireTagMap = assignWireTags(inputs, project.wireTagMap);
  const runs = inputs
    .map((r) =>
      selectWire(
        r,
        wireTagMap[r.runId]!,
        library.wires,
        library.codeTables,
        project.settings,
        project.wireOverrides[r.runId],
      ),
    )
    .sort((a, b) => a.tag.localeCompare(b.tag, undefined, { numeric: true }));
  const dmx = patchDmx(project, graph);
  const segments = dmxSegments(project, graph);
  for (const node of graph.nodes.values()) {
    const spec = node.item?.specs;
    if (spec?.kind !== 'controller') continue;
    for (const port of spec.ports.filter(
      (p) => p.direction !== 'in' && p.maxDevices !== undefined,
    )) {
      const receiverIds = new Set(
        graph.control
          .filter(
            (e) => e.from === node.id && e.fromPort === port.name && e.protocol === port.protocol,
          )
          .map((e) => e.to),
      );
      const count = [...receiverIds].reduce((sum, id) => {
        const receiver = graph.nodes.get(id)!;
        return sum + ('qty' in receiver.entity ? (receiver.entity.qty ?? 1) : 1);
      }, 0);
      if (count > port.maxDevices!)
        messages.push(
          message(
            'DEVICE_CAPACITY',
            'error',
            node.id,
            `${node.tag}/${port.name}: ${count} controlled devices exceeds the verified limit of ${port.maxDevices}.`,
          ),
        );
    }
    const reachable = new Set<string>();
    const universes = new Set<number>();
    function visit(id: string) {
      for (const edge of graph.control.filter((e) => e.from === id)) {
        if (edge.universe) universes.add(edge.universe);
        if (reachable.has(edge.to) || edge.to === node.id) continue;
        reachable.add(edge.to);
        const receiver = graph.nodes.get(edge.to)!;
        if ('dmx' in receiver.entity && receiver.entity.dmx)
          universes.add(receiver.entity.dmx.universe);
        visit(edge.to);
      }
    }
    visit(node.id);
    const pixels = [...reachable].reduce((sum, id) => {
      const target = graph.nodes.get(id)!;
      const s = target.item?.specs;
      return (
        sum +
        (s?.kind === 'tape' && s.pixel && 'lengthFt' in target.entity
          ? Math.ceil(
              (target.entity.lengthFt ?? 0) *
                (1 + project.settings.tapeLengthMarginPct / 100) *
                s.pixel.pixelsPerFt,
            )
          : 0)
      );
    }, 0);
    for (const [actual, limit, label] of [
      [pixels, spec.maxPixels, 'pixels'],
      [universes.size, spec.maxUniverses, 'universes'],
      [reachable.size, spec.maxBusDevices, 'downstream devices'],
    ] as const)
      if (limit !== undefined && actual > limit)
        messages.push(
          message(
            'DEVICE_CAPACITY',
            'error',
            node.id,
            `${node.tag}: ${actual} ${label} exceeds the verified device limit of ${limit}.`,
          ),
        );
  }
  messages.push(...runs.flatMap((r) => r.messages), ...dmx.messages, ...segments.messages);
  for (const load of project.loads) {
    const node = graph.nodes.get(load.id)!;
    const spec = node.item?.specs;
    const edge = parent(load.id);
    const upstream = edge ? graph.nodes.get(edge.from)?.item?.specs : undefined;
    if (
      spec?.kind === 'fixture' &&
      spec.drive === 'CC' &&
      upstream &&
      (upstream.kind === 'driver' || upstream.kind === 'psu') &&
      upstream.outputmA
    ) {
      const needed = demand(load.id).watts / (upstream.outputmA / 1000);
      for (const run of runs.filter((r) => r.entityRef === load.id && r.vdV !== null))
        if (needed + run.vdV! > (upstream.outputVMax ?? 0))
          messages.push(
            message(
              'CC_COMPLIANCE',
              'error',
              load.id,
              `Fixture voltage ${round(needed)} V plus cable drop ${round(run.vdV!)} V exceeds driver compliance.`,
            ),
          );
    }
  }
  return EngineResultSchema.parse({
    runs,
    loading,
    patch: dmx.patch,
    segments: segments.segments,
    messages: uniqueMessages(messages),
    bom: buildBom(project, library.products, library.wires, runs, segments.segments),
    wireTagMap,
    loadWatts: Object.fromEntries(project.loads.map((l) => [l.id, demand(l.id).watts])),
    splits,
  });
}
