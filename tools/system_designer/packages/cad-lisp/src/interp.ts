/**
 * The AutoLISP subset the toolkit's pure files use (W-0.1 spike), ported from
 * `tools/cad_toolkit/test/mini_lisp.py` with the same semantics: dynamic scope (shallow binding on the
 * symbol's value slot), integer division, 32-bit integers, case-insensitive symbols, nil as the empty
 * list, dotted pairs, `vl-catch-all-apply`, files read line by line (from a virtual file system).
 */

import { installBuiltins } from './builtins';
import {
  Cons,
  LispError,
  LispFunction,
  type Native,
  type Numbers,
  Sym,
  UNBOUND,
  type Value,
  boxInt,
  boxReal,
  list,
  toArray,
} from './values';

export interface InterpreterOptions {
  numbers?: 'box-int' | 'box-real';
}

/** In-memory files: what `open` reads and writes. */
export class Vfs {
  readonly files = new Map<string, string>();
  put(path: string, content: string) {
    this.files.set(path, content);
  }
  get(path: string) {
    return this.files.get(path);
  }
}

const TOKEN = /\s+|;\|[\s\S]*?\|;|;[^\n]*|"(?:\\[\s\S]|[^"\\])*"|[()']|[^\s()'";]+/g;
const ESCAPES: Record<string, string> = {
  n: '\n',
  t: '\t',
  r: '\r',
  e: '\x1b',
  '\\': '\\',
  '"': '"',
};
const INT_TOKEN = /^[+-]?\d+$/;
const REAL_TOKEN = /^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$/;

function unescape(body: string): string {
  let out = '';
  let index = 0;
  while (index < body.length) {
    const char = body[index]!;
    if (char === '\\' && index + 1 < body.length) {
      const next = body[index + 1]!;
      if (next >= '0' && next <= '9') {
        const digits = /^[0-7]{1,3}/.exec(body.slice(index + 1))?.[0];
        if (digits === undefined) throw new LispError('bad octal escape');
        out += String.fromCharCode(parseInt(digits, 8));
        index += 1 + digits.length;
        continue;
      }
      out += ESCAPES[next] ?? next;
      index += 2;
      continue;
    }
    out += char;
    index += 1;
  }
  return out;
}

export type Callable = LispFunction | Native;

export class Interpreter {
  readonly N: Numbers;
  readonly T: Sym;
  readonly vfs = new Vfs();
  private readonly symbols = new Map<string, Sym>();
  private readonly LAMBDA: Sym;
  private readonly QUOTE: Sym;
  private readonly SLASH: Sym;

  constructor(options: InterpreterOptions = {}) {
    this.N = options.numbers === 'box-real' ? boxReal : boxInt;
    this.T = this.sym('T');
    this.LAMBDA = this.sym('LAMBDA');
    this.QUOTE = this.sym('QUOTE');
    this.SLASH = this.sym('/');
    this.installSpecials();
    installBuiltins(this);
  }

  sym(name: string): Sym {
    const upper = name.toUpperCase();
    let found = this.symbols.get(upper);
    if (!found) {
      found = new Sym(upper);
      this.symbols.set(upper, found);
    }
    return found;
  }

  // --- Reader ------------------------------------------------------------------------------------

  atom(token: string): Value {
    if (token.startsWith('"')) return unescape(token.slice(1, -1));
    if (INT_TOKEN.test(token)) {
      const n = Number(token);
      return this.N.int(Math.abs(n) < 2 ** 31 ? n | 0 : Number(BigInt.asIntN(32, BigInt(token))));
    }
    if (REAL_TOKEN.test(token)) return this.N.real(Number(token));
    const symbol = this.sym(token);
    return symbol.name === 'NIL' ? null : symbol;
  }

