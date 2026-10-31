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

// A frappe.call stand-in that fails the way the handler expects: it calls the
// error callback and rejects the returned promise. The handler must report the
// failure once, whichever path it takes first.
function failingCall(err) {
  return opts => {
    if (opts.error) opts.error(err);
    return Promise.reject(err);
  };
}

// Lets pending promise callbacks and any setImmediate work run.
const flush = () => new Promise(resolve => setImmediate(resolve));

const neverSettles = () => new Promise(() => {});
const succeeds = async () => ({ message: { ok: true } });

function setup(t, { call = succeeds, xcall = async () => ({ sync_status: 'Synced' }) } = {}) {
  const dom = new JSDOM('<html><head></head><body></body></html>');
  t.after(() => dom.window.close());
  const $ = jquery(dom.window);
  const handlers = {};
  const buttons = {};
  const queries = [];
  const messages = [];
  const timers = new Map();
  const intervals = new Map();
  let serial = 0;
  let frozen = false;
  const frm = {
    doc: { name: 'demo', product_slug: 'demo' },
    is_new: () => false,
    add_custom_button(label, fn) {
      buttons[label] = fn;
      return $('<button>');
    },
    set_query(...args) {
      queries.push(args);
    },
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
      msgprint(message) { messages.push(message); },
      show_alert(message) { messages.push(message); },
      call: opts => call(opts),
      xcall: (...args) => xcall(...args),
    },
  });
  handlers['ilL-Webflow-Product'].refresh(frm);
  return {
    frm,
    buttons,
    queries,
    timers,
    intervals,
    messages,
    frozen: () => frozen,
  };
}

test('the product form registers its compatible-product query during refresh', t => {
  const state = setup(t);
  assert.equal(state.queries.length, 1);
  const [field, table, query] = state.queries[0];
  assert.equal(field, 'related_product');
  assert.equal(table, 'compatible_products');
  const result = query({ target_brands: [{ brand: 'illumenate', enabled: 1 }, { brand: 'other', enabled: 0 }] });
  assert.deepEqual(Array.from(result.filters.brands), ['illumenate']);
});

test('a server call that never responds cannot leave the product form frozen', t => {
  const state = setup(t, { call: neverSettles });
  state.buttons['Sync to Webflow']();
  assert.equal(state.frozen(), true);
  assert.equal(state.timers.size, 1);

  const [deadline] = state.timers.values();
  deadline();

  assert.equal(state.frozen(), false);
  assert.equal(state.timers.size, 0);
  assert.equal(state.intervals.size, 0);
  assert.match(state.messages[0], /not been confirmed/);
});

test('a late server response after the deadline does not start polling', async t => {
  const pending = deferred();
  const state = setup(t, { call: () => pending.promise });
  state.buttons['Sync to Webflow']();

  const [deadline] = state.timers.values();
  deadline();
  assert.equal(state.frozen(), false);

  pending.resolve({ message: { ok: true } });
  await flush();

  assert.equal(state.intervals.size, 0, 'no polling may start after the form was released');
  assert.equal(state.frozen(), false);
});

test('a failed server request clears the deadline and reports the error once', async t => {
  const state = setup(t, { call: failingCall({ message: 'Server exploded' }) });
  state.buttons['Sync to Webflow']();
  await flush();

  assert.equal(state.frozen(), false);
  assert.equal(state.timers.size, 0);
  assert.equal(state.intervals.size, 0);
  assert.equal(state.messages.length, 1);
  assert.equal(state.messages[0].message, 'Server exploded');
});

test('a server response with no message is reported as a failure', async t => {
  const state = setup(t, { call: async () => ({}) });
  state.buttons['Sync to Webflow']();
  await flush();

  assert.equal(state.frozen(), false);
  assert.equal(state.timers.size, 0);
  assert.equal(state.intervals.size, 0);
  assert.equal(state.messages.length, 1);
  assert.equal(state.messages[0].message, 'No response from server.');
});

test('polling keeps the form frozen while the sync is still pending', async t => {
  const state = setup(t, { xcall: async () => ({ sync_status: 'Pending' }) });
  state.buttons['Sync to Webflow']();
  await flush();
  assert.equal(state.intervals.size, 1);

  [...state.intervals.values()][0]();
  await flush();

  assert.equal(state.frozen(), true);
  assert.equal(state.intervals.size, 1);
  assert.equal(state.messages.length, 0);
});

test('a Synced status from polling clears the interval and deadline', async t => {
  const state = setup(t);
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

test('an Error status from polling reports the pipeline failure and releases the form', async t => {
  const state = setup(t, { xcall: async () => ({ sync_status: 'Error' }) });
  state.buttons['Sync to Webflow']();
  await flush();

  [...state.intervals.values()][0]();
  await flush();

  assert.equal(state.frozen(), false);
  assert.equal(state.intervals.size, 0);
  assert.equal(state.timers.size, 0);
  assert.equal(state.messages.length, 1);
  assert.equal(state.messages[0].title, 'Sync Error');
});
