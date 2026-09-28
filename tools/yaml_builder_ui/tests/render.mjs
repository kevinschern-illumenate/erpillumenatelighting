// Server rendering checks the actual JSX without requiring a connected browser.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import react from '@vitejs/plugin-react';

const schema = JSON.parse(readFileSync(new URL('../src/catalog-schema.json', import.meta.url)));
const examples = JSON.parse(readFileSync(new URL('../src/catalog-examples.json', import.meta.url)));
const server = await createServer({ configFile: false, plugins: [react()], server: { middlewareMode: true }, appType: 'custom' });
try {
  const { default: CatalogApp, RecordFields } = await server.ssrLoadModule('/src/CatalogApp.jsx');
  const shell = renderToStaticMarkup(React.createElement(CatalogApp, { onLegacy() {} }));
  for (const product of Object.values(schema.products)) assert.ok(shell.includes(product.label));
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
  console.log('Rendered catalog shell, all seven product examples, and legacy editor successfully.');
} finally { await server.close(); }
