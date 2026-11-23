import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { PURE_FILES, createVm } from './bench';
import { decode } from './trace';

const REPO = resolve(import.meta.dirname, '../../../../..');
const MODELS = resolve(REPO, 'tools/system_designer/fixtures/cad/web/bench-models.json');
const sources = Object.fromEntries(
  PURE_FILES.map((n) => [n, readFileSync(resolve(REPO, 'tools/cad_toolkit/lisp', n), 'utf8')]),
);

describe.runIf(existsSync(MODELS))('native il-json-text', () => {
  it('writes exactly what the LISP writer writes, for the catalog and every benchmark package', () => {
    const input = JSON.parse(readFileSync(MODELS, 'utf8'));
    const lisp = createVm(sources, { numbers: 'box-int', nativeSha: true });
    const native = createVm(sources, {
      numbers: 'box-int',
      nativeSha: true,
      nativeJson: true,
    });
    for (const vm of [lisp, native]) vm.set('*bench-catalog*', decode(vm, input.catalog));
    expect(native.call('il-json-text', native.get('*bench-catalog*'))).toBe(
      lisp.call('il-json-text', lisp.get('*bench-catalog*')),
    );
    for (const size of Object.keys(input.models)) {
      const texts = [lisp, native].map((vm) => {
        const model = decode(vm, input.models[size]);
        const catalog = vm.get('*bench-catalog*');
        const issues = vm.call('il-check', model, catalog, input.today);
        return [
          vm.call('il-json-text', vm.call('il-package', model, catalog, issues, 'bench')),
          vm.call('il-model-hash', model, catalog),
        ];
      });
      expect(texts[1]).toEqual(texts[0]);
    }
  }, 120_000);
});
