// Controlled browser regressions against the committed ERP bundle.
// Uses the existing Playwright install: npm ci --prefix tests/portal_e2e.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
const { chromium, expect } = createRequire(new URL('../../../tests/portal_e2e/package.json', import.meta.url))('@playwright/test');
const assets = new URL('../../../illumenate_lighting/public/catalog_builder/', import.meta.url);
const browser = await chromium.launch({ executablePath: process.env.BROWSER_EXECUTABLE || undefined, args: ['--no-sandbox'] });
const doctype = 'ilL-Extrusion-Kit-Template';
const catalog = { schema_version: 2, product_type: 'extrusion-kit', series_name: 'Browser regression', add_to_reference: true,
  records: { [doctype]: [{ template_code: 'UI-KIT', template_name: 'UI test' }] }, external_links: {} };
const row = { batch: 1, doctype, catalog_name: 'UI-KIT', name: 'UI-KIT', status: 'checked', message: '', warnings: [] };
const passed = { status: 'Passed', log: 'LOG-CHECK', catalog_hash: 'checked-hash', errors: [], results: [row],
  summary: { records: 1, checked: 1, created: 0, errors: 0, skipped: 0, warnings: 0, duration_ms: 21 } };
const imported = { ...passed, status: 'Imported', log: 'LOG-IMPORT', results: [{ ...row, status: 'created' }], summary: { ...passed.summary, checked: 0, created: 1 } };
const reference = { source: 'live', doctypes: { [doctype]: { source: 'live', records: {} } } };
const json = (route, message) => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ message }) });
async function open(draft = catalog, { ready = true } = {}) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const state = { calls: [], check: route => json(route, passed), import_catalog: route => json(route, imported), reference: route => json(route, reference), history: route => json(route, []), design_readiness: route => json(route, { incomplete: 0, total: 1 }) };
  await context.addInitScript(draft => localStorage.setItem('illumenate-product-catalog-v2', JSON.stringify({ active: 'extrusion-kit', drafts: { 'extrusion-kit': draft } })), draft);
  await context.route('http://catalog.test/**', async route => {
    const url = new URL(route.request().url());
    if (url.pathname.startsWith('/api/method/')) {
      const method = url.pathname.split('.').at(-1);
      state.calls.push({ method, body: route.request().postDataJSON() });
      return state[method](route);
    }
    if (url.pathname.endsWith('.js') || url.pathname.endsWith('.css')) return route.fulfill({ contentType: url.pathname.endsWith('.js') ? 'text/javascript' : 'text/css', body: readFileSync(new URL(url.pathname.slice(1), assets)) });
    return route.fulfill({ contentType: 'text/html', body: '<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/catalog-builder.css"></head><body><div id="builder"></div><script src="/catalog-builder.js"></script><script>IllCatalogBuilder.mount("builder", {csrfToken:"test-token"})</script></body></html>' });
  });
  const page = await context.newPage();
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.goto('http://catalog.test/catalog-builder');
  const check = page.getByRole('button', { name: 'Check in ERPNext', exact: true });
  const importButton = page.getByRole('button', { name: 'Import to ERPNext', exact: true });
  if (ready) await expect(check).toBeEnabled(); else await expect(page.locator('.grid-top')).toBeVisible();
  return { context, state, page, check, importButton, errors };
}
try {
  {
    // Bulk row tools: shift-click checking, Set field, Delete all in a child table, Clear all for a DocType.
    const kits = Array.from({ length: 6 }, (_, i) => ({ template_code: `UI-KIT-${i + 1}`, template_name: `Kit ${i + 1}`,
      allowed_options: i ? [] : [{ option_type: 'Finish' }, { option_type: 'Lens' }] }));
    const { context, page, errors } = await open({ ...catalog, records: { [doctype]: kits } }, { ready: false });
    if (await page.locator('.catalog-types-toggle').isVisible()) await page.locator('.catalog-types-toggle').click();
    await page.locator('.catalog-sidebar button', { has: page.locator('.catalog-type-name', { hasText: /^Extrusion-Kit-Template$/ }) }).click();
    const grid = page.locator('.grid-top');
    await grid.getByLabel('Select row 2', { exact: true }).click();
    await grid.getByLabel('Select row 5', { exact: true }).click({ modifiers: ['Shift'] });
    await expect(grid.locator('.grid-status')).toContainText('4 rows checked');
    await grid.getByLabel('Select row 3', { exact: true }).click({ modifiers: ['Shift'] });
    await expect(grid.locator('.grid-status')).toContainText('1 row checked', { message: 'shift-clicking a checked row unchecks rows 5 back to 3' });
    await grid.getByLabel('Select row 6', { exact: true }).click();
    await expect(grid.locator('.grid-status')).toContainText('2 rows checked');
    await grid.locator('summary', { hasText: 'Set field on 2' }).click();
    await grid.locator('.grid-set-field select').selectOption('warranty_years');
    await grid.locator('.grid-set-field input').fill('5');
    await grid.getByRole('button', { name: 'Apply to 2 rows' }).click();
    for (const [row, value] of [[2, '5'], [6, '5'], [3, ''], [1, '']]) await expect(grid.getByLabel(`Warranty (Years), row ${row}`, { exact: true })).toHaveValue(value);
    await grid.getByLabel('Allowed Options, row 1: 2 rows', { exact: true }).click();
    const child = page.locator('.grid-nested');
    await child.getByRole('button', { name: 'Delete all', exact: true }).click();
    await child.getByRole('button', { name: 'Click again to delete all 2', exact: true }).click();
    await expect(grid.getByLabel('Allowed Options, row 1: 0 rows', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Clear all', exact: true }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Clear Extrusion-Kit-Template', exact: true }).click();
    await expect(page.locator('.catalog-bar-title p')).toHaveText('0 records');
    await page.getByRole('button', { name: '↶ Undo' }).click();
    await expect(page.locator('.catalog-bar-title p')).toHaveText('6 records');
    assert.deepEqual(errors, []);
    await context.close();
    console.log('Passed: shift-click row ranges, Set field on checked rows, Delete all child rows, Clear all with undo.');
  }
  {
    const { context, state, page, check, importButton, errors } = await open();
    assert.equal(state.calls.filter(call => call.method === 'history').length, 0);
    let release;
    const hold = new Promise(resolve => { release = resolve; });
    state.check = async route => { await hold; return json(route, passed); };
    await check.evaluate(button => { button.click(); button.click(); });
    await expect(page.getByText('Checking 1 records…')).toBeVisible();
    for (const name of ['Open YAML', 'Load example', 'Clear draft', 'Family expansion editor']) await expect(page.getByRole('button', { name, exact: true })).toBeDisabled();
    await expect(page.getByLabel('Catalog name', { exact: true })).toBeDisabled();
    for (const button of await page.getByRole('navigation', { name: 'Product families' }).getByRole('button').all()) await expect(button).toBeDisabled();
    release();
    await expect(importButton).toBeEnabled();
    assert.equal(state.calls.filter(call => call.method === 'check').length, 1);
    const expected = structuredClone(catalog); delete expected.add_to_reference;
    assert.deepEqual(state.calls.find(call => call.method === 'check').body, { catalog: expected });
    const name = page.getByLabel('Catalog name', { exact: true });
    await name.fill('Edited');
    await expect(importButton).toBeDisabled();
    await expect(page.getByText('Catalog changed since the last check — run Check again')).toBeVisible();
    await name.fill(catalog.series_name);
    await expect(importButton).toBeDisabled();
    await check.click(); await expect(importButton).toBeEnabled();
    await importButton.click();
    await expect(page.getByRole('dialog')).toContainText('1 Extrusion-Kit-Template');
    await expect(page.getByRole('dialog')).toContainText('This cannot be undone from the builder.');
    await page.keyboard.press('Escape'); await expect(page.getByRole('dialog')).toHaveCount(0);
    assert.equal(state.calls.filter(call => call.method === 'import_catalog').length, 0);
    await importButton.click();
    state.reference = route => route.abort();
    await page.getByRole('dialog').getByRole('button', { name: 'Import to ERPNext', exact: true }).click();
    await expect(page.getByText('Created 1 records in ERPNext.')).toBeVisible();
    // The refresh failure is flagged on the readiness button and explained in its panel.
    await expect(page.locator('.catalog-readiness-toggle')).toContainText('Existing ERPNext records did not load');
    await page.locator('.catalog-readiness-toggle').click();
    await expect(page.locator('.catalog-review [role=alert]')).toContainText('Failed to fetch');
    assert.deepEqual(state.calls.find(call => call.method === 'import_catalog').body, { catalog: expected, expected_hash: 'checked-hash' });
    await expect(importButton).toBeDisabled();
    await expect(page.getByRole('link', { name: 'UI-KIT', exact: true })).toHaveAttribute('href', '/app/ill-extrusion-kit-template/UI-KIT');
    state.history = route => json(route, [{ name: 'LOG-IMPORT', creation: '2026-10-05 14:00:00', mode: 'Import', status: 'Imported', series_name: catalog.series_name, record_count: 1, created_count: 1, error_count: 0, skipped_count: 0, warning_count: 0 }]);
    await page.locator('.catalog-history summary').click();
    await expect(page.locator('.catalog-history')).toContainText('1 created');
    await expect(page.locator('.catalog-history a')).toHaveAttribute('href', '/app/ill-catalog-import/LOG-IMPORT');
    await page.getByRole('button', { name: 'Start a new draft', exact: true }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Start a new draft', exact: true }).click();
    await expect(page.locator('.catalog-results')).toHaveCount(0);
    await expect(check).toBeDisabled();
    assert.deepEqual(errors, []);
    await context.close();
    console.log('Passed: exact payload/hash, double-click guard, busy controls, edit invalidation, confirmation, success after refresh failure, history, new draft.');
  }
  {
    const { context, state, page, check, importButton, errors } = await open();
    state.check = route => route.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({ exc_type: 'CSRFTokenError' }) });
    await check.click();
    await expect(page.locator('.catalog-run [role=alert]')).toContainText('Reload the page');
    await expect(page.locator('.catalog-run a')).toHaveAttribute('href', '/login?redirect-to=/catalog-builder');
    await expect(page.getByLabel('Catalog name', { exact: true })).toBeEnabled();
    state.check = route => json(route, { ...passed, status: 'Failed', summary: { ...passed.summary, errors: 1, skipped: 1 }, results: [{ ...row, status: 'error', message: 'Invalid value', warnings: ['Review this value'] }, { ...row, status: 'skipped', message: 'Dependency failed' }] });
    await check.click();
    await expect(page.getByText('2 problems. Nothing was saved.')).toBeVisible();
    await page.getByRole('button', { name: 'Errors', exact: true }).click();
    await expect(page.locator('.catalog-result-table tbody tr')).toHaveCount(1);
    await page.getByRole('button', { name: 'Edit UI-KIT', exact: true }).click();
    // The table view focuses the record's first cell; cards focus the record card.
    await expect(page.getByLabel('Template Code, row 1', { exact: true })).toBeFocused();
    await expect(page.locator('.catalog-editor h2')).toHaveText('Extrusion-Kit-Template');
    await page.getByRole('button', { name: 'Skipped', exact: true }).click();
    await expect(page.locator('.catalog-result-table')).toContainText('Dependency failed');
    await page.getByRole('button', { name: 'Warnings', exact: true }).click();
    await expect(page.locator('.catalog-result-table')).toContainText('Review this value');
    state.check = route => json(route, passed);
    await check.click(); await expect(importButton).toBeEnabled();
    state.import_catalog = route => route.abort();
    await importButton.click();
    await page.getByRole('dialog').getByRole('button', { name: 'Import to ERPNext', exact: true }).click();
    await expect(page.getByText(/Import confirmation was not received/)).toBeVisible();
    await expect(page.getByLabel('Catalog name', { exact: true })).toHaveValue(catalog.series_name);
    await expect(importButton).toBeDisabled();
    assert.equal(state.calls.filter(call => call.method === 'import_catalog').length, 1);
    state.history = route => route.abort();
    await page.locator('.catalog-readiness-toggle').click();
    await page.locator('.catalog-history summary').click();
    await expect(page.getByRole('button', { name: 'Retry history' })).toBeVisible();
    state.history = route => json(route, []);
    await page.getByRole('button', { name: 'Retry history' }).click();
    await expect(page.getByText('No recent checks or imports.')).toBeVisible();
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Mobile page must not overflow horizontally');
    assert.deepEqual(errors, []);
    await context.close();
    console.log('Passed: CSRF/login recovery, error selection/focus, result filters, unknown import outcome without retry, preserved draft, history retry, mobile layout.');
  }
} finally { await browser.close(); }
