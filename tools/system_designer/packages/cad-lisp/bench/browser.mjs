/* global console, navigator, Worker */
// W-0.1: run the LISP benchmark in a Chromium Web Worker.
//   node packages/cad-lisp/bench/browser.mjs   (from tools/system_designer)
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { chromium } from 'playwright';
import { build } from 'vite';

const HERE = import.meta.dirname;
const REPO = resolve(HERE, '../../../../..');
const FILES = [
  'il-util.lsp',
  'il-json.lsp',
  'il-math.lsp',
  'il-sha256.lsp',
  'il-catalog.lsp',
  'il-model.lsp',
  'il-controls.lsp',
];
const sources = Object.fromEntries(
  FILES.map((n) => [n, readFileSync(resolve(REPO, 'tools/cad_toolkit/lisp', n), 'utf8')]),
);
const input = JSON.parse(
  readFileSync(resolve(REPO, 'tools/system_designer/fixtures/cad/web/bench-models.json'), 'utf8'),
);

const output = await build({
  configFile: false,
  logLevel: 'warn',
  build: {
    write: false,
    minify: true,
    lib: {
      entry: resolve(HERE, 'worker.ts'),
      formats: ['iife'],
      name: 'bench',
    },
  },
});
const workerCode = (Array.isArray(output) ? output[0] : output).output[0].code;
console.log(`worker bundle ${(workerCode.length / 1024).toFixed(1)} KB`);

const browser = await chromium.launch();
const page = await browser.newPage();
await page.route('http://bench.local/**', (route) => {
  const url = route.request().url();
  if (url.endsWith('/worker.js')) return route.fulfill({ contentType: 'text/javascript', body: workerCode });
  return route.fulfill({
    contentType: 'text/html',
    body: '<!doctype html><title>bench</title>',
  });
});
await page.goto('http://bench.local/');
console.log(await page.evaluate(() => navigator.userAgent));
const matrix = [
  { numbers: 'box-int', nativeSha: true, nativeJson: false },
  { numbers: 'box-real', nativeSha: true, nativeJson: false },
  { numbers: 'box-int', nativeSha: true, nativeJson: true },
  { numbers: 'box-real', nativeSha: true, nativeJson: true },
];
for (const options of matrix) {
  const reply = await page.evaluate(
    ([sources, input, options]) =>
      new Promise((done) => {
        const worker = new Worker('/worker.js');
        worker.onmessage = (event) => {
          done(event.data);
          worker.terminate();
        };
        worker.postMessage({
          sources,
          input,
          options: { ...options, repeat: 3 },
        });
      }),
    [sources, input, options],
  );
  console.log(`chromium-worker ${options.numbers} nativeJson=${options.nativeJson}`, JSON.stringify(reply));
}
await browser.close();
