/**
 * Builtins: exactly the table in `mini_lisp.py builtins(interp)`, with its semantics (integer wrap,
 * Python-style formatting, `vl-catch-all-apply` catching interpreter and type errors). Lists are cons
 * cells (values.ts); builtins take their arguments as one array.
 */

import { formatFixed, pyFloatRepr } from './format';
import { type Interpreter, lispEqual, pyEq } from './interp';
import {
  CaughtError,
  Cons,
  Exit,
  FileHandle,
  LispError,
  LispFunction,
  type Native,
  Sym,
  type Value,
  car,
  cdr,
  list,
  toArray,
  truncWrap,
  wrap,
} from './values';

export function princText(interp: Interpreter, value: Value, readable = false): string {
  const N = interp.N;
  if (value === null) return 'nil';
  if (typeof value === 'string') return readable ? `"${value.replaceAll('\\', '\\\\').replaceAll('"', '\\"')}"` : value;
  if (N.isNum(value)) {
    if (N.isInt(value)) return String(N.val(value));
    const text = formatFixed(N.val(value), 6).replace(/0+$/, '');
    return text.endsWith('.') ? `${text}0` : text;
  }
  if (value instanceof Cons) {
    // Python prints a list as (a b c) and a Pair as (car . cdr); (a b . c) is Pair(a, Pair(b, c)).
    const parts: string[] = [];
    let cell: Value = value;
    while (cell instanceof Cons) {
      parts.push(princText(interp, cell.car, true));
      cell = cell.cdr;
    }
    if (cell === null) return `(${parts.join(' ')})`;
    let text = princText(interp, cell, true);
    for (let i = parts.length - 1; i >= 0; i--) text = `(${parts[i]} . ${text})`;
    return text;
  }
  if (value instanceof Sym) return value.name;
  return String(value);
}

