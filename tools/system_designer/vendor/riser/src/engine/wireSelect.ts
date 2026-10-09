import { AWG_SMALL_TO_LARGE, type AWG } from '../schemas/common';
import type { ProjectSettings, ValidationMessage, WireOverrideSchema } from '../schemas/project';
import type { WireType } from '../schemas/wire';
import type { CodeTable } from '../schemas/reference-data';
import type { z } from 'zod';
import { maximumLength, voltageDrop } from './voltageDrop';
import { message, round } from './messages';
import type { RunInput, RunResult, WireCandidate } from './model';

export const powerTypes = [
  'lv-branch',
  'lv-fixture-whip',
  'class2-dc',
  'class2-dc-multichannel',
  'landscape-ac',
];
export const awgSize = (awg: AWG) => AWG_SMALL_TO_LARGE.indexOf(awg);
export function environmentMatches(wire: WireType, environment: RunInput['env']): boolean {
  switch (environment) {
    case 'plenum':
      return wire.plenum;
    case 'riser':
      return wire.riser || wire.plenum;
    case 'wet':
      return wire.wet;
    case 'direct-burial':
      return wire.directBurial;
    case 'outdoor-exposed':
      return wire.sunlightResistant && wire.wet;
    case 'raceway':
      return true;
    case 'dry-concealed':
      return wire.category !== 'building-wire' && wire.category !== 'flex-cord';
  }
}
export function requiredConductors(run: RunInput, common = 1): RunInput['required'] {
  return {
    ...run.required,
    power: run.required.power + (run.type === 'class2-dc-multichannel' ? common - 1 : 0),
  };
}
export function constructionMatches(run: RunInput, wire: WireType, common = 1): boolean {
  if (!wire.applications.includes(run.type) || !environmentMatches(wire, run.env)) return false;
  if (run.type === 'wireless') return wire.conductors.length === 0;
  if (wire.ratedV < run.voltageV) return false;
  const required = requiredConductors(run, common);
  const count = (role: string) =>
    wire.conductors.filter((c) => c.role === role).reduce((sum, c) => sum + c.count, 0);
  const spareChannelsForCommon =
    run.type === 'class2-dc-multichannel' && common > 1
      ? Math.max(0, count('channel') - required.channel)
      : 0;
  return (
    count('power') + spareChannelsForCommon >= required.power &&
    count('ground') >= required.ground &&
    count('channel') >= required.channel &&
    count('signal') >= required.signal &&
    count('data-pair') >= required.dataPair
  );
}
function currentGroups(wire: WireType) {
  return wire.conductors.filter((c) => c.role === 'power' || c.role === 'channel');
}
export function wireResistance(
  wire: WireType,
  tables: CodeTable[],
  settings: ProjectSettings,
  ac = false,
): number | null {
  const groups = currentGroups(wire);
  const values = groups.map((c) => {
    if (ac && settings.acVdMethod === 'effective-z') {
      const table = tables.find(
        (t) =>
          t.kind === 'effective-z' &&
          t.source.edition === settings.necEdition &&
          t.status === 'available',
      );
      return table?.kind === 'effective-z' && c.material === 'Cu'
        ? table.rows.find((r) => r.awg === c.awg)?.effectiveZOhmPerKft
        : undefined;
    }
    if (c.resistanceOhmPerKft !== undefined) return c.resistanceOhmPerKft;
    if (wire.resistanceOhmPerKft !== undefined) return wire.resistanceOhmPerKft;
    const table = tables.find(
      (t) => t.kind === 'resistance' && t.source.edition === settings.necEdition,
    );
    const row =
      table?.kind === 'resistance' && c.material === 'Cu'
        ? table.rows.find((r) => r.awg === c.awg)
        : undefined;
    return c.stranding === 'solid' ? row?.solid : row?.stranded;
  });
  return values.length && values.every((v) => v !== undefined)
    ? Math.max(...(values as number[]))
    : null;
}
export function wireAmpacity(
  wire: WireType,
  tables: CodeTable[],
  settings: ProjectSettings,
): number | null {
  const groups = currentGroups(wire);
  const values = groups.map((c) => {
    if (c.ampacityA !== undefined) return c.ampacityA;
    if (wire.ampacityBasis !== '310.16' && wire.ampacityA !== undefined) return wire.ampacityA;
    if (c.material !== 'Cu') return undefined;
    const table = tables.find(
      (t) => t.kind === 'ampacity' && t.source.edition === settings.necEdition,
    );
    const row = table?.kind === 'ampacity' ? table.rows.find((r) => r.awg === c.awg) : undefined;
    if (wire.ampacityBasis === '310.16') {
      const temp = Math.min(
        settings.terminationTempC,
        wire.tempRatingC,
        wire.ampacityTempLimitC ?? 90,
      );
      return temp >= 90 ? row?.at90C : temp >= 75 ? row?.at75C : row?.at60C;
    }
    if (['class2-power', 'landscape'].includes(wire.category)) {
      const fixture = tables.find(
        (t) => t.kind === 'fixture-wire' && t.source.edition === settings.necEdition,
      );
      return fixture?.kind === 'fixture-wire'
        ? fixture.rows.find((r) => r.awg === c.awg)?.ampacityA
        : undefined;
    }
    return undefined;
  });
  return values.length && values.every((v) => v !== undefined)
    ? Math.min(...(values as number[]))
    : null;
}
export function targetDrop(run: RunInput, settings: ProjectSettings) {
  return run.type === 'landscape-ac'
    ? settings.vdTargetLandscapePct
    : run.type.startsWith('lv-')
      ? settings.vdTargetLineVoltagePct
      : settings.vdTargetLowVoltagePct;
}
export function evaluateWire(
  run: RunInput,
  wire: WireType,
  tables: CodeTable[],
  settings: ProjectSettings,
  parallelSets = 1,
  common = 1,
): WireCandidate {
  const groups = currentGroups(wire);
  const awg = [...groups].sort((a, b) => awgSize(a.awg) - awgSize(b.awg))[0]?.awg;
  const reasons: string[] = [];
  if (!constructionMatches(run, wire, common))
    reasons.push('Construction, voltage rating, application or environment does not match');
  const data = !powerTypes.includes(run.type);
  const terminalOk = groups.every((g) =>
    run.terminalMaxAwg.every((limit) => awgSize(g.awg) <= awgSize(limit)),
  );
  if (data)
    return {
      wireTypeId: wire.id,
      awg,
      eligible: reasons.length === 0,
      reasons,
      ampacityA: null,
      vdV: null,
      vdPct: null,
      endV: null,
      maxLengthFt: null,
      terminalOk,
    };
  const ampacityA = wireAmpacity(wire, tables, settings);
  const demand =
    (Math.max(
      run.currentA / (run.type === 'class2-dc-multichannel' ? common : 1),
      ...run.channelCurrentsA,
      0,
    ) /
      parallelSets) *
    settings.continuousLoadFactor;
  if (common > 1 && run.type !== 'class2-dc-multichannel')
    reasons.push('Common-conductor doubling applies only to multichannel DC runs');
  if (ampacityA === null) reasons.push('Ampacity data unavailable');
  else if (ampacityA + 1e-9 < demand)
    reasons.push(`Ampacity ${ampacityA} A < ${round(demand)} A required`);
  if (run.type.startsWith('lv-') && awg && awgSize(awg) < awgSize(settings.minAwgLineVoltage))
    reasons.push(`Below line-voltage minimum #${settings.minAwgLineVoltage}`);
  if (run.breakerA !== undefined && awg) {
    const table = tables.find(
      (t) => t.kind === 'ampacity' && t.source.edition === settings.necEdition,
    );
    const row = table?.kind === 'ampacity' ? table.rows.find((r) => r.awg === awg) : undefined;
    if (!row) reasons.push('OCPD reference data unavailable');
    else if (
      row.smallConductorOcpdLimitA !== undefined &&
      run.breakerA > row.smallConductorOcpdLimitA
    )
      reasons.push(
        `Breaker exceeds #${awg} small-conductor OCPD limit ${row.smallConductorOcpdLimitA} A`,
      );
    else if (ampacityA !== null && run.breakerA > ampacityA)
      reasons.push('Breaker exceeds conductor ampacity');
  }
  const resistance = wireResistance(
    wire,
    tables,
    settings,
    run.type.startsWith('lv-') || run.type === 'landscape-ac',
  );
  const vdV =
    resistance === null
      ? null
      : voltageDrop(run, resistance, parallelSets, common, settings.vdMethod);
  const vdPct = vdV !== null && run.voltageV > 0 ? (vdV / run.voltageV) * 100 : null;
  if (resistance === null) reasons.push('Resistance/effective-impedance data unavailable');
  else if (vdPct !== null && vdPct > targetDrop(run, settings) + 1e-9)
    reasons.push(`Voltage drop exceeds ${targetDrop(run, settings)}% target`);
  return {
    wireTypeId: wire.id,
    awg,
    eligible: reasons.length === 0,
    reasons,
    ampacityA,
    vdV,
    vdPct,
    endV: vdV === null ? null : run.voltageV - vdV,
    maxLengthFt:
      resistance === null
        ? null
        : maximumLength(run, resistance, targetDrop(run, settings), parallelSets, common),
    terminalOk,
  };
}
export function selectWire(
  run: RunInput,
  tag: string,
  wires: WireType[],
  tables: CodeTable[],
  settings: ProjectSettings,
  override?: z.infer<typeof WireOverrideSchema>,
): RunResult {
  const sets = override?.parallelSets ?? 1;
  const common = override?.parallelCommonConductors ?? 1;
  const messages: ValidationMessage[] = [];
  const matching = wires.filter((w) => constructionMatches(run, w, common));
  const candidates = matching.map((w) => evaluateWire(run, w, tables, settings, sets, common));
  const ranked = candidates
    .filter((c) => c.eligible)
    .sort(
      (a, b) =>
        (a.awg ? awgSize(a.awg) : 0) - (b.awg ? awgSize(b.awg) : 0) ||
        (wires.find((w) => w.id === a.wireTypeId)?.costPerFt ?? Infinity) -
          (wires.find((w) => w.id === b.wireTypeId)?.costPerFt ?? Infinity),
    );
  const chosenWire = override
    ? wires.find((w) => w.id === override.wireTypeId)
    : wires.find((w) => w.id === ranked[0]?.wireTypeId);
  const chosen = chosenWire
    ? evaluateWire(run, chosenWire, tables, settings, sets, common)
    : undefined;
  if (override && chosen && !candidates.some((c) => c.wireTypeId === chosen.wireTypeId))
    candidates.push(chosen);
  if (!chosen) {
    messages.push(
      message(
        'NO_VALID_WIRE',
        'error',
        run.entityRef,
        `${tag}: no wire passes construction, environment, ampacity and voltage-drop requirements.`,
      ),
    );
    const maximum = Math.max(0, ...candidates.map((c) => c.maxLengthFt ?? 0));
    if (maximum > 0)
      messages.push(
        message(
          'MAX_LENGTH_HINT',
          'info',
          run.entityRef,
          `Longest target-compliant candidate feed is ${round(maximum, 1)} ft.`,
        ),
      );
  } else {
    for (const reason of chosen.reasons)
      messages.push(
        message(
          reason.startsWith('Voltage drop') ? 'VD_OVER_TARGET' : 'NO_VALID_WIRE',
          reason.startsWith('Voltage drop') ? 'warning' : 'error',
          run.entityRef,
          `${tag}: ${reason}.`,
        ),
      );
    if (!chosen.terminalOk) {
      const terminal = [...run.terminalMaxAwg].sort((a, b) => awgSize(a) - awgSize(b))[0];
      const lengths = candidates.filter((c) => c.awg === terminal).map((c) => c.maxLengthFt ?? 0);
      messages.push(
        message(
          'TERMINAL_OVERSIZE',
          'warning',
          run.entityRef,
          `${tag}: #${chosen.awg} exceeds an endpoint's #${terminal} terminal. Maximum #${terminal} length at ${targetDrop(run, settings)}% is ${round(Math.max(0, ...lengths), 1)} ft. Move the supply closer or use a listed distribution block/pigtail; any parallel arrangement requires review.`,
        ),
      );
    }
    if (chosenWire?.verify)
      messages.push(
        message(
          'WIRE_REQUIRES_VERIFICATION',
          'warning',
          run.entityRef,
          `${tag}: verify ${chosenWire.riserLabel} ratings, listings and installation conditions before use.`,
        ),
      );
    if (
      run.minOperatingV !== undefined &&
      chosen.endV !== null &&
      chosen.endV + 1e-9 < run.minOperatingV
    )
      messages.push(
        message(
          'TAPE_UNDERVOLTAGE',
          'error',
          run.entityRef,
          `${tag}: ${round(chosen.endV)} V at load is below ${run.minOperatingV} V minimum.`,
        ),
      );
  }
  if (sets > 1 || common > 1)
    messages.push(
      message(
        'PARALLEL_REVIEW_REQUIRED',
        'warning',
        run.entityRef,
        `${tag}: parallel sets/common conductors are a manual override; verify termination, listing, sharing and applicable conductor rules.`,
      ),
    );
  if (
    powerTypes.includes(run.type) &&
    (chosen
      ? chosen.reasons.some((r) => r.includes('data unavailable'))
      : candidates.some((c) => c.reasons.some((r) => r.includes('data unavailable'))))
  )
    messages.push(
      message(
        'CODE_TABLE_UNAVAILABLE',
        'error',
        run.entityRef,
        `${tag}: required ${settings.necEdition} reference or manufacturer data is unavailable. Incomplete candidates are excluded.`,
      ),
    );
  if (!powerTypes.includes(run.type)) {
    const limits = [
      run.type === 'ethernet' ? 328 : run.type === 'spi-data' ? settings.spiMaxDataFt : undefined,
      run.maxDataLengthFt,
    ].filter((n): n is number => n !== undefined);
    const limit = limits.length ? Math.min(...limits) : undefined;
    if (limit !== undefined && run.lengthFt > limit)
      messages.push(
        message(
          run.type === 'spi-data' ? 'SPI_DATA_LENGTH' : 'DATA_LENGTH',
          'warning',
          run.entityRef,
          `${tag}: ${run.lengthFt} ft exceeds the ${limit} ft link limit. ${run.type === 'spi-data' ? 'Use a compatible differential transmitter/receiver.' : 'Revise the link or follow device-specific instructions.'}`,
        ),
      );
  }
  return {
    ...run,
    tag,
    wireTypeId: chosen?.wireTypeId ?? null,
    parallelSets: sets,
    parallelCommonConductors: common,
    overridden: !!override,
    vdV: chosen?.vdV ?? null,
    vdPct: chosen?.vdPct ?? null,
    endV: chosen?.endV ?? null,
    ampacityA: chosen?.ampacityA ?? null,
    checks: {
      ampacity:
        chosen && powerTypes.includes(run.type)
          ? !chosen.reasons.some((r) => /[Aa]mpacity|OCPD|Breaker/.test(r))
          : null,
      terminal: chosen?.terminalOk ?? null,
      voltageDrop:
        chosen?.vdPct === null || chosen?.vdPct === undefined
          ? null
          : chosen.vdPct <= targetDrop(run, settings) + 1e-9,
    },
    candidates,
    messages,
  };
}
