import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, test, type Page } from '@playwright/test';

// Smoke test of the committed bundle exactly as the portal template loads it.
const OUT = resolve(import.meta.dirname, '../../../../illumenate_lighting/public/system_designer');
// HTTPS like the portal: crypto.randomUUID needs a secure context.
const ORIGIN = 'https://portal.test';
const EXPANSION = JSON.parse(
  readFileSync(resolve(import.meta.dirname, '../../packages/core-schemas/fixtures/open-design/expected.json'), 'utf8'),
);
const CATALOG = JSON.parse(
  readFileSync(resolve(import.meta.dirname, '../../packages/core-schemas/fixtures/catalog/payload.json'), 'utf8'),
);
const OPEN = {
  schedule: {
    name: 'SCH-0001',
    schedule_name: 'Test house',
    version: 1,
    is_locked: false,
    status: 'Draft',
    project: null,
  },
  ...EXPANSION,
  design: null,
  design_meta: null,
  reconcile: null,
  catalog_hash: 'c'.repeat(64),
  review_requirement: { required: false, reasons: [], satisfied: true },
  permissions: { can_edit: true, can_review: false, can_view_pricing: false },
  settings: { terms_text: 'Design aid. Verify against product documentation and local code.' },
  newer_version: null,
};

async function serve(page: Page) {
  await page.route(`${ORIGIN}/**`, async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/method/x.open_design')
      return route.fulfill({ json: { message: { success: true, data: OPEN } } });
    if (path === '/api/method/x.get_catalog')
      return route.fulfill({ json: { message: { success: true, data: { hash: OPEN.catalog_hash, ...CATALOG } } } });
    if (path === '/api/method/x.eligible_supplies')
      return route.fulfill({
        json: {
          message: {
            success: true,
            data: [{ catalog_id: 'drv:TEST-PSU-96', item_code: 'TEST-PSU-96', rank: 2, location_rating: 'Dry' }],
          },
        },
      });
    if (path === '/portal/schedules/SCH-0001/design') {
      return route.fulfill({
        contentType: 'text/html',
        body: `<!doctype html><link rel="stylesheet" href="/assets/illumenate_lighting/system_designer/designer.css">
<div id="ill-system-designer-root"></div>
<script type="module">
import "/assets/illumenate_lighting/system_designer/designer.js";
window.IllSystemDesigner.mount(document.getElementById("ill-system-designer-root"), {schedule: "SCH-0001", csrfToken: "t", apiBase: "/api/method/x"});
</script>`,
      });
    }
    const file = path.replace('/assets/illumenate_lighting/system_designer/', '');
    const body = readFileSync(resolve(OUT, file));
    return route.fulfill({ body, contentType: file.endsWith('.css') ? 'text/css' : 'text/javascript' });
  });
}

test('the committed bundle opens a schedule in the guided shell', async ({ page }) => {
  await serve(page);
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') errors.push(message.text());
  });
  await page.goto(`${ORIGIN}/portal/schedules/SCH-0001/design`);
  await expect(page.getByRole('heading', { name: 'ilLumenate System Designer' })).toBeVisible();
  await expect(page.getByTestId('schedule-name')).toHaveText('Test house · Version 1');
  await page.getByRole('button', { name: 'Accept and continue' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByTestId('design-size')).toContainText('runs in');
  await page.getByRole('button', { name: 'Continue' }).click();
  await expect(page.getByRole('heading', { name: 'Spaces', level: 2 })).toBeVisible();
  expect(errors).toEqual([]);
});

test('runs are dragged onto a supply output on the power board', async ({ page }) => {
  await serve(page);
  await page.goto(`${ORIGIN}/portal/schedules/SCH-0001/design`);
  await page.getByRole('button', { name: 'Accept and continue' }).click();
  await page.getByRole('button', { name: 'Spaces' }).click();
  await page.getByTestId('space-space-kitchen').getByRole('button', { name: 'Add cabinet' }).click();
  await page.getByRole('button', { name: 'Power' }).click();
  await page.getByTestId('board-C-1').getByRole('button', { name: 'Add supply' }).click();
  await page.getByRole('button', { name: 'Add Test 96 W supply' }).click();
  await page.getByTestId('pool-a1linear:1:1').dragTo(page.getByTestId('output-PS-1-OUT1'));
  await expect(page.getByTestId('output-PS-1-OUT1')).toContainText('A1-1.1 · 26.4 W');
  await expect(page.getByTestId('assigned-count')).toContainText('1 of');
  // A second 26.4 W run fits; a third would pass the 76.8 W usable rating and is refused with the reason.
  await page.getByTestId('pool-a1linear:1:2').dragTo(page.getByTestId('output-PS-1-OUT1'));
  await page.getByTestId('pool-a1linear:2:1').dragTo(page.getByTestId('output-PS-1-OUT1'));
  await expect(page.getByRole('alert')).toHaveText('PS-1/OUT1 would carry 79.2 W of its 76.8 W usable');
});

test('the Check step runs the engine in a worker and sizes an assigned run', async ({ page }) => {
  await serve(page);
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.goto(`${ORIGIN}/portal/schedules/SCH-0001/design`);
  await page.getByRole('button', { name: 'Accept and continue' }).click();
  await page.getByRole('button', { name: 'Spaces' }).click();
  await page.getByTestId('space-space-kitchen').getByRole('button', { name: 'Add cabinet' }).click();
  await page.getByRole('button', { name: 'Power' }).click();
  await page.getByTestId('board-C-1').getByRole('button', { name: 'Add supply' }).click();
  await page.getByRole('button', { name: 'Add Test 96 W supply' }).click();
  await page.getByTestId('pool-a1linear:1:1').dragTo(page.getByTestId('output-PS-1-OUT1'));
  await page.getByRole('navigation').getByRole('button', { name: 'Check' }).click();
  await expect(page.getByTestId('result-a1linear:1:1')).toContainText('18/2 CL3R');
  await expect(page.getByTestId('check-UNRESOLVED_REF-PS-1')).toContainText('PS-1 is not on a panel circuit yet.');
  expect(errors).toEqual([]);
});
