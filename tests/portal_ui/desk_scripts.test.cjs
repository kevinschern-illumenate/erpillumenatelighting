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

function setup(t, fetchResponse) {
  const dom = new JSDOM('<html><head></head><body></body></html>');
  t.after(() => dom.window.close());
  const $ = jquery(dom.window);
  const handlers = {}, buttons = {}, queries = [], messages = [], requests = [];
  const timers = new Map(), intervals = new Map();
  let serial = 0, frozen = false;
  const frm = {
    doc: { name: 'demo', product_slug: 'demo' },
    is_new: () => false,
    add_custom_button(label, fn) { buttons[label] = fn; return $('<button>'); },
    set_query(...args) { queries.push(args); },
    reload_doc() {},
    dashboard: { set_headline_alert() {} },
  };
  vm.runInNewContext(productScript, {
    $, __: value => value, document: dom.window.document, window: dom.window,
    AbortController, console,
    setTimeout(fn) { const id = ++serial; timers.set(id, fn); return id; },
    clearTimeout(id) { timers.delete(id); },
    setInterval(fn) { const id = ++serial; intervals.set(id, fn); return id; },
    clearInterval(id) { intervals.delete(id); },
    fetch(url, options) { requests.push({ url, ...options }); return fetchResponse(); },
    frappe: {
      ui: { form: { on(doctype, callbacks) { handlers[doctype] = callbacks; } } },
      dom: { freeze() { frozen = true; }, unfreeze() { frozen = false; } },
      msgprint(message) { messages.push(message); },
      xcall: async () => ({ sync_status: 'Synced' }),
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
  [...state.timers.values()][0]();
  assert.equal(state.frozen(), false);
  assert.equal(state.requests[0].signal.aborted, true);
  assert.equal(state.timers.size, 0);
  assert.equal(state.intervals.size, 0);
  assert.match(state.messages[0], /not been confirmed/);
});

test('webhook errors clear the deadline and release the form', async t => {
  const state = setup(t, async () => ({ ok: false, status: 500 }));
  state.buttons['Sync to Webflow']();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(state.frozen(), false);
  assert.equal(state.timers.size, 0);
  assert.match(state.messages[0].message, /500/);
});

test('successful polling clears the deadline so it cannot interrupt another operation', async t => {
  const state = setup(t, async () => ({ ok: true, json: async () => ({ success: true }) }));
  state.buttons['Sync to Webflow']();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(state.intervals.size, 1);
  [...state.intervals.values()][0]();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(state.frozen(), false);
  assert.equal(state.intervals.size, 0);
  assert.equal(state.timers.size, 0);
  assert.equal(state.messages.length, 1);
});
