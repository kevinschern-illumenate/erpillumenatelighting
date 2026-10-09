import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, test } from '@playwright/test';

// Smoke test of the committed bundle exactly as the portal template loads it.
const OUT = resolve(import.meta.dirname, '../../../../illumenate_lighting/public/system_designer');
// HTTPS like the portal: crypto.randomUUID needs a secure context.
const ORIGIN = 'https://portal.test';
const EXPANSION = JSON.parse(
  readFileSync(resolve(import.meta.dirname, '../../packages/core-schemas/fixtures/open-design/expected.json'), 'utf8'),
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

test('the committed bundle opens a schedule in the guided shell', async ({ page }) => {
  await page.route(`${ORIGIN}/**`, async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/method/x.open_design')
      return route.fulfill({ json: { message: { success: true, data: OPEN } } });
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
