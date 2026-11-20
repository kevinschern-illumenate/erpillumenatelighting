// Writes the CAD toolkit's layer and block data (draw-to-quote plan 1.6, 3.4). CI fails if it is stale.
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { runnerImport } from 'vite';

const target = resolve(import.meta.dirname, '../../cad_toolkit/lisp/il-assets.lsp');
const { module } = await runnerImport(resolve(import.meta.dirname, '../packages/drawing/src/cadAssets.ts'));
mkdirSync(dirname(target), { recursive: true });
writeFileSync(target, module.cadAssetsLisp());
console.log(`Wrote ${target}`);
