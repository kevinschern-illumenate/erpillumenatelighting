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

const API = 'illumenate_lighting.illumenate_lighting.api.webflow_export_v2.';
const PROGRESS = API + 'get_sync_progress';
const TRIGGER = API + 'trigger_sync_v2';
const SPEC_SHEET = API + 'request_spec_sheet';
const syncScript = fs.readFileSync(
  path.join(__dirname, '../../illumenate_lighting/public/js/webflow_sync.js'),
  'utf8',
);
const BASELINE = {
  server_time: '2026-11-03 10:00:00',
  brands: [{ brand: 'illumenate', state: 'pending' }, { brand: 'lighting_206', state: 'pending' }],
  complete: false,
  failed: false,
};

// Lets pending promise callbacks and any setImmediate work run.
const flush = async () => {
  for (let i = 0; i < 5; i += 1) await new Promise(resolve => setImmediate(resolve));
};

const neverSettles = () => new Promise(() => {});
const staged = async () => ({ status: 'success', jobs: ['JOB-1'] });
const completed = () => ({
  ...BASELINE,
  complete: true,
  brands: BASELINE.brands.map(row => ({ ...row, state: 'complete' })),
});

// trigger answers trigger_sync_v2; progress answers polls that carry "since".
function setup(t, trigger = staged, progress = () => ({ ...BASELINE }), doc = {}) {
  const dom = new JSDOM('<html><head></head><body></body></html>');
  t.after(() => dom.window.close());
  const $ = jquery(dom.window);
  $.fn.modal = function () { return this; };
  const handlers = {};
  const buttons = {};
  const queries = [];
  const messages = [];
  const requests = [];
  const timers = new Map();
  const dialogs = [];
  const clock = { now: 0 };
  let serial = 0;
  class Dialog {
    constructor(options) {
      this.options = options;
      this.$wrapper = $('<div><div class="modal-header"><button class="btn-modal-close"></button></div></div>');
      this.fields_dict = { body: { $wrapper: $('<div>') } };
      this.open = false;
      dialogs.push(this);
    }
    show() { this.open = true; }
    hide() { this.open = false; }
  }
  const frm = {
    doc: {
      name: 'demo',
      product_slug: 'demo',
      target_brands: [
        { brand: 'illumenate', enabled: 1 },
        { brand: 'lighting_206', enabled: 1 },
        { brand: 'retired', enabled: 0 },
      ],
      ...doc,
    },
    is_new: () => false,
    is_dirty: () => Boolean(doc.__dirty),
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
  const context = {
    $,
    __: value => value,
    document: dom.window.document,
    window: dom.window,
    console,
    Date: { now: () => clock.now },
    Promise,
    setTimeout(fn) {
      const id = ++serial;
      timers.set(id, fn);
      return id;
    },
    clearTimeout(id) {
      timers.delete(id);
    },
    frappe: {
      ui: { Dialog, form: { on(doctype, callbacks) { handlers[doctype] = callbacks; } } },
      utils: { escape_html: value => String(value).replace(/</g, '&lt;') },
      msgprint(message) { messages.push(message); },
      xcall(method, args) {
        requests.push({ method, args });
        if (method === TRIGGER) return trigger(args);
        if (method === PROGRESS) return Promise.resolve(args.since ? progress(args) : { ...BASELINE });
        return Promise.resolve({});
      },
      show_alert(message) { messages.push(message); },
    },
  };
  vm.runInNewContext(syncScript, context);
  vm.runInNewContext(productScript, context);
  handlers['ilL-Webflow-Product'].refresh(frm);
  const runTimers = () => {
    const pending = [...timers.entries()];
    timers.clear();
    pending.forEach(([, fn]) => fn());
  };
  return { frm, buttons, queries, timers, dialogs, messages, requests, clock, runTimers };
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

test('sync stages through the publication pipeline, never the spec sheet webhook (plan 4.19)', async t => {
  const state = setup(t, staged, completed);
  state.buttons['Sync to Webflow']();
  await flush();
  assert.equal(state.dialogs.length, 1);
  assert.equal(state.dialogs[0].open, true);
  const sync = state.requests.filter(row => row.method.startsWith(API));
  const methods = sync.map(row => row.method);
  assert.deepEqual(methods.slice(0, 2), [PROGRESS, TRIGGER]);
  assert.equal(sync[1].args.docname, 'demo');
  assert.ok(!methods.includes(SPEC_SHEET));
});

test('successful polling closes the dialog and reports the sync once', async t => {
  const state = setup(t, staged, completed);
  state.buttons['Sync to Webflow']();
  await flush();
  state.runTimers();
  await flush();
  const poll = state.requests.filter(row => row.method === PROGRESS).pop();
  assert.equal(poll.args.since, BASELINE.server_time);
  assert.equal(state.dialogs[0].open, false);
  assert.equal(state.messages.length, 1);
  assert.equal(state.messages[0].message, 'Synced to Webflow.');
});

test('an earlier Synced status does not complete a new sync', async t => {
  const state = setup(t, staged, () => ({
    ...BASELINE,
    brands: BASELINE.brands.map(row => ({ ...row, sync_status: 'Synced', state: 'pending' })),
  }));
  state.buttons['Sync to Webflow']();
  await flush();
  state.runTimers();
  await flush();
  assert.equal(state.dialogs[0].open, true);
  assert.equal(state.timers.size, 1, 'it keeps polling');
  assert.equal(state.messages.length, 0);
});

test('a failed publication job reports the pipeline failure, escapes its error and closes the dialog', async t => {
  const state = setup(t, staged, () => ({
    ...BASELINE,
    failed: true,
    brands: [{ brand: 'illumenate', state: 'failed', error: '<b>Publication failed (500)</b>' }],
  }));
  state.buttons['Sync to Webflow']();
  await flush();
  state.runTimers();
  await flush();
  assert.equal(state.dialogs[0].open, false);
  assert.equal(state.timers.size, 0);
  assert.equal(state.messages.length, 1);
  assert.match(state.messages[0].message, /&lt;b>Publication failed/);
});

test('a product that is not ready for any brand sends nothing and says so', async t => {
  const state = setup(t, async () => ({ status: 'success', jobs: [] }));
  state.buttons['Sync to Webflow']();
  await flush();
  assert.equal(state.dialogs[0].open, false);
  assert.equal(state.timers.size, 0);
  assert.match(state.messages[0].message, /Nothing was sent/);
});

test('a failed server request closes the dialog and reports the error once', async t => {
  const state = setup(t, () => Promise.reject({ message: 'Pipeline failed with status 500.' }));
  state.buttons['Sync to Webflow']();
  await flush();
  assert.equal(state.dialogs[0].open, false);
  assert.equal(state.timers.size, 0);
  assert.equal(state.messages.length, 1);
  assert.match(state.messages[0].message, /500/);
});

test('a sync that is never confirmed releases the dialog after the deadline', async t => {
  const state = setup(t);
  state.buttons['Sync to Webflow']();
  await flush();
  state.clock.now = 181000;
  state.runTimers();
  await flush();
  assert.equal(state.dialogs[0].open, false);
  assert.equal(state.timers.size, 0);
  assert.match(state.messages[0].message, /Not confirmed yet/);
});

test('an unsaved product is not synced', async t => {
  const state = setup(t, staged, completed, { __dirty: true });
  state.buttons['Sync to Webflow']();
  await flush();
  assert.equal(state.dialogs.length, 0);
  assert.ok(!state.requests.some(row => row.method === TRIGGER));
  assert.equal(state.messages[0], 'Save the product first.');
});
