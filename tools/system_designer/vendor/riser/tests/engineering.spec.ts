import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { readFileSync } from 'node:fs';
import Papa from 'papaparse';
const seedProducts = JSON.parse(readFileSync('src/data/products.example.json', 'utf8')) as Record<
  string,
  unknown
>[];
function flatten(row: Record<string, unknown>, prefix = ''): Record<string, unknown> {
  return Object.assign(
    {},
    ...Object.entries(row).map(([k, v]) => {
      const key = prefix ? `${prefix}.${k}` : k;
      return v && typeof v === 'object' && !Array.isArray(v)
        ? flatten(v as Record<string, unknown>, key)
        : { [key]: Array.isArray(v) ? JSON.stringify(v) : v };
    }),
  );
}
const exportCsv = (rows: Record<string, unknown>[]) => Papa.unparse(rows.map((r) => flatten(r)));

test('full demo flows through review, worker drawing, pins and downloads', async ({ page }) => {
  test.setTimeout(90000);
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto('/#/tables');
  await page.getByRole('button', { name: 'Load complete example' }).click();
  await page.getByRole('tab', { name: /Equipment/ }).click();
  await expect(page.locator('[role="row"][row-id]')).toHaveCount(6);
  await page.getByRole('link', { name: /Review/ }).click();
  await expect(page.getByRole('heading', { name: 'Derived runs', exact: true })).toBeVisible();
  await expect(page.locator('tbody tr')).toHaveCount(14);
  await page.getByRole('tab', { name: 'DMX patch', exact: true }).click();
  await expect(page.getByText('(proposed)', { exact: false })).toHaveCount(2);
  await page.getByRole('button', { name: 'Auto-patch', exact: true }).click();
  await expect(page.getByText('(proposed)', { exact: false })).toHaveCount(0);
  await page.getByRole('link', { name: /Drawing/ }).click();
  await expect(page.locator('.drawing-paper svg')).toBeVisible({ timeout: 20000 });
  await expect(page.getByRole('status').filter({ hasText: /sheets ·/ })).toBeVisible();
  await page.screenshot({ path: 'test-results/complete-drawing.png', fullPage: true });
  const node = page.locator('[data-node="ps-1"]');
  await node.scrollIntoViewIfNeeded();
  const box = await node.boundingBox();
  expect(box).not.toBeNull();
  await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
  await page.mouse.down();
  await page.mouse.move(box!.x + box!.width / 2 + 12, box!.y + box!.height / 2 - 12, { steps: 5 });
  await page.mouse.up();
  await expect(page.getByRole('button', { name: 'Reset all pins' })).toBeEnabled();
  await expect(page.getByText('Saved locally', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button', { name: 'Reset all pins' })).toBeEnabled();
  await expect(page.locator('.drawing-paper svg')).toBeVisible({ timeout: 20000 });
  await page.getByRole('button', { name: 'Reset all pins' }).click();
  await expect(page.getByRole('button', { name: 'Reset all pins' })).toBeDisabled();
  await page.getByRole('button', { name: 'Symbol gallery', exact: true }).click();
  await expect(page.locator('.drawing-paper')).toContainText('ATTR:');
  await page.screenshot({ path: 'test-results/symbol-gallery.png', fullPage: true });
  await page.getByRole('link', { name: /Export/ }).click();
  await expect(page.getByRole('button', { name: 'Download PDF', exact: true })).toBeEnabled({
    timeout: 20000,
  });
  for (const [button, extension] of [
    ['Download PDF', '.pdf'],
    ['Download DXF ZIP', '-dxf.zip'],
    ['Download tiled DXF', '-tiled.dxf'],
    ['Download CSV schedules', '-schedules.zip'],
  ]) {
    const pending = page.waitForEvent('download');
    await page.getByRole('button', { name: button!, exact: true }).click();
    const download = await pending;
    expect(download.suggestedFilename()).toContain(extension!);
    const path = await download.path();
    expect((await readFile(path!)).length).toBeGreaterThan(300);
  }
  expect(errors).toEqual([]);
});

test('validates a mapped 50-row CSV and commits the ERP demo with library undo', async ({
  page,
}) => {
  await page.goto('/#/libraries');
  const example = seedProducts.find((p) => p.category === 'psu')!;
  const csv = exportCsv(
    Array.from({ length: 50 }, (_, i) => ({ ...example, id: `csv-${i}`, sku: `CSV-${i}` })),
  ).replace(/^id,sku,/, 'id,item_code,');
  await page
    .getByLabel('Import products CSV')
    .setInputFiles({ name: 'psus.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) });
  await expect(page.locator('.import-summary')).toContainText('50 new');
  await expect(page.locator('.import-summary')).toContainText('0 errors');
  await page.getByRole('button', { name: 'Commit import' }).click();
  await expect(page.getByText('50 rows imported.')).toBeVisible();
  await page.getByRole('tab', { name: 'ERPNext Sync' }).click();
  await page.getByRole('button', { name: 'Preview pull' }).click();
  await expect(page.getByText(/3 added · 0 updated/)).toBeVisible();
  await page.getByRole('button', { name: 'Commit valid pull' }).click();
  await expect(page.getByText(/Pull committed/)).toBeVisible();
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await page.getByRole('button', { name: 'Preview pull' }).click();
  await expect(page.getByText(/3 added · 0 updated/)).toBeVisible();
});

test('TSV paste is atomic, row edits undo, and metric lengths use canonical feet', async ({
  page,
}) => {
  await page.goto('/#/tables');
  await page.getByRole('button', { name: 'Paste from Excel' }).click();
  await page
    .getByLabel('Excel paste buffer')
    .fill('tag\tpanel\tcircuit\nLP-X/1\tLP-X\t1\nLP-X/2\tLP-X\t2');
  await page.getByRole('button', { name: 'Add pasted rows' }).click();
  await expect(page.locator('[role="row"][row-id]')).toHaveCount(2);
  await page.getByRole('button', { name: 'Undo', exact: true }).click();
  await expect(page.locator('[role="row"][row-id]')).toHaveCount(0);
  await page.getByRole('button', { name: 'Load complete example' }).click();
  await page
    .getByRole('link', { name: /Project/ })
    .first()
    .click();
  await page.getByLabel('units', { exact: true }).selectOption('m');
  await page.getByRole('link', { name: /Tables/ }).click();
  await page.getByRole('tab', { name: /Loads/ }).click();
  const cell = page.locator('[role="row"][row-id][row-id="load-1"] [col-id="lengthFt"]');
  await expect(cell).toHaveText('3.658');
  await cell.dblclick();
  await page.locator('.ag-cell-inline-editing input').fill('6.096');
  await page.keyboard.press('Enter');
  await expect(cell).toHaveText('6.096');
  await page
    .getByRole('link', { name: /Project/ })
    .first()
    .click();
  await page.getByLabel('units', { exact: true }).selectOption('ft');
  await page.getByRole('link', { name: /Tables/ }).click();
  await page.getByRole('tab', { name: /Loads/ }).click();
  await expect(
    page.locator('[role="row"][row-id][row-id="load-1"] [col-id="lengthFt"]'),
  ).toHaveText('20');
});
