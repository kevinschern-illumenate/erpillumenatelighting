// Server rendering checks the actual JSX without requiring a connected browser.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import React from 'react';
import ReactDOM from 'react-dom/client';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import react from '@vitejs/plugin-react';

const schema = JSON.parse(readFileSync(new URL('../src/catalog-schema.json', import.meta.url)));
const examples = JSON.parse(readFileSync(new URL('../src/catalog-examples.json', import.meta.url)));
const server = await createServer({ configFile: false, plugins: [react()], server: { middlewareMode: true }, appType: 'custom' });
try {
  const { default: CatalogApp, RecordFields } = await server.ssrLoadModule('/src/CatalogApp.jsx');
  const loadReference = () => new Promise(() => {});
  const shell = renderToStaticMarkup(React.createElement(CatalogApp, { onLegacy() {}, loadReference }));
  for (const product of Object.values(schema.products)) assert.ok(shell.includes(product.label));
  const { default: Workspace } = await server.ssrLoadModule('/src/Workspace.jsx');
  const erpShell = renderToStaticMarkup(React.createElement(Workspace, { loadReference, mode: 'erp' }));
  assert.ok(erpShell.includes('Download catalog') && erpShell.includes('YAML Builder'));
  for (const [product, catalog] of Object.entries(examples)) {
    for (const [doctype, records] of Object.entries(catalog.records)) {
      for (const row of records) {
        const html = renderToStaticMarkup(React.createElement(RecordFields, { doctype, row, catalog, onChange() {} }));
        assert.ok(html.includes('catalog-fields'), `${product} / ${doctype} must render`);
      }
    }
  }
  const { default: Legacy } = await server.ssrLoadModule('/src/App.jsx');
  assert.ok(renderToStaticMarkup(React.createElement(Legacy)).includes('YAML Builder'));
  // Exercise the actual ERP entry and loader without needing a browser or site.
  const { mount } = await server.ssrLoadModule('/src/erp-main.jsx');
  const originalCreateRoot = ReactDOM.createRoot;
  const originalFetch = globalThis.fetch;
  const originalDocument = globalThis.document;
  try {
    let mounted;
    const element = {};
    globalThis.document = { getElementById: id => { assert.equal(id, 'erp-root'); return element; } };
    ReactDOM.createRoot = target => {
      assert.equal(target, element);
      return { render: tree => { mounted = tree.props.children.props; } };
    };
    mount('erp-root', { referenceUrl: '/api/reference', csrfToken: 'test-csrf' });
    assert.equal(mounted.mode, 'erp');
    assert.equal(mounted.csrfToken, 'test-csrf');
    const reference = { schema_version: 1, doctypes: {} };
    globalThis.fetch = async (url, options) => {
      assert.equal(url, '/api/reference');
      assert.equal(options.credentials, 'same-origin');
      assert.equal(options.headers.Accept, 'application/json');
      return { ok: true, json: async () => ({ message: reference }) };
    };
    assert.deepEqual(await mounted.loadReference(), reference);
    for (const status of [401, 403, 500]) {
      globalThis.fetch = async () => ({ ok: false, status });
      await assert.rejects(mounted.loadReference(), status === 500 ? /500/ : /Reload the page/);
    }
  } finally {
    ReactDOM.createRoot = originalCreateRoot;
    globalThis.fetch = originalFetch;
    if (originalDocument === undefined) delete globalThis.document;
    else globalThis.document = originalDocument;
  }
  console.log('Rendered Vercel/ERP catalog shells, all seven product examples, and legacy editor; verified ERP reference loading.');
} finally { await server.close(); }