export function installBuiltins(interp: Interpreter) {
  const N = interp.N;
  const T = interp.T;
  const sym = (name: string) => interp.sym(name);
  const bool = (flag: boolean): Value => (flag ? T : null);
  const a0 = (args: Value[]) => args[0] ?? null;
  const a1 = (args: Value[]) => args[1] ?? null;

  const num = (value: Value): number => {
    if (N.isNum(value)) return N.val(value);
    throw new LispError(`bad argument type: numberp: ${princText(interp, value)}`);
  };
  const intArg = (value: Value) => Math.trunc(num(value));
  const allInt = (values: Value[]) => values.every((v) => N.isInt(v));

  const arith = (op: '+' | '-' | '*' | '/', values: Value[]): Value => {
    const nums = values.map(num);
    if (allInt(values)) {
      let result = nums[0]!;
      for (let i = 1; i < nums.length; i++) {
        const v = nums[i]!;
        if (op === '/') {
          if (v === 0) throw new LispError('divide by zero');
          result = Math.trunc(result / v);
        } else if (op === '+') result = (result + v) | 0;
        else if (op === '-') result = (result - v) | 0;
        else result = Math.imul(result, v);
      }
      return N.int(wrap(result));
    }
    let result = nums[0]!;
    for (let i = 1; i < nums.length; i++) {
      const v = nums[i]!;
      if (op === '/') {
        if (v === 0) throw new LispError('divide by zero');
        result /= v;
      } else if (op === '+') result += v;
      else if (op === '-') result -= v;
      else result *= v;
    }
    return N.real(result);
  };

  const compareKey = (value: Value): number | string => {
    if (N.isNum(value)) return N.val(value);
    if (typeof value === 'string') return value;
    throw new LispError(`bad argument type for comparison: ${princText(interp, value)}`);
  };
  const ordered =
    (test: (a: number | string, b: number | string) => boolean): Native =>
    (values) => {
      for (let i = 1; i < values.length; i++) {
        const a = compareKey(values[i - 1]!);
        const b = compareKey(values[i]!);
        if (typeof a !== typeof b) throw new LispError('bad argument type for comparison');
        if (!test(a, b)) return null;
      }
      return T;
    };

  const fnOf = (f: Value) => (f instanceof LispFunction ? f : interp.fn(f));
  const call = (f: Value, ...args: Value[]) => interp.apply(fnOf(f), args);

  const trim = (chars: string, text: string, left: boolean, right: boolean) => {
    let start = 0;
    let end = text.length;
    if (left) while (start < end && chars.includes(text[start]!)) start++;
    if (right) while (end > start && chars.includes(text[end - 1]!)) end--;
    return text.slice(start, end);
  };

  const writes = new Map<FileHandle, string[]>();
  const write = (handle: FileHandle, text: string) => {
    const chunks = writes.get(handle) ?? [];
    chunks.push(text);
    writes.set(handle, chunks);
  };
  const splitLines = (content: string): string[] => {
    const lines: string[] = [];
    for (const match of content.matchAll(/[^\r\n]*(\r\n|\r|\n)|[^\r\n]+$/g)) {
      if (match[0] === '') break;
      lines.push(match[0].replace(/[\r\n]+$/, ''));
    }
    return lines;
  };

  const lispType = (value: Value): Value => {
    if (value === null) return null;
    if (N.isNum(value)) return sym(N.isInt(value) ? 'INT' : 'REAL');
    if (typeof value === 'string') return sym('STR');
    if (value instanceof Cons) return sym('LIST');
    if (value instanceof Sym) return sym('SYM');
    if (value instanceof LispFunction) return sym('USUBR');
    if (value instanceof FileHandle) return sym('FILE');
    return sym('SUBR');
  };

  const minMax =
    (pick: (a: number, b: number) => number): Native =>
    (values) => {
      const picked = values.map(num).reduce((a, b) => pick(a, b));
      return allInt(values) ? N.int(wrap(picked)) : N.real(picked);
    };

  /** Parallel walk of several lists, stopping at the shortest (Python `zip`). */
  const columns = (lists: Value[]): Value[][] => {
    const arrays = lists.map(toArray);
    const count = arrays.length ? Math.min(...arrays.map((c) => c.length)) : 0;
    const rows: Value[][] = [];
    for (let i = 0; i < count; i++) rows.push(arrays.map((c) => c[i]!));
    return rows;
  };

  const table: Record<string, Native> = {
    '+': (v) => (v.length ? arith('+', v) : N.int(0)),
    '-': (v) => (v.length === 1 ? arith('-', [N.int(0), v[0]!]) : arith('-', v)),
    '*': (v) => (v.length ? arith('*', v) : N.int(1)),
    '/': (v) => arith('/', v),
    '1+': (v) => arith('+', [a0(v), N.int(1)]),
    '1-': (v) => arith('-', [a0(v), N.int(1)]),
    '=': (v) => {
      for (let i = 1; i < v.length; i++) if (!pyEq(N, v[i - 1]!, v[i]!)) return null;
      return T;
    },
    '/=': (v) => {
      for (let i = 1; i < v.length; i++) if (pyEq(N, v[i - 1]!, v[i]!)) return null;
      return T;
    },
    '<': ordered((a, b) => a < b),
    '>': ordered((a, b) => a > b),
    '<=': ordered((a, b) => a <= b),
    '>=': ordered((a, b) => a >= b),
    ABS: (v) => (N.isInt(a0(v)) ? N.int(wrap(Math.abs(num(a0(v))))) : N.real(Math.abs(num(a0(v))))),
    FIX: (v) => N.int(truncWrap(num(a0(v)))),
    FLOAT: (v) => N.real(num(a0(v))),
    REM: ([a = null, b = null]) =>
      N.isInt(a) && N.isInt(b) ? N.int(truncWrap(num(a) % num(b))) : N.real(num(a) % num(b)),
    EXPT: ([a = null, b = null]) => {
      if (N.isInt(a) && N.isInt(b) && num(b) >= 0)
        return N.int(Number(BigInt.asIntN(32, BigInt(num(a)) ** BigInt(num(b)))));
      return N.real(num(a) ** num(b));
    },
    SQRT: (v) => {
      if (num(a0(v)) < 0) throw new LispError('math domain error');
      return N.real(Math.sqrt(num(a0(v))));
    },
    SIN: (v) => N.real(Math.sin(num(a0(v)))),
    COS: (v) => N.real(Math.cos(num(a0(v)))),
    ATAN: (v) => N.real(v.length < 2 || v[1] === null ? Math.atan(num(a0(v))) : Math.atan2(num(a0(v)), num(v[1]!))),
    MIN: minMax(Math.min),
    MAX: minMax(Math.max),
    MINUSP: (v) => bool(num(a0(v)) < 0),
    ZEROP: (v) => bool(num(a0(v)) === 0),
    NUMBERP: (v) => bool(N.isNum(a0(v))),
    EQ: ([a = null, b = null]) => bool(a === b || (N.isNum(a) && N.isNum(b) && N.val(a) === N.val(b))),
    EQUAL: ([a = null, b = null, fuzz = null]) => bool(lispEqual(N, a, b, fuzz === null ? 0 : num(fuzz))),
    NOT: (v) => bool(a0(v) === null),
    NULL: (v) => bool(a0(v) === null),
    LISTP: (v) => bool(a0(v) === null || a0(v) instanceof Cons),
    ATOM: (v) => bool(!(a0(v) instanceof Cons)),
    TYPE: (v) => lispType(a0(v)),
    CAR: (v) => car(a0(v)),
    CDR: (v) => cdr(a0(v)),
    CADR: (v) => car(cdr(a0(v))),
    CADDR: (v) => car(cdr(cdr(a0(v)))),
    CDDR: (v) => cdr(cdr(a0(v))),
    CADDDR: (v) => car(cdr(cdr(cdr(a0(v))))),
    CDDDDR: (v) => cdr(cdr(cdr(cdr(a0(v))))),
    LOGAND: (v) => N.int(v.reduce<number>((a, b) => a & intArg(b), -1) | 0),
    LOGIOR: (v) => N.int(v.reduce<number>((a, b) => a | intArg(b), 0) | 0),
    LSH: ([x = null, n = null]) => {
      const shift = n === null ? 0 : intArg(n);
      const value = intArg(x) >>> 0;
      if (shift >= 0) return N.int(shift >= 32 ? 0 : (value << shift) | 0);
      return N.int(-shift >= 32 ? 0 : (value >>> -shift) | 0);
    },
    '~': (v) => N.int(~intArg(a0(v))),
    BOOLE: ([operator = null, ...values]) => {
      const op = intArg(operator);
      let result = intArg(values[0] ?? N.int(0)) | 0;
      for (let i = 1; i < values.length; i++) {
        const x = intArg(values[i]!) | 0;
        let next = 0;
        if (op & 1) next |= result & x;
        if (op & 2) next |= result & ~x;
        if (op & 4) next |= ~result & x;
        if (op & 8) next |= ~result & ~x;
        result = next | 0;
      }
      return N.int(result);
    },
    CAAR: (v) => car(car(a0(v))),
    CDAR: (v) => cdr(car(a0(v))),
    LAST: (v) => {
      let cell = a0(v);
      if (!(cell instanceof Cons)) return null;
      while (cell.cdr instanceof Cons) cell = cell.cdr;
      return cell.car;
    },
    NTH: ([index = null, items = null]) => {
      let i = intArg(index);
      if (i < 0) return null;
      let cell = items;
      while (i > 0 && cell instanceof Cons) {
        cell = cell.cdr;
        i--;
      }
      return cell instanceof Cons ? cell.car : null;
    },
    LENGTH: (v) => {
      const value = a0(v);
      if (typeof value === 'string') return N.int(value.length);
      let n = 0;
      for (let cell: Value = value; cell instanceof Cons; cell = cell.cdr) n++;
      return N.int(n);
    },
    CONS: ([a = null, b = null]) => new Cons(a, b),
    LIST: (v) => list(v),
    APPEND: (lists) => {
      // Python copies every list; sharing the last one (as AutoLISP does) gives equal results.
      if (!lists.length) return null;
      let tail: Value = lists[lists.length - 1]!;
      toArray(tail);
      for (let i = lists.length - 2; i >= 0; i--) tail = list(toArray(lists[i]!), tail);
      return tail;
    },
    REVERSE: (v) => {
      let result: Value = null;
      for (let cell = a0(v); cell instanceof Cons; cell = cell.cdr) result = new Cons(cell.car, result);
      return result;
    },
    ASSOC: ([key = null, items = null]) => {
      for (let cell = items; cell instanceof Cons; cell = cell.cdr) {
        const item = cell.car;
        if (item instanceof Cons && lispEqual(N, item.car, key)) return item;
      }
      return null;
    },
    MEMBER: ([item = null, items = null]) => {
      for (let cell = items; cell instanceof Cons; cell = cell.cdr) if (lispEqual(N, item, cell.car)) return cell;
      return null;
    },
    SUBST: ([next = null, old = null, items = null]) =>
      items === null ? null : list(toArray(items).map((item) => (lispEqual(N, item, old) ? next : item))),
    MAPCAR: ([f = null, ...lists]) => {
      const fn = fnOf(f);
      return list(columns(lists).map((row) => interp.apply(fn, row)));
    },
    APPLY: ([f = null, args = null]) => interp.apply(fnOf(f), toArray(args)),
    STRCAT: (v) => v.join(''),
    SUBSTR: ([text = null, start = null, length = null]) => {
      const s = text as string;
      const begin = Math.max(intArg(start) - 1, 0);
      return length === null ? s.slice(begin) : s.slice(begin, begin + intArg(length));
    },
    STRLEN: (v) => N.int(v.reduce<number>((total, s) => total + (s as string).length, 0)),
    ASCII: (v) => N.int((a0(v) as string).length ? (a0(v) as string).codePointAt(0)! : 0),
    CHR: (v) => String.fromCodePoint(intArg(a0(v))),
    ITOA: (v) => (N.isInt(a0(v)) ? String(N.val(a0(v))) : pyFloatRepr(num(a0(v)))),
    ATOI: (v) => {
      const match = /^\s*[+-]?\d+/.exec(a0(v) as string);
      return N.int(match ? Number(BigInt.asIntN(32, BigInt(match[0].trim()))) : 0);
    },
    ATOF: (v) => {
      const match = /^\s*[+-]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?/.exec(a0(v) as string);
      return N.real(match ? Number(match[0].trim()) : 0);
    },
    RTOS: (v) => formatFixed(num(a0(v)), v.length < 3 || v[2] === null ? 4 : intArg(v[2]!)),
    STRCASE: ([text = null, lower = null]) =>
      lower !== null ? (text as string).toLowerCase() : (text as string).toUpperCase(),
    'VL-STRING-SEARCH': ([pattern = null, text = null, start = null]) => {
      const at = (text as string).indexOf(pattern as string, start === null ? 0 : intArg(start));
      return at < 0 ? null : N.int(at);
    },
    'VL-STRING-TRIM': (v) => trim(a0(v) as string, a1(v) as string, true, true),
    'VL-STRING-RIGHT-TRIM': (v) => trim(a0(v) as string, a1(v) as string, false, true),
    'VL-STRING-LEFT-TRIM': (v) => trim(a0(v) as string, a1(v) as string, true, false),
    'VL-PRINC-TO-STRING': (v) => princText(interp, a0(v)),
    'VL-SORT': ([items = null, test = null]) => {
      const result: Value[] = [];
      for (const item of toArray(items)) {
        let index = result.length;
        while (index > 0 && call(test, item, result[index - 1]!) !== null) index--;
        result.splice(index, 0, item);
      }
      return list(result);
    },
    'VL-SOME': ([test = null, ...lists]) => {
      for (const row of columns(lists)) {
        const value = call(test, ...row);
        if (value !== null) return value;
      }
      return null;
    },
    'VL-REMOVE-IF': ([test = null, items = null]) => list(toArray(items).filter((item) => call(test, item) === null)),
    'VL-REMOVE-IF-NOT': ([test = null, items = null]) =>
      list(toArray(items).filter((item) => call(test, item) !== null)),
    'VL-REMOVE': ([item = null, items = null]) => list(toArray(items).filter((value) => !lispEqual(N, item, value))),
    'VL-POSITION': ([item = null, items = null]) => {
      let i = 0;
      for (let cell = items; cell instanceof Cons; cell = cell.cdr, i++)
        if (lispEqual(N, item, cell.car)) return N.int(i);
      return null;
    },
    'VL-CATCH-ALL-APPLY': ([f = null, args = null]) => {
      try {
        return interp.apply(fnOf(f), toArray(args));
      } catch (error) {
        if (
          error instanceof LispError ||
          error instanceof Exit ||
          error instanceof TypeError ||
          error instanceof RangeError
        )
          return new CaughtError((error as Error).message || 'quit / exit abort');
        throw error;
      }
    },
    'VL-CATCH-ALL-ERROR-P': (v) => bool(a0(v) instanceof CaughtError),
    'VL-CATCH-ALL-ERROR-MESSAGE': (v) => (a0(v) as CaughtError).message,
    DISTANCE: ([a = null, b = null]) => {
      const p = toArray(a).map(num);
      const q = toArray(b).map(num);
      return N.real(Math.hypot((p[0] ?? 0) - (q[0] ?? 0), (p[1] ?? 0) - (q[1] ?? 0)));
    },
    OPEN: ([path = null, mode = null]) => {
      const m = (mode as string).toLowerCase();
      if (m === 'r') {
        const content = interp.vfs.get(path as string);
        return content === undefined ? null : new FileHandle(path as string, m, splitLines(content));
      }
      const handle = new FileHandle(path as string, m, null);
      writes.set(handle, m === 'a' ? [interp.vfs.get(path as string) ?? ''] : []);
      return handle;
    },
    CLOSE: (v) => {
      const handle = a0(v);
      if (handle instanceof FileHandle && handle.mode !== 'r')
        interp.vfs.put(handle.path, (writes.get(handle) ?? []).join(''));
      if (handle instanceof FileHandle) writes.delete(handle);
      return null;
    },
    'READ-LINE': (v) => {
      const handle = a0(v);
      if (!(handle instanceof FileHandle) || !handle.lines || handle.position >= handle.lines.length) return null;
      return handle.lines[handle.position++]!;
    },
    'WRITE-LINE': ([text = null, handle = null]) => {
      if (handle instanceof FileHandle) write(handle, `${text as string}\n`);
      return text;
    },
    PRINC: ([value = null, handle = null]) => {
      if (handle instanceof FileHandle) write(handle, princText(interp, value));
      return value;
    },
    EXIT: () => {
      throw new Exit();
    },
  };
  table.PRIN1 = table.PRINC!;
  table.PRINT = table.PRINC!;
  table.QUIT = table.EXIT!;

  for (const [name, fn] of Object.entries(table)) sym(name).builtin = fn;
}