  readAll(text: string): Value[] {
    const tokens: string[] = [];
    for (const match of text.matchAll(TOKEN)) {
      const token = match[0];
      if (/^\s/.test(token) || token.startsWith(';')) continue;
      tokens.push(token);
    }
    let position = 0;
    const read = (): Value => {
      const token = tokens[position++];
      if (token === undefined) throw new LispError('unexpected end of input');
      if (token === "'") return new Cons(this.QUOTE, new Cons(read(), null));
      if (token === '(') {
        const items: Value[] = [];
        while (tokens[position] !== ')') {
          if (tokens[position] === undefined) throw new LispError('missing )');
          if (tokens[position] === '.') {
            position += 1;
            const tail = read();
            position += 1;
            return list(items, tail);
          }
          items.push(read());
        }
        position += 1;
        return list(items);
      }
      if (token === ')') throw new LispError('unexpected )');
      return this.atom(token);
    };
    const forms: Value[] = [];
    while (position < tokens.length) forms.push(read());
    return forms;
  }

  // --- Evaluation --------------------------------------------------------------------------------

  loadText(text: string): Value {
    let result: Value = null;
    for (const form of this.readAll(text)) result = this.eval(form);
    return result;
  }

  run(text: string): Value {
    return this.loadText(text);
  }

  call(name: string, ...args: Value[]): Value {
    return this.apply(this.fn(this.sym(name)), args);
  }

  get(name: string): Value {
    const value = this.sym(name).value;
    return value === UNBOUND ? null : value;
  }

  set(name: string, value: Value) {
    this.sym(name).value = value;
  }

  fn(head: Value): Callable {
    if (head instanceof Sym) {
      const value = head.value;
      if (value instanceof LispFunction || typeof value === 'function') return value;
      if (head.builtin) return head.builtin;
      throw new LispError(`no function definition: ${head.name}`);
    }
    if (head instanceof Cons && head.car === this.LAMBDA) return this.eval(head) as LispFunction;
    if (head instanceof LispFunction || typeof head === 'function') return head;
    throw new LispError('bad function');
  }

  eval(form: Value): Value {
    if (form instanceof Sym) {
      if (form === this.T) return this.T;
      const value = form.value;
      return value === UNBOUND ? null : value;
    }
    if (!(form instanceof Cons)) return form;
    const head = form.car;
    if (head instanceof Sym && head.special) return head.special(form);
    const fn = this.fn(head);
    const args: Value[] = [];
    for (let cell = form.cdr; cell instanceof Cons; cell = cell.cdr) args.push(this.eval(cell.car));
    return this.apply(fn, args);
  }

  apply(fn: Callable, args: Value[]): Value {
    if (typeof fn === 'function') return fn(args);
    const names = fn.names;
    const count = names.length;
    const params = fn.params.length;
    const saved = new Array<Value | typeof UNBOUND>(count);
    for (let i = 0; i < count; i++) saved[i] = names[i]!.value;
    try {
      for (let i = 0; i < count; i++) names[i]!.value = i < params && i < args.length ? args[i]! : null;
      let result: Value = null;
      const body = fn.body;
      for (let i = 0; i < body.length; i++) result = this.eval(body[i]!);
      return result;
    } finally {
      for (let i = count - 1; i >= 0; i--) names[i]!.value = saved[i]!;
    }
  }

  parseParams(spec: Value): [Sym[], Sym[]] {
    const params: Sym[] = [];
    const locals: Sym[] = [];
    let inLocals = false;
    for (let cell = spec; cell instanceof Cons; cell = cell.cdr) {
      if (cell.car === this.SLASH) {
        inLocals = true;
        continue;
      }
      (inLocals ? locals : params).push(cell.car as Sym);
    }
    return [params, locals];
  }

