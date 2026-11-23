/**
 * AutoLISP values for the browser interpreter (W-0.1 spike; port of `tools/cad_toolkit/test/mini_lisp.py`).
 *
 * Lists are cons cells, as in AutoLISP: `cons` and `cdr` are O(1). (The Python reference uses arrays,
 * which makes every `(setq acc (cons x acc))` loop quadratic; the toolkit's JSON writer is one, and at
 * 200 runs it took 1.7 s on arrays.) `nil` is `null`; a dotted pair is a `Cons` whose cdr is an atom.
 * Symbols are interned per interpreter and carry their global value slot (shallow binding), special
 * form and builtin, so evaluation needs no map lookups.
 *
 * AutoLISP distinguishes integers from reals (`(/ 7 2)` is 3, `itoa`, `type`), which JS numbers cannot.
 * One of the two must be boxed; `Numbers` hides which, so the spike can measure both.
 */

export const UNBOUND: unique symbol = Symbol('unbound');

/** Builtins take their arguments as one array (`apply 'strcat` on 100k pieces would overflow a spread). */
export type Native = (args: Value[]) => Value;

export class Sym {
  value: Value | typeof UNBOUND = UNBOUND;
  special: ((form: Cons) => Value) | null = null;
  builtin: Native | null = null;
  constructor(readonly name: string) {}
}

export class Cons {
  constructor(
    public car: Value,
    public cdr: Value,
  ) {}
}

export class LispFunction {
  readonly names: Sym[];
  constructor(
    readonly name: string,
    readonly params: Sym[],
    readonly locals: Sym[],
    readonly body: Value[],
  ) {
    this.names = [...params, ...locals];
  }
}

export class CaughtError {
  constructor(readonly message: string) {}
}

export class FileHandle {
  position = 0;
  constructor(
    readonly path: string,
    readonly mode: string,
    readonly lines: string[] | null,
  ) {}
}

/** A boxed integer (`box-int` mode) or a boxed real (`box-real` mode). */
export class Boxed {
  constructor(readonly v: number) {}
}

export type Value = null | string | number | Boxed | Sym | Cons | LispFunction | Native | CaughtError | FileHandle;

export class LispError extends Error {}
export class Exit extends Error {
  constructor() {
    super('quit / exit abort');
  }
}

export interface Numbers {
  readonly mode: 'box-int' | 'box-real';
  isNum(v: Value): boolean;
  isInt(v: Value): boolean;
  /** A JS integer already in 32-bit range. */
  int(n: number): Value;
  real(x: number): Value;
  val(v: Value): number;
}

const INT_CACHE_LOW = -1024;
const INT_CACHE = Array.from({ length: 8192 }, (_, i) => new Boxed(i + INT_CACHE_LOW));

/** Integers boxed, reals plain JS numbers. */
export const boxInt: Numbers = {
  mode: 'box-int',
  isNum: (v) => typeof v === 'number' || v instanceof Boxed,
  isInt: (v) => v instanceof Boxed,
  int: (n) => {
    const index = n - INT_CACHE_LOW;
    return index >= 0 && index < INT_CACHE.length ? INT_CACHE[index]! : new Boxed(n);
  },
  real: (x) => x,
  val: (v) => (typeof v === 'number' ? v : (v as Boxed).v),
};

/** Integers plain JS numbers, reals boxed. */
export const boxReal: Numbers = {
  mode: 'box-real',
  isNum: (v) => typeof v === 'number' || v instanceof Boxed,
  isInt: (v) => typeof v === 'number',
  int: (n) => n,
  real: (x) => new Boxed(x),
  val: (v) => (typeof v === 'number' ? v : (v as Boxed).v),
};

/** `wrap_int`: two's-complement 32-bit (ToInt32 is exact on any finite double). */
export const wrap = (n: number): number => n | 0;

/** Truncate a real to a wrapped integer like Python's `wrap_int(int(x))`. */
export function truncWrap(x: number): number {
  const t = Math.trunc(x);
  if (Math.abs(t) < 2 ** 31) return t | 0;
  if (!Number.isFinite(t)) throw new LispError('cannot convert float to integer');
  return Number(BigInt.asIntN(32, BigInt(t)));
}

/** A proper list from an array (`nil` when empty). */
export function list(items: readonly Value[], tail: Value = null): Value {
  let result = tail;
  for (let i = items.length - 1; i >= 0; i--) result = new Cons(items[i]!, result);
  return result;
}

/** The elements of a proper list (a dotted tail is an error, as iterating a Pair is in Python). */
export function toArray(value: Value): Value[] {
  const out: Value[] = [];
  let cell = value;
  while (cell instanceof Cons) {
    out.push(cell.car);
    cell = cell.cdr;
  }
  if (cell !== null) throw new LispError(`bad argument type: listp ${describe(value)}`);
  return out;
}

export function car(value: Value): Value {
  if (value === null) return null;
  if (value instanceof Cons) return value.car;
  throw new LispError(`bad argument type: consp ${describe(value)}`);
}

export function cdr(value: Value): Value {
  if (value === null) return null;
  if (value instanceof Cons) return value.cdr;
  throw new LispError(`bad argument type: consp ${describe(value)}`);
}

export function describe(value: Value): string {
  if (value instanceof Sym) return value.name;
  if (typeof value === 'string') return JSON.stringify(value);
  if (value instanceof Cons) return '(...)';
  return String(value);
}
