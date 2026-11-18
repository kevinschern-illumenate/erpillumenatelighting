// Automatic Webflow push line on the Webflow Product form (plan 4.19, sync rebuild step 3).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const jquery = require('jquery');
const { JSDOM } = require('jsdom');

const source = fs.readFileSync(
  path.join(__dirname, '../../illumenate_lighting/public/js/webflow_auto_push.js'), 'utf8');
const API = 'illumenate_lighting.illumenate_lighting.webflow_auto_push.get_status';
const flush = async () => {
  for (let i = 0; i < 5; i += 1) await new Promise(resolve => setImmediate(resolve));
};

function setup(t, status) {
  const dom = new JSDOM('<html><body><div class="layout"></div></body></html>');
  t.after(() => dom.window.close());
  const $ = jquery(dom.window);
  const handlers = {}, calls = [];
  const frm = {
    doc: { name: 'kit-ra01' },
    layout: { wrapper: dom.window.document.querySelector('.layout') },
    is_new: () => false,
  };
  const context = {
    $,
    window: {},
    __: (text, args) => String(text).replace(/\{(\d+)\}/g, (_m, i) => String((args || [])[i])),
    frappe: {
      ui: { form: { on(doctype, callbacks) { handlers[doctype] = callbacks; } } },
      utils: { escape_html: value => String(value).replace(/</g, '&lt;').replace(/>/g, '&gt;') },
      xcall(method, args) {
        calls.push({ method, args });
        return Promise.resolve(status);
      },
    },
  };
  vm.runInNewContext(source, context);
  const refresh = () => handlers['ilL-Webflow-Product'].refresh(frm);
  return { frm, calls, refresh, text: () => dom.window.document.querySelector('.layout').textContent };
}

test('a waiting push shows when it is due, once per refresh', async t => {
  const status = { enabled: true, waiting: [{ brand: 'illumenate', due_at: '2026-11-22 10:42:00', state: 'wait' }], retries: [] };
  const ui = setup(t, status);
  ui.refresh();
  await flush();
  ui.refresh();
  await flush();
  assert.equal(ui.calls[0].method, API);
  assert.equal(ui.calls[0].args.product, 'kit-ra01');
  assert.equal(ui.text().match(/due 10:42/g).length, 1);
});

test('held, approval and retry lines; hostile text is escaped', async t => {
  const ui = setup(t, {
    enabled: false,
    waiting: [
      { brand: '<b>x</b>', due_at: '2026-11-22 10:42:00', state: 'held' },
      { brand: 'lighting_206', due_at: '2026-11-22 10:42:00', state: 'approval' },
    ],
    retries: [{ brand: 'illumenate', next_attempt_on: '2026-11-22 10:47:00' }],
  });
  ui.refresh();
  await flush();
  assert.match(ui.text(), /held: automatic pushes are off/);
  assert.match(ui.text(), /<b>x<\/b>/); // shown as text, not markup
  assert.match(ui.text(), /waits for the pending approval/);
  assert.match(ui.text(), /retries at 10:47/);
});

test('nothing waiting shows nothing', async t => {
  const ui = setup(t, { enabled: true, waiting: [], retries: [] });
  ui.refresh();
  await flush();
  assert.equal(ui.text(), '');
});
