import { roundNumber } from '@ill/core-schemas/hash';
import type { Design } from '@ill/core-schemas/design';
import type { DesignCheck } from './designCheck';
import { reviewTriggers, type ReviewGate, type ReviewTrigger } from './power';

/**
 * The gating subset the server re-checks in Python (plan §18.2, WP-3.6): supply and output loading,
 * Class 2, run length, voltage drop and wire selection on single-channel Class 2 DC runs, voltage match,
 * dealer data and the D4 triggers. `system_design/verify.py` computes the same shape; the golden
 * fixtures hold both sides to it.
 */

export const VERIFY_CODES = [
  'PSU_OVERLOAD',
  'PSU_ABOVE_DERATE',
  'CLASS2_OVER_100VA',
  'TAPE_RUN_TOO_LONG',
  'VOLTAGE_MISMATCH',
  'VD_OVER_TARGET',
  'NO_VALID_WIRE',
  'TAPE_UNDERVOLTAGE',
  'DATA_BY_DEALER',
] as const;
/** Wire checks the mirror computes only for single-channel Class 2 DC runs. */
const WIRE_CODES = new Set(['VD_OVER_TARGET', 'NO_VALID_WIRE', 'TAPE_UNDERVOLTAGE']);
const VERIFIED_RUN_TYPE = 'class2-dc';

export interface VerifySubset {
  loading: { entityId: string; port: string; wattsW: number }[];
  runs: Record<string, { wireTypeId: string | null; vdPct: number | null }>;
  /** `CODE|entityRef`, sorted and unique. */
  messages: string[];
  review: ReviewTrigger[];
}

// Code-unit order, the same as Python's `sorted`.
const order = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);
const round = (value: number | null) => (value === null ? null : (roundNumber(value) as number));

export function verifySubset(design: Design, check: DesignCheck, gate?: ReviewGate): VerifySubset {
  const { result } = check;
  const loading = result.loading
    .filter((row) => row.kind === 'psu')
    .map((row) => ({ entityId: row.entityId, port: row.port, wattsW: round(row.wattsW)! }))
    .sort((a, b) => order(a.entityId, b.entityId) || order(a.port, b.port));
  const runs: VerifySubset['runs'] = {};
  const typesByRef = new Map<string, Set<string>>();
  for (const run of result.runs) {
    typesByRef.set(run.entityRef, new Set([...(typesByRef.get(run.entityRef) ?? []), run.type]));
    if (run.type === VERIFIED_RUN_TYPE) runs[run.runId] = { wireTypeId: run.wireTypeId, vdPct: round(run.vdPct) };
  }
  const verified = (ref: string) => {
    const types = typesByRef.get(ref);
    return Boolean(types && types.size === 1 && types.has(VERIFIED_RUN_TYPE));
  };
  const codes = new Set<string>(VERIFY_CODES);
  const messages = [
    ...new Set(
      check.messages
        .filter((item) => codes.has(item.code) && (!WIRE_CODES.has(item.code) || verified(item.entityRef)))
        .map((item) => `${item.code}|${item.entityRef}`),
    ),
  ].sort();
  return { loading, runs, messages, review: reviewTriggers(design, gate) };
}
