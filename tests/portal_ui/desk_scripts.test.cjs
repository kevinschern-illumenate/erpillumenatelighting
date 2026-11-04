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

// A promise that the test settles by hand, so it controls when the server replies.
function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

// Lets pending promise callbacks and any setImmediate work run.
const flush = () => new Promise(resolve => setImmediate(resolve));

const neverSettles = () => new Promise(() => {});
const succeeds = async () => ({ success: true });
const completed = () => ({
  ...BASELINE,
  complete: true,
  brands: BASELINE.brands.map(row => ({ ...row, state: 'complete' })),
});

// requestResponse answers request_spec_sheet; progress answers polls that carry "since".
function setup(t, requestResponse = succeeds, progress = () => ({ ...BASELINE })) {
  const dom = new JSDOM('<html><head></head><body></body></html>');
  t.after(() => dom.window.close());
  const $ = jquery(dom.window);
  const handlers = {};
  const buttons = {};
  const queries = [];
  const messages = [];
  const requests = [];
  const timers = new Map();
  const intervals = new Map();
  let serial = 0;
  let frozen = false;
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
    add_custom_button(label, fn) {
      buttons[label] = fn;
      return $('<button>');
    },
    set_query(...args) {
      queries.push(args);
    },
    set_intro() {},
    reload_doc() {},
    dashboard: { set_headline_alert() {} },
  };
  vm.runInNewContext(productScript, {
    $,
    __: value => value,
    document: dom.window.document,
    window: dom.window,
    AbortController,
    console,
    setTimeout(fn) {
      const id = ++serial;
      timers.set(id, fn);
      return id;
    },
    clearTimeout(id) {
      timers.delete(id);
    },
    setInterval(fn) {
      const id = ++serial;
      intervals.set(id, fn);
      return id;
    },
    clearInterval(id) {
      intervals.delete(id);
    },
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
  const state = setup(t, neverSettles);
  assert.equal(state.queries.length, 1);
  const [field, table, query] = state.queries[0];
  assert.equal(field, 'related_product');
  assert.equal(table, 'compatible_products');
  const result = query({ target_brands: [{ brand: 'illumenate', enabled: 1 }, { brand: 'other', enabled: 0 }] });
  assert.deepEqual(Array.from(result.filters.brands), ['illumenate']);
});

test('a server call that never responds cannot leave the product form frozen', async t => {
  const state = setup(t, neverSettles);
  state.buttons['Sync to Webflow']();
  assert.equal(state.frozen(), true);
  assert.equal(state.timers.size, 1);
  await flush();

  const [deadline] = state.timers.values();
  deadline();

  assert.equal(state.frozen(), false);
  assert.equal(state.timers.size, 0);
  assert.equal(state.intervals.size, 0);
  assert.match(state.messages[0], /not been confirmed/);
});

test('a late server response after the deadline does not start polling', async t => {
  const pending = deferred();
  const state = setup(t, () => pending.promise);
  state.buttons['Sync to Webflow']();
  await flush();

  const [deadline] = state.timers.values();
  deadline();
  assert.equal(state.frozen(), false);

  pending.resolve({ success: true });
  await flush();

  assert.equal(state.intervals.size, 0, 'no polling may start after the form was released');
  assert.equal(state.frozen(), false);
  assert.equal(state.messages.length, 1);
});

test('a failed server request clears the deadline and reports the error once', async t => {
  const state = setup(t, () => Promise.reject({ message: 'Pipeline failed with status 500.' }));
  state.buttons['Sync to Webflow']();
  await flush();

  assert.equal(state.frozen(), false);
  assert.equal(state.timers.size, 0);
  assert.equal(state.intervals.size, 0);
  assert.equal(state.messages.length, 1);
  assert.match(state.messages[0].message, /500/);
});

test('a server response with no message is reported as a failure', async t => {
  const state = setup(t, async () => undefined);
  state.buttons['Sync to Webflow']();
  await flush();

  assert.equal(state.frozen(), false);
  assert.equal(state.timers.size, 0);
  assert.equal(state.intervals.size, 0);
  assert.equal(state.messages.length, 1);
  assert.equal(state.messages[0].message, 'No response from server.');
});

test('polling keeps the form frozen while the sync is still pending', async t => {
  const state = setup(t);
  state.buttons['Sync to Webflow']();
  await flush();
  assert.equal(state.intervals.size, 1);

  [...state.intervals.values()][0]();
  await flush();

  assert.equal(state.frozen(), true);
  assert.equal(state.intervals.size, 1);
  assert.equal(state.messages.length, 0);
});

test('successful polling clears the interval and deadline', async t => {
  const state = setup(t, succeeds, completed);
  state.buttons['Sync to Webflow']();
  await flush();
  assert.equal(state.intervals.size, 1);

  [...state.intervals.values()][0]();
  await flush();

  assert.equal(state.frozen(), false);
  assert.equal(state.intervals.size, 0);
  assert.equal(state.timers.size, 0);
  assert.equal(state.messages.length, 1);
  assert.equal(state.messages[0].message, 'Webflow Sync Complete!');
});

test('sync requests every enabled target brand instead of a hard-coded brand', async t => {
  const state = setup(t);
  state.buttons['Sync to Webflow']();
  await flush();
  const brands = state.requests.filter(row => row.method === SPEC_SHEET).map(row => row.args.brand);
  assert.deepEqual(brands, ['illumenate', 'lighting_206']);
});

test('an earlier Synced status does not complete a new sync', async t => {
  const state = setup(t, succeeds, () => ({
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

test('a failed publication job reports the pipeline failure, escapes its error and releases the form', async t => {
  const state = setup(t, succeeds, () => ({
    ...BASELINE,
    failed: true,
    brands: [{ brand: 'illumenate', state: 'failed', error: '<b>Publication failed (500)</b>' }],
  }));
  state.buttons['Sync to Webflow']();
  await flush();
  [...state.intervals.values()][0]();
  await flush();
  assert.equal(state.frozen(), false);
  assert.equal(state.intervals.size, 0);
  assert.equal(state.timers.size, 0);
  assert.equal(state.messages.length, 1);
  assert.equal(state.messages[0].title, 'Sync Error');
  assert.match(state.messages[0].message, /&lt;b>Publication failed/);
});