  private installSpecials() {
    const def = (name: string, special: (form: Cons) => Value) => {
      this.sym(name).special = special;
    };
    const second = (f: Cons): Value => (f.cdr instanceof Cons ? f.cdr.car : null);
    const rest = (f: Value): Cons | null => (f instanceof Cons && f.cdr instanceof Cons ? f.cdr : null);
    const progn = (cell: Value): Value => {
      let result: Value = null;
      for (let c = cell; c instanceof Cons; c = c.cdr) result = this.eval(c.car);
      return result;
    };
    def('QUOTE', (f) => second(f));
    def('SETQ', (f) => {
      let value: Value = null;
      for (let c = f.cdr; c instanceof Cons; c = c.cdr instanceof Cons ? c.cdr.cdr : null) {
        value = this.eval(c.cdr instanceof Cons ? c.cdr.car : null);
        (c.car as Sym).value = value;
      }
      return value;
    });
    def('IF', (f) => {
      const test = rest(f);
      const then = rest(test);
      const otherwise = rest(then);
      if (this.eval(test?.car ?? null) !== null) return this.eval(then?.car ?? null);
      return otherwise ? this.eval(otherwise.car) : null;
    });
    def('COND', (f) => {
      for (let c = f.cdr; c instanceof Cons; c = c.cdr) {
        const clause = c.car as Cons;
        const test = this.eval(clause.car);
        if (test !== null) return clause.cdr instanceof Cons ? progn(clause.cdr) : test;
      }
      return null;
    });
    def('WHILE', (f) => {
      const test = second(f);
      const body = rest(f)?.cdr ?? null;
      let result: Value = null;
      while (this.eval(test) !== null) result = body === null ? result : progn(body);
      return result;
    });
    def('REPEAT', (f) => {
      const times = Math.trunc(this.N.val(this.eval(second(f))));
      const body = rest(f)?.cdr ?? null;
      let result: Value = null;
      for (let n = 0; n < times; n++) result = body === null ? result : progn(body);
      return result;
    });
    def('FOREACH', (f) => {
      const name = second(f) as Sym;
      const listForm = rest(rest(f));
      const items = this.eval(listForm?.car ?? null);
      const body = listForm?.cdr ?? null;
      const saved = name.value;
      let result: Value = null;
      try {
        for (let c = items; c instanceof Cons; c = c.cdr) {
          name.value = c.car;
          if (body !== null) result = progn(body);
        }
      } finally {
        name.value = saved;
      }
      return result;
    });
    def('PROGN', (f) => progn(f.cdr));
    def('AND', (f) => {
      for (let c = f.cdr; c instanceof Cons; c = c.cdr) if (this.eval(c.car) === null) return null;
      return this.T;
    });
    def('OR', (f) => {
      for (let c = f.cdr; c instanceof Cons; c = c.cdr) if (this.eval(c.car) !== null) return this.T;
      return null;
    });
    def('DEFUN', (f) => {
      const name = second(f) as Sym;
      const spec = rest(rest(f));
      const [params, locals] = this.parseParams(spec?.car ?? null);
      name.value = new LispFunction(name.name, params, locals, toArray(spec?.cdr ?? null));
      return name;
    });
    def('LAMBDA', (f) => {
      const spec = rest(f);
      const [params, locals] = this.parseParams(spec?.car ?? null);
      return new LispFunction('lambda', params, locals, toArray(spec?.cdr ?? null));
    });
    def('FUNCTION', (f) => {
      const value = second(f);
      if (value instanceof Cons && value.car === this.LAMBDA) return this.eval(value);
      return value;
    });
  }
}

// --- Equality used by builtins -----------------------------------------------------------------------

/** `lisp_equal` (EQUAL, MEMBER, ASSOC, SUBST): iterative along cdrs, recursive on cars. */
export function lispEqual(N: Numbers, a: Value, b: Value, fuzz = 0): boolean {
  for (;;) {
    if (N.isNum(a) && N.isNum(b)) {
      const x = N.val(a);
      const y = N.val(b);
      return fuzz ? Math.abs(x - y) <= fuzz : x === y;
    }
    if (a instanceof Cons && b instanceof Cons) {
      if (!lispEqual(N, a.car, b.car, fuzz)) return false;
      a = a.cdr;
      b = b.cdr;
      continue;
    }
    return a === b;
  }
}

/** Python `==` as `=` and `/=` use it (lists compare by elements, numbers by value). */
export function pyEq(N: Numbers, a: Value, b: Value): boolean {
  if (N.isNum(a) && N.isNum(b)) return N.val(a) === N.val(b);
  if (a instanceof Cons && b instanceof Cons) return lispEqual(N, a, b);
  return a === b;
}
