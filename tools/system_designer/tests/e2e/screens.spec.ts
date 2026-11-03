import { mkdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { test, type Page } from '@playwright/test';

// Screenshot baseline (SD-1.0, SD-4.3): every step at three widths, with the portal stylesheet loaded
// as on the real page. Runs only when SD_SCREENS_DIR names an output folder.
const DIR = process.env.SD_SCREENS_DIR;
const OUT = resolve(import.meta.dirname, '../../../../illumenate_lighting/public/system_designer');
const PORTAL_CSS = resolve(import.meta.dirname, '../../../../illumenate_lighting/public/css/portal.css');
const ORIGIN = 'https://portal.test';
const EXPANSION = JSON.parse(
  readFileSync(resolve(import.meta.dirname, '../../packages/core-schemas/fixtures/open-design/expected.json'), 'utf8'),
);
const CATALOG = JSON.parse(
  readFileSync(resolve(import.meta.dirname, '../../packages/core-schemas/fixtures/catalog/payload.json'), 'utf8'),
);
const OPEN = {
  schedule: { name: 'SCH-0001', schedule_name: 'Test house', version: 1, is_locked: false, status: 'Draft', project: 'PRJ-1' },
  ...EXPANSION,
  design: null,
  design_meta: null,
  reconcile: null,
  catalog_hash: 'c'.repeat(64),
  review_requirement: { required: false, reasons: [], satisfied: true },
  permissions: { can_edit: true, can_review: false, can_view_pricing: false },
  settings: { terms_text: 'Design aid. Verify against product documentation and local code.' },
  newer_version: null,
  title_block: { project_name: 'Lakeside residence', project_number: '', site_address: '', customer: '' },
};
const ok = (data: unknown) => ({ json: { message: { success: true, data } } });

async function serve(page: Page) {
  await page.route(`${ORIGIN}/**`, async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/method/x.open_design') return route.fulfill(ok(OPEN));
    if (path === '/api/method/x.get_catalog') return route.fulfill(ok({ hash: OPEN.catalog_hash, ...CATALOG }));
    if (path === '/api/method/x.log_event') return route.fulfill(ok({ event_key: null }));
    if (path === '/api/method/x.eligible_supplies')
      return route.fulfill(
        ok([{ catalog_id: 'drv:TEST-PSU-96', item_code: 'TEST-PSU-96', rank: 2, location_rating: 'Dry' }]),
      );
    if (path === '/assets/illumenate_lighting/css/portal.css')
      return route.fulfill({ body: readFileSync(PORTAL_CSS), contentType: 'text/css' });
    if (path === '/portal/schedules/SCH-0001/design')
      return route.fulfill({
        contentType: 'text/html',
        body: `<!doctype html><meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="/assets/illumenate_lighting/css/portal.css">
<link rel="stylesheet" href="/assets/illumenate_lighting/system_designer/designer.css">
<body style="margin:0;background:var(--ill-surface-soft);font-family:var(--ill-font-family)">
<main class="ill-portal-shell ill-portal-shell--bare"><div id="ill-system-designer-root"></div></main>
<script type="module">
import "/assets/illumenate_lighting/system_designer/designer.js";
window.IllSystemDesigner.mount(document.getElementById("ill-system-designer-root"), {schedule: "SCH-0001", csrfToken: "t", apiBase: "/api/method/x"});
</script>`,
      });
    const file = path.replace('/assets/illumenate_lighting/system_designer/', '');
    try {
      const body = readFileSync(resolve(OUT, file));
      const type = file.endsWith('.css') ? 'text/css' : file.endsWith('.ttf') ? 'font/ttf' : 'text/javascript';
      return route.fulfill({ body, contentType: type });
    } catch {
      return route.fulfill({ status: 404, body: '' });
    }
  });
}

const STEPS = ['Start', 'Spaces', 'Runs', 'Power', 'Check', 'Views', 'Finish'];
const WIDTHS = [1440, 1024, 768];

test.describe('screens', () => {
  test.skip(!DIR, 'Set SD_SCREENS_DIR to write the screenshot baseline');
  for (const width of WIDTHS)
    test(`every step at ${width}px`, async ({ page }) => {
      mkdirSync(resolve(DIR!), { recursive: true });
      await page.setViewportSize({ width, height: 900 });
      await serve(page);
      await page.goto(`${ORIGIN}/portal/schedules/SCH-0001/design`);
      await page.waitForTimeout(500);
      await page.screenshot({ path: resolve(DIR!, `${width}-00-terms.png`) });
      await page.getByRole('button', { name: 'Accept and continue' }).click();
      const steps = page.getByRole('navigation', { name: /Design steps|Design tabs/ });
      // A small board so Power, Check and Views have something to show.
      await steps.getByRole('button', { name: 'Spaces' }).click();
      await page.getByTestId('space-space-kitchen').getByRole('button', { name: 'Add cabinet' }).click();
      await steps.getByRole('button', { name: 'Power' }).click();
      await page.getByTestId('board-C-1').getByRole('button', { name: 'Add supply' }).click();
      await page.getByRole('button', { name: 'Add Test 96 W supply' }).click();
      await page.getByTestId('pool-a1linear:1:1').dragTo(page.getByTestId('output-PS-1-OUT1'));
      for (const [index, name] of STEPS.entries()) {
        await steps.getByRole('button', { name, exact: false }).first().click();
        await page.waitForTimeout(300);
        await page.screenshot({ path: resolve(DIR!, `${width}-${index + 1}-${name.toLowerCase()}.png`), fullPage: true });
      }
    });
});
