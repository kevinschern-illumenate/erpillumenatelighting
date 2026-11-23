import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { PURE_FILES, createVm, runBench } from './bench';
import { sha256Text } from './sha256';

const REPO = resolve(import.meta.dirname, '../../../../..');
const LISP = resolve(REPO, 'tools/cad_toolkit/lisp');
const MODELS = resolve(REPO, 'tools/system_designer/fixtures/cad/web/bench-models.json');
const sources = Object.fromEntries(PURE_FILES.map((name) => [name, readFileSync(resolve(LISP, name), 'utf8')]));

describe('native il-sha256', () => {
  it('equals the LISP il-sha256', () => {
    const vm = createVm(sources, { numbers: 'box-int', nativeSha: false });
    const texts = [
      '',
      'abc',
      'a'.repeat(55),
      'a'.repeat(56),
      'a'.repeat(64),
      '{"schema":"ilq/2","runs":[]}'.repeat(30),
    ];
    for (const text of texts) expect(sha256Text(text)).toBe(vm.call('il-sha256', text));
  });
});

// Timing run, not a gate: BENCH=1 npx vitest run packages/cad-lisp/src/bench.test.ts
describe.runIf(process.env.BENCH && existsSync(MODELS))('W-0.1 benchmark (Node)', () => {
  it.each([
    ['box-int', false],
    ['box-real', false],
    ['box-int', true],
    ['box-real', true],
  ] as const)(
    '%s, native json %s',
    (numbers, nativeJson) => {
      const input = JSON.parse(readFileSync(MODELS, 'utf8'));
      const result = runBench(sources, input, {
        numbers,
        nativeSha: true,
        nativeJson,
        repeat: 3,
      });
      console.log(`node ${numbers} nativeJson=${nativeJson}`, JSON.stringify(result));
    },
    600_000,
  );
  it('LISP il-sha256 at 20 runs (box-int)', () => {
    const input = JSON.parse(readFileSync(MODELS, 'utf8'));
    const result = runBench(sources, input, {
      numbers: 'box-int',
      nativeSha: false,
      repeat: 1,
      sizes: ['20'],
    });
    console.log('node box-int nativeSha=false', JSON.stringify(result));
  }, 600_000);
});
