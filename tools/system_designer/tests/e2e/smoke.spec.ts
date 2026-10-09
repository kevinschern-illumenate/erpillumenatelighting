import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, test } from '@playwright/test';

// Smoke test of the committed bundle exactly as the portal template loads it.
const OUT = resolve(import.meta.dirname, '../../../../illumenate_lighting/public/system_designer');
const ORIGIN = 'http://portal.test';

test('the committed bundle mounts the placeholder', async ({ page }) => {
  await page.route(`${ORIGIN}/**`, async (route) => {
    const path = new URL(route.request().url()).pathname;
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
  await page.goto(`${ORIGIN}/portal/schedules/SCH-0001/design`);
  await expect(page.getByRole('heading', { name: 'ilLumenate System Designer' })).toBeVisible();
  await expect(page.getByTestId('schedule-name')).toHaveText('Schedule SCH-0001');
  expect(errors).toEqual([]);
});
