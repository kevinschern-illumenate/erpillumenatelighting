import { readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

const SRC = join(import.meta.dirname, '..');
const TOKENS = join(SRC, 'ui', 'tokens.css');

function cssFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) =>
    entry.isDirectory() ? cssFiles(join(dir, entry.name)) : entry.name.endsWith('.css') ? [join(dir, entry.name)] : [],
  );
}

describe('design tokens (SD-1.1)', () => {
  it('keeps raw colours in tokens.css only', () => {
    const offenders = cssFiles(SRC)
      .filter((file) => file !== TOKENS)
      .flatMap((file) =>
        readFileSync(file, 'utf8')
          .split('\n')
          .map((line, index) => ({ line, at: `${relative(SRC, file)}:${index + 1}` }))
          .filter(({ line }) => /#[0-9a-f]{3,8}\b|rgba?\(|hsla?\(/i.test(line))
          .map(({ at, line }) => `${at} ${line.trim()}`),
      );
    expect(offenders).toEqual([]);
  });

  it('maps the semantic tokens onto portal tokens', () => {
    const css = readFileSync(TOKENS, 'utf8');
    for (const token of ['--sd-text:', '--sd-accent:', '--sd-error:', '--sd-warning:', '--sd-ok:', '--sd-border:'])
      expect(css).toMatch(new RegExp(`${token} var\\(--ill-`));
  });
});
