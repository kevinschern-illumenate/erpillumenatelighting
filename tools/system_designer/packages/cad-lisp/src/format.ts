/**
 * Number formatting with Python's semantics, which `mini_lisp.py` uses for `rtos` and `princ`.
 *
 * Python's `f"{x:.{p}f}"` rounds the exact binary value half to even. `Number.prototype.toFixed` also
 * works on the exact value but breaks exact ties away from zero, and drops the sign of negative zero.
 * Exact ties are detected from the 100-digit expansion (a tie's expansion terminates at digit p + 1).
 */

export function formatFixed(x: number, digits: number): string {
  if (Number.isNaN(x)) return 'nan';
  if (!Number.isFinite(x)) return x > 0 ? 'inf' : '-inf';
  const negative = x < 0 || Object.is(x, -0);
  const magnitude = Math.abs(x);
  let text = magnitude.toFixed(digits);
  if (magnitude < 1e21 && digits < 100) {
    const exact = magnitude.toFixed(100);
    const dot = exact.indexOf('.');
    const fraction = exact.slice(dot + 1);
    if (fraction[digits] === '5' && /^0*$/.test(fraction.slice(digits + 1))) {
      const kept = digits === 0 ? exact.slice(0, dot) : exact.slice(0, dot + 1 + digits);
      const last = kept[kept.length - 1]!;
      if ((last.charCodeAt(0) - 48) % 2 === 0) text = kept;
    }
  }
  return negative ? `-${text}` : text;
}

/** Python `repr(float)` for the values the toolkit prints (`str(2.0)` is `2.0`). */
export function pyFloatRepr(x: number): string {
  if (Number.isNaN(x)) return 'nan';
  if (!Number.isFinite(x)) return x > 0 ? 'inf' : '-inf';
  if (Number.isInteger(x) && Math.abs(x) < 1e16) return `${Object.is(x, -0) ? '-' : ''}${Math.abs(x)}.0`;
  return String(x);
}
