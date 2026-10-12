import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { expect, test, type Browser, type Page } from '@playwright/test';

// The Phase 4 commerce loop through the committed bundle (WP-4.6): a dealer designs and asks for
// review, an Applications Engineer approves, the dealer writes the design back, and the schedule
// can be ordered. The server is a small in-memory fake of the H6 endpoints; the installed tests in
// system_design/test_designs.py cover the same steps against Frappe.
const OUT = resolve(import.meta.dirname, '../../../../illumenate_lighting/public/system_designer');
const ORIGIN = 'https://portal.test';
const API = '/api/method/x.';
const EXPANSION = JSON.parse(
  readFileSync(resolve(import.meta.dirname, '../../packages/core-schemas/fixtures/open-design/expected.json'), 'utf8'),
);
const CATALOG = JSON.parse(
  readFileSync(resolve(import.meta.dirname, '../../packages/core-schemas/fixtures/catalog/payload.json'), 'utf8'),
);
const HASH = 'c'.repeat(64);
const DEALER = { can_edit: true, can_review: false, can_view_pricing: false, can_engineer: false };
const REVIEWER = { can_edit: false, can_review: true, can_view_pricing: false, can_engineer: true };

interface Server {
  design: unknown;
  meta: Record<string, unknown> | null;
  deliverables: Record<string, unknown>[];
  calls: string[];
  written: boolean;
  /** Rows the fake `writeback_apply` received. */
  accepted: string[];
}

function requirement(server: Server) {
  const approved = server.meta?.status === 'Approved';
  return {
    required: true,
    reasons: [{ code: 'LOAD_OVER_THRESHOLD', detail: '1800 W' }],
    satisfied: approved,
    approved_design: approved ? 'SYSD-1' : null,
  };
}

const ok = (data: unknown) => ({ json: { message: { success: true, data } } });

async function serve(page: Page, server: Server, permissions: typeof DEALER, user: string) {
  await page.route(`${ORIGIN}/**`, async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path.startsWith(API)) {
      const method = path.slice(API.length);
      server.calls.push(method);
      const form = new URLSearchParams(request.postData() ?? '');
      switch (method) {
        case 'open_design':
          return route.fulfill(
            ok({
              schedule: {
                name: 'SCH-0001',
                schedule_name: 'Test house',
                version: 1,
                is_locked: false,
                status: 'READY',
              },
              ...EXPANSION,
              design: server.design,
              design_meta: server.meta,
              reconcile: null,
              catalog_hash: HASH,
              review_requirement: requirement(server),
              permissions,
              settings: { terms_text: 'Design aid. Verify against product documentation and local code.' },
              newer_version: null,
              user,
              deliverables: server.deliverables,
            }),
          );
        case 'get_catalog':
          return route.fulfill(ok({ hash: HASH, ...CATALOG }));
        case 'log_event':
          return route.fulfill(ok({ event_key: null }));
        case 'eligible_supplies':
          return route.fulfill(ok([{ catalog_id: 'drv:TEST-PSU-96', item_code: 'TEST-PSU-96', rank: 2 }]));
        case 'save_design': {
          server.design = JSON.parse(form.get('design_json')!);
          const modified = `2026-10-09 12:0${server.calls.filter((call) => call === 'save_design').length}:00`;
          server.meta = {
            name: 'SYSD-1',
            revision: 'A',
            status: 'Draft',
            modified,
            schedule_version: 1,
            is_current: true,
            terms_accepted: true,
          };
          return route.fulfill(
            ok({ name: 'SYSD-1', revision: 'A', modified, build_hash: 'b'.repeat(64), summary: {} }),
          );
        }
        case 'verify_design':
          return route.fulfill(ok({ ok: true, mismatches: [] }));
        case 'list_comments':
          return route.fulfill(ok([]));
        case 'upload_deliverable': {
          const row = {
            name: `row-${server.deliverables.length + 1}`,
            kind: 'Riser PDF',
            variant: 'Tabloid',
            file: '/private/files/riser.pdf',
            file_sha256: 'f'.repeat(64),
            revision: 'A',
            build_hash: 'b'.repeat(64),
            created_by: user,
            created_on: '2026-10-09 12:10:00',
          };
          server.deliverables.push(row);
          return route.fulfill(ok({ file_url: row.file, row }));
        }
        case 'request_review':
          expect(form.get('error_count')).toBe('0');
          server.meta = { ...server.meta, status: 'In Review', review_request: 'ILL-REQ-1' };
          return route.fulfill(ok({ request: 'ILL-REQ-1', reviewer: 'Ada Engineer', design_meta: server.meta }));
        case 'review_decide':
          server.meta = { ...server.meta, status: form.get('decision'), approved_by: user };
          return route.fulfill(ok({ review: 'DR-1', status: form.get('decision'), design_meta: server.meta }));
        case 'writeback_preview':
          return route.fulfill(
            ok({
              add: server.written
                ? []
                : [
                    {
                      key: 'Supply:TEST-PSU-96',
                      role: 'Supply',
                      item_code: 'TEST-PSU-96',
                      item_name: 'Test 96 W supply',
                      qty: 1,
                      location: 'C-1',
                    },
                  ],
              update: [],
              remove: [],
              replaces_configurator_lines: [],
              blocked: [],
              error_count: 0,
              can_apply: true,
            }),
          );
        case 'writeback_apply':
          server.accepted = JSON.parse(form.get('accepted_keys')!);
          server.written = true;
          return route.fulfill(ok({ added: server.accepted.length, updated: 0, removed: 0, replaced: 0 }));
        default:
          return route.fulfill({
            status: 404,
            json: { message: { success: false, code: 'NOT_FOUND', error: method } },
          });
      }
    }
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
    const type = file.endsWith('.css') ? 'text/css' : file.endsWith('.ttf') ? 'font/ttf' : 'text/javascript';
    return route.fulfill({ body: readFileSync(resolve(OUT, file)), contentType: type });
  });
}

