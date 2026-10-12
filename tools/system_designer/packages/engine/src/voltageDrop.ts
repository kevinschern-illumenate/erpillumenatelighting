import type { RunInput } from './model';

export function voltageDrop(
  run: RunInput,
  resistance: number,
  parallelSets = 1,
  commonConductors = 1,
  method: 'lumped-at-end' | 'distributed' = 'lumped-at-end',
): number {
  const factor = run.phase === '3PH' ? Math.sqrt(3) : 2;
  const current = run.currentA / parallelSets;
  if (run.type === 'class2-dc-multichannel')
    return (
      (run.lengthFt *
        resistance *
        (current / commonConductors + Math.max(0, ...run.channelCurrentsA) / parallelSets)) /
      1000
    );
  const distributed = run.distributed;
  if (method === 'distributed' && distributed && distributed.qty > 1) {
    const ampFeet =
      current * distributed.homeRunFt +
      ((current / distributed.qty) *
        distributed.interFixtureFt *
        distributed.qty *
        (distributed.qty - 1)) /
        2;
    return (factor * ampFeet * resistance) / 1000;
  }
  return (factor * run.lengthFt * current * resistance) / 1000;
}
export function maximumLength(
  run: RunInput,
  resistance: number,
  targetPct: number,
  parallelSets = 1,
  commonConductors = 1,
): number | null {
  const perFoot = voltageDrop(
    { ...run, lengthFt: 1, distributed: undefined },
    resistance,
    parallelSets,
    commonConductors,
  );
  return perFoot > 0 ? (run.voltageV * targetPct) / 100 / perFoot : null;
}
