/**
 * Native `il-json-text` (W-0.1 fallback, W5.1): the same text as `il-jw-pieces` in `il-json.lsp`, built
 * in one pass instead of one cons and one `substr` per character. Numbers are formatted by the LISP's
 * own `il-num->str` and other atoms by `il-str`, so formatting cannot drift; `native-json.test.ts`
 * compares the output with the LISP writer character for character.
 */

import type { Interpreter } from './interp';
import { Cons, type Value } from './values';

export function installNativeJson(interp: Interpreter) {
  const N = interp.N;
  const OBJ = interp.sym('IL-OBJ');
  const ARR = interp.sym('IL-ARR');
  const TRUE = interp.sym('IL-TRUE');
  const FALSE = interp.sym('IL-FALSE');
  const six = N.int(6);

  const string = (text: string, out: string[]) => {
    let escaped = '"';
    for (let i = 0; i < text.length; i++) {
      const char = text[i]!;
      const code = text.codePointAt(i)!;
      if (char === '"') escaped += '\\"';
      else if (char === '\\') escaped += '\\\\';
      else if (code === 10) escaped += '\\n';
      else if (code === 13) escaped += '\\r';
      else if (code === 9) escaped += '\\t';
      else if (code < 32) escaped += ' ';
      else escaped += char;
    }
    out.push(`${escaped}"`);
  };

  const write = (value: Value, out: string[]) => {
    if (value === null) out.push('null');
    else if (value === TRUE) out.push('true');
    else if (value === FALSE) out.push('false');
    else if (typeof value === 'string') string(value, out);
    else if (N.isNum(value))
      out.push(N.isInt(value) ? String(N.val(value)) : (interp.call('il-num->str', value, six) as string));
    else if (value instanceof Cons && value.car === OBJ) {
      out.push('{');
      let first = true;
      for (let cell = value.cdr; cell instanceof Cons; cell = cell.cdr) {
        const pair = cell.car as Cons;
        if (!first) out.push(',');
        first = false;
        string(pair.car as string, out);
        out.push(':');
        write(pair.cdr, out);
      }
      out.push('}');
    } else if (value instanceof Cons && value.car === ARR) {
      out.push('[');
      let first = true;
      for (let cell = value.cdr; cell instanceof Cons; cell = cell.cdr) {
        if (!first) out.push(',');
        first = false;
        write(cell.car, out);
      }
      out.push(']');
    } else string(interp.call('il-str', value) as string, out);
  };

  interp.set('il-json-text', (args) => {
    const out: string[] = [];
    write(args[0] ?? null, out);
    return out.join('');
  });
}
