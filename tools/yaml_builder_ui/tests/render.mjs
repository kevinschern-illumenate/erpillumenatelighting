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
  assert.ok(shell.includes('Add to ERPNext reference after import'));
  assert.ok(!shell.includes('Refresh ERPNext records'));
  for (const product of Object.values(schema.products)) assert.ok(shell.includes(product.label));
  const { default: Workspace } = await server.ssrLoadModule('/src/Workspace.jsx');
  const erpShell = renderToStaticMarkup(React.createElement(Workspace, { loadReference, mode: 'erp' }));
  assert.ok(erpShell.includes('Refresh ERPNext records'));
  assert.ok(!erpShell.includes('Add to ERPNext reference after import'));
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
  assert.ok(shell.includes('Generate the import package'));
  assert.ok(!shell.includes('Check in ERPNext'));
  assert.ok(shell.includes('https://illumenatelighting.v.frappe.cloud/catalog-builder'));
  assert.ok(shell.includes('Save draft here, then Open YAML there'));
  assert.ok(!erpShell.includes('Open ERPNext Catalog Builder'));
  assert.ok(!erpShell.includes('Generate the import package'));
  assert.ok(erpShell.includes('Check in ERPNext') && erpShell.includes('Import to ERPNext'));
  assert.ok(erpShell.includes('Recent checks and imports'));
  const { default: ImportResults, ApiError } = await server.ssrLoadModule('/src/ImportResults.jsx');
  const summary = { records: 2, created: 0, checked: 2, errors: 0, skipped: 0, warnings: 1, duration_ms: 1250 };
  const row = { batch: 1, doctype: 'ilL-Rel-Profile Lens', catalog_name: 'CATALOG-NAME', name: 'saved / name', status: 'checked', warnings: ['Review <script>alert(1)</script>'] };
  const renderResult = response => renderToStaticMarkup(React.createElement(ImportResults, { response: { summary, errors: [], results: [row], log: 'LOG / 1', ...response }, onSelect() {} }));
  const passed = renderResult({ status: 'Passed' });
  assert.ok(passed.includes('All 2 records passed. Nothing was saved'));
  assert.ok(!passed.includes('href="/app/ill-rel-profile-lens/'));
  assert.ok(passed.includes('/app/ill-catalog-import/LOG%20%2F%201'));
  assert.ok(passed.includes('&lt;script&gt;') && !passed.includes('<script>'));
  const failed = renderResult({ status: 'Failed', summary: { ...summary, errors: 1, skipped: 1 }, errors: ['Permission denied'], results: [{ ...row, status: 'error' }, { ...row, status: 'skipped' }] });
  assert.ok(failed.includes('2 problems. Nothing was saved.'));
  assert.ok(failed.includes('Edit CATALOG-NAME') && failed.includes('Permission denied') && failed.includes('skipped'));
  const created = { ...row, status: 'created' };
  const imported = renderResult({ status: 'Imported', summary: { ...summary, created: 2 }, results: [created], errors: ['Audit receipt unavailable'], log: null });
  assert.ok(imported.includes('Created 2 records in ERPNext.'));
  assert.ok(imported.includes('/app/ill-rel-profile-lens/saved%20%2F%20name'));
  assert.ok(imported.includes('target="_blank" rel="noopener"'));
  assert.ok(imported.includes('Audit receipt unavailable'));
  const rolledBack = renderResult({ status: 'Rolled Back', results: [created] });
  assert.ok(rolledBack.includes('Everything was rolled back'));
  assert.ok(!rolledBack.includes('href="/app/ill-rel-profile-lens/'));
  assert.ok(renderResult({ status: 'Refused', errors: ['Run Check again'] }).includes('Run Check again'));
  assert.ok(renderResult({ status: 'Error' }).includes('See audit log LOG / 1'));
  const sessionError = renderToStaticMarkup(React.createElement(ApiError, { error: { message: 'Reload the page', sessionExpired: true } }));
  assert.ok(sessionError.includes('href="/login?redirect-to=/catalog-builder"'));
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
    const calls = [];
    globalThis.fetch = async (url, options) => {
      calls.push({ url, options });
      return { ok: true, json: async () => ({ message: { status: 'Passed' } }) };
    };
    mount('erp-root', { csrfToken: 'test-csrf' });
    assert.equal(mounted.mode, 'erp');
    await mounted.api.reference(true);
    assert.ok(calls[0].url.endsWith('.reference?refresh=1'));
    await mounted.api.record('Item', 'A&B +/?');
    assert.equal(new URL(calls[1].url, 'https://example.test').searchParams.get('name'), 'A&B +/?');
    await mounted.api.check({ records: {} });
    assert.equal(calls[2].options.headers['X-Frappe-CSRF-Token'], 'test-csrf');
    assert.equal(mounted.loadReference, undefined);
  } finally {
    ReactDOM.createRoot = originalCreateRoot;
    globalThis.fetch = originalFetch;
    if (originalDocument === undefined) delete globalThis.document;
    else globalThis.document = originalDocument;
  }
  console.log('Rendered Vercel/ERP catalog shells, all seven product examples, and legacy editor; verified API mounting, results, audit links, and session recovery.');
} finally { await server.close(); }
