const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const jquery = require('jquery');
const { JSDOM } = require('jsdom');

const root = path.join(__dirname, '../../illumenate_lighting/illumenate_lighting/doctype');
const productScript = fs.readFileSync(path.join(root, 'ill_webflow_product/ill_webflow_product.js'), 'utf8');

test('all DocType scripts parse even when they are excluded from the asset bundle', () => {
  for (const directory of fs.readdirSync(root, { withFileTypes: true })) {
    if (!directory.isDirectory()) continue;
    for (const name of fs.readdirSync(path.join(root, directory.name))) {
      if (!name.endsWith('.js')) continue;
      const filename = path.join(root, directory.name, name);
      new vm.Script(fs.readFileSync(filename, 'utf8'), { filename });
    }
  }
});

const PROGRESS = 'illumenate_lighting.illumenate_lighting.api.webflow_export_v2.get_sync_progress';
const SPEC_SHEET = 'illumenate_lighting.illumenate_lighting.api.webflow_export_v2.request_spec_sheet';
const BASELINE = {
  server_time: '2026-11-03 10:00:00',
  brands: [{ brand: 'illumenate', state: 'pending' }, { brand: 'lighting_206', state: 'pending' }],
  complete: false,
  failed: false,
};
const flush = () => new Promise(resolve => setImmediate(resolve));

// requestResponse answers request_spec_sheet; progress answers polls that carry "since".
function setup(t, requestResponse, progress = () => ({ ...BASELINE })) {
  const dom = new JSDOM('<html><head></head><body></body></html>');
  t.after(() => dom.window.close());
  const $ = jquery(dom.window);
  const handlers = {}, buttons = {}, queries = [], messages = [], requests = [];
  const timers = new Map(), intervals = new Map();
  let serial = 0, frozen = false;
  const frm = {
    doc: {
      name: 'demo',
      product_slug: 'demo',
      target_brands: [
        { brand: 'illumenate', enabled: 1 },
        { brand: 'lighting_206', enabled: 1 },
        { brand: 'retired', enabled: 0 },
      ],
    },
    is_new: () => false,
    add_custom_button(label, fn) { buttons[label] = fn; return $('<button>'); },
    set_query(...args) { queries.push(args); },
    reload_doc() {},
    dashboard: { set_headline_alert() {} },
  };
  vm.runInNewContext(productScript, {
    $, __: value => value, document: dom.window.document, window: dom.window,
    console,
    setTimeout(fn) { const id = ++serial; timers.set(id, fn); return id; },
    clearTimeout(id) { timers.delete(id); },
    setInterval(fn) { const id = ++serial; intervals.set(id, fn); return id; },
    clearInterval(id) { intervals.delete(id); },
    frappe: {
      ui: { form: { on(doctype, callbacks) { handlers[doctype] = callbacks; } } },
      dom: { freeze() { frozen = true; }, unfreeze() { frozen = false; } },
      utils: { escape_html: value => String(value).replace(/</g, '&lt;') },
      msgprint(message) { messages.push(message); },
      xcall(method, args) {
        requests.push({ method, args });
        if (method === SPEC_SHEET) return requestResponse(args);
        if (method === PROGRESS) return Promise.resolve(args.since ? progress(args) : { ...BASELINE });
        return Promise.resolve({});
      },
      show_alert(message) { messages.push(message); },
    },
  });
  handlers['ilL-Webflow-Product'].refresh(frm);
  return { frm, buttons, queries, timers, intervals, messages, requests, frozen: () => frozen };
}

test('the product form registers its compatible-product query during refresh', t => {
  const state = setup(t, () => new Promise(() => {}));
  assert.equal(state.queries.length, 1);
  const [field, table, query] = state.queries[0];
  assert.equal(field, 'related_product');
  assert.equal(table, 'compatible_products');
  const result = query({ target_brands: [{ brand: 'illumenate', enabled: 1 }, { brand: 'other', enabled: 0 }] });
  assert.deepEqual(Array.from(result.filters.brands), ['illumenate']);
});

test('a webhook that never responds cannot leave the product form frozen', async t => {
  const state = setup(t, () => new Promise(() => {}));
  state.buttons['Sync to Webflow']();
  assert.equal(state.frozen(), true);
  assert.equal(state.timers.size, 1);
  await flush();
  [...state.timers.values()][0]();
  assert.equal(state.frozen(), false);
  assert.equal(state.timers.size, 0);
  assert.equal(state.intervals.size, 0);
  assert.match(state.messages[0], /not been confirmed/);
});

test('webhook errors clear the deadline and release the form', async t => {
  const state = setup(t, () => Promise.reject({ message: 'Pipeline failed with status 500.' }));
  state.buttons['Sync to Webflow']();
  await flush();
  assert.equal(state.frozen(), false);
  assert.equal(state.timers.size, 0);
  assert.match(state.messages[0].message, /500/);
});

test('successful polling clears the deadline so it cannot interrupt another operation', async t => {
  const state = setup(t, async () => ({ success: true }), () => ({
    ...BASELINE, complete: true,
    brands: BASELINE.brands.map(row => ({ ...row, state: 'complete' })),
  }));
  state.buttons['Sync to Webflow']();
  await flush();
  assert.equal(state.intervals.size, 1);
  [...state.intervals.values()][0]();
  await flush();
  assert.equal(state.frozen(), false);
  assert.equal(state.intervals.size, 0);
  assert.equal(state.timers.size, 0);
  assert.equal(state.messages.length, 1);
});

test('sync requests every enabled target brand instead of a hard-coded brand', async t => {
  const state = setup(t, async () => ({ success: true }));
  state.buttons['Sync to Webflow']();
  await flush();
  const brands = state.requests.filter(row => row.method === SPEC_SHEET).map(row => row.args.brand);
  assert.deepEqual(brands, ['illumenate', 'lighting_206']);
});

test('an earlier Synced status does not complete a new sync', async t => {
  const state = setup(t, async () => ({ success: true }), () => ({
    ...BASELINE,
    brands: BASELINE.brands.map(row => ({ ...row, sync_status: 'Synced', state: 'pending' })),
  }));
  state.buttons['Sync to Webflow']();
  await flush();
  [...state.intervals.values()][0]();
  await flush();
  const poll = state.requests.filter(row => row.method === PROGRESS).pop();
  assert.equal(poll.args.since, BASELINE.server_time);
  assert.equal(state.frozen(), true);
  assert.equal(state.intervals.size, 1);
  assert.equal(state.messages.length, 0);
});

test('a failed publication job for this run stops polling and escapes its error', async t => {
  const state = setup(t, async () => ({ success: true }), () => ({
    ...BASELINE, failed: true,
    brands: [{ brand: 'illumenate', state: 'failed', error: '<b>Publication failed (500)</b>' }],
  }));
  state.buttons['Sync to Webflow']();
  await flush();
  [...state.intervals.values()][0]();
  await flush();
  assert.equal(state.frozen(), false);
  assert.equal(state.intervals.size, 0);
  assert.match(state.messages[0].message, /&lt;b>Publication failed/);
});
