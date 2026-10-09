import type { CatalogSpecs } from '../schemas/catalog';
import type { Load, ProjectSettings } from '../schemas/project';

export function loadProfile(
  load: Load,
  spec: CatalogSpecs,
  settings: ProjectSettings,
): { watts: number; channelAmps: number[]; voltage: number; current: number } {
  if (spec.kind === 'incomplete')
    throw new Error('Complete product specifications before calculating loads');
  if (spec.kind === 'tape') {
    const length = (load.lengthFt ?? 0) * (1 + settings.tapeLengthMarginPct / 100);
    const rated = spec.wPerFtMax * length;
    const watts = spec.pixel
      ? Math.ceil(length * spec.pixel.pixelsPerFt) * spec.pixel.ampsPerPixelMax * spec.voltage
      : rated *
        (spec.powerBasis === 'max-operating' ? 1 : spec.maxSimultaneousPct / (spec.channels * 100));
    const channelAmps = (
      spec.channelWPerFtMax ??
      Array.from({ length: spec.channels }, () => spec.wPerFtMax / spec.channels)
    ).map((w) => (w * length) / spec.voltage);
    return {
      watts,
      channelAmps: spec.pixel ? [] : channelAmps,
      voltage: spec.voltage,
      current: watts / spec.voltage,
    };
  }
  if (spec.kind === 'fixture') {
    const watts = spec.watts * (load.qty ?? 0);
    const voltage = Array.isArray(spec.inputV) ? spec.inputV[0] : spec.inputV;
    return {
      watts,
      channelAmps: [],
      voltage,
      current: spec.drive === 'CC' ? (spec.mA ?? 0) / 1000 : watts / voltage,
    };
  }
  return { watts: 0, channelAmps: [], voltage: 0, current: 0 };
}
export function inputCurrent(watts: number, voltage: number, spec: CatalogSpecs, qty = 1): number {
  if (spec.kind === 'incomplete')
    throw new Error('Complete product specifications before calculating current');
  if (!(voltage > 0)) return 0;
  if (spec.kind === 'psu' || spec.kind === 'driver')
    return spec.maxInputA !== undefined && spec.maxInputAAtV === voltage
      ? spec.maxInputA * qty
      : watts /
          spec.efficiency /
          (voltage *
            (spec.inputType === 'AC'
              ? spec.powerFactor * (spec.inputPhase === '3PH' ? Math.sqrt(3) : 1)
              : 1));
  return watts / voltage;
}
export function suggestedFeeds(lengthFt: number, singleLimit: number): number {
  return Math.max(2, Math.ceil(lengthFt / singleLimit));
}