async function openAs(browser: Browser, server: Server, permissions: typeof DEALER, user: string) {
  const context = await browser.newContext({ acceptDownloads: true });
  const page = await context.newPage();
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await serve(page, server, permissions, user);
  await page.goto(`${ORIGIN}/portal/schedules/SCH-0001/design`);
  return { context, page, errors };
}

const step = (page: Page, name: string) => page.getByRole('navigation').getByRole('button', { name }).click();

async function keepRiser(page: Page) {
  await step(page, 'Views');
  await page.getByRole('button', { name: 'Draw riser' }).click();
  await expect(page.getByRole('img', { name: /Riser sheet/ })).toBeVisible();
  await page.getByRole('button', { name: 'Download PDF' }).click();
  await expect(page.getByTestId('views-notice')).toHaveText('Downloaded and kept on revision A.');
}

test('design, review, approve, write back, then the schedule can be ordered', async ({ browser }) => {
  test.setTimeout(120_000);
  const server: Server = { design: null, meta: null, deliverables: [], calls: [], written: false, accepted: [] };

  // The dealer lays out one run, saves, keeps the riser and asks for review.
  const dealer = await openAs(browser, server, DEALER, 'dealer@example.com');
  let page = dealer.page;
  await page.getByRole('button', { name: 'Accept and continue' }).click();
  await page.getByRole('button', { name: 'Spaces' }).click();
  await page.getByTestId('space-space-kitchen').getByRole('button', { name: 'Add cabinet' }).click();
  await page.getByRole('button', { name: 'Power' }).click();
  await page.getByTestId('board-C-1').getByRole('button', { name: 'Add supply' }).click();
  await page.getByRole('button', { name: 'Add Test 96 W supply' }).click();
  await page.getByTestId('pool-a1linear:1:1').dragTo(page.getByTestId('output-PS-1-OUT1'));
  await page.getByRole('button', { name: 'Save', exact: true }).click();
  await expect.poll(() => server.meta?.name).toBe('SYSD-1');
  await keepRiser(page);
  await step(page, 'Finish');
  await expect(page.getByTestId('review-requirement')).toContainText('Review is required');
  await page.getByRole('button', { name: 'Request review' }).click();
  await expect(page.getByTestId('review-notice')).toHaveText('Review requested. Ada Engineer will review revision A.');
  expect(dealer.errors).toEqual([]);
  await dealer.context.close();

  // The Applications Engineer opens the same design, keeps the riser and approves it.
  const reviewer = await openAs(browser, server, REVIEWER, 'ae@example.com');
  page = reviewer.page;
  await keepRiser(page);
  await step(page, 'Finish');
  await expect(page.getByTestId('reviewer-panel')).toBeVisible();
  await page.getByRole('button', { name: 'Approve', exact: true }).click();
  await expect(page.getByTestId('review-notice')).toHaveText('Revision A is approved.');
  expect(reviewer.errors).toEqual([]);
  await reviewer.context.close();

  // The dealer adds the design's lines to the schedule; the approved design satisfies the gate.
  const back = await openAs(browser, server, DEALER, 'dealer@example.com');
  page = back.page;
  await step(page, 'Finish');
  await expect(page.getByTestId('review-gate')).toHaveText(
    'Ordering is allowed: the approved design matches the schedule.',
  );
  await page.getByRole('button', { name: 'Show the changes' }).click();
  await page.getByRole('button', { name: 'Add 1 change to the schedule' }).click();
  await expect(page.getByTestId('writeback-notice')).toHaveText('The schedule is updated: 1 added.');
  await expect(page.getByTestId('writeback-in-sync')).toBeVisible();
  expect(server.accepted).toEqual(['Supply:TEST-PSU-96']);
  expect(server.calls).toEqual(expect.arrayContaining(['request_review', 'review_decide', 'writeback_apply']));
  expect(back.errors).toEqual([]);
  await back.context.close();
});
