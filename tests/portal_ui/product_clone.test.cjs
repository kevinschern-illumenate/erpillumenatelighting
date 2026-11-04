const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const script = fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/public/js/product_clone.js'), 'utf8');
const HOSTILE = '<img src=x onerror=alert(1)>';
const tick = () => new Promise(resolve => setImmediate(resolve));

function setup({ roles = ['ilL Catalog Publisher'], dirty = false, isNew = false, response } = {}) {
  const handlers = {}, buttons = {}, calls = [], routes = [], messages = [], dialogs = [];
  const escape = value => String(value).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  class Dialog {
    constructor(options) { this.options = options; this.values = {}; this.enabled = true; dialogs.push(this); }
    set_value(field, value) { this.values[field] = value; }
    get_value(field) { return this.values[field]; }
    show() { this.shown = true; }
    hide() { this.shown = false; }
    disable_primary_action() { this.enabled = false; }
    enable_primary_action() { this.enabled = true; }
  }
  const window = {};
  vm.runInNewContext(script, {
    window,
    __: (text, args) => String(text).replace(/\{(\d+)\}/g, (_m, i) => String((args || [])[i])),
    frappe: {
      user_roles: roles,
      ui: { Dialog, form: { on(doctype, callbacks) { handlers[doctype] = callbacks; } } },
      utils: { escape_html: escape },
      async call(options) {
        calls.push(JSON.parse(JSON.stringify(options)));
        if (options.method.endsWith('.duplicate')) {
          if (response instanceof Error) throw response;
          return { message: response || { doctype: 'ilL-Webflow-Product', name: 'slim-24', readiness: 'product' } };
        }
        return { message: { ready: false, issues: [{ record: 'slim-24', field: 'featured_image', message: HOSTILE }], warnings: [] } };
      },
      async set_route(...args) { routes.push(args); },
      msgprint(message) { messages.push(message); },
    },
  });
  const frm = {
    doctype: 'ilL-Webflow-Product',
    doc: { name: 'slim-12', product_name: 'Slim 12' },
    is_new: () => isNew,
    is_dirty: () => dirty,
    add_custom_button(label, fn, group) { buttons[label] = { fn, group }; },
  };
  return { handlers, buttons, calls, routes, messages, dialogs, frm, window };
}

test('the product and all six templates get a staff-only Duplicate action', () => {
  const state = setup();
  for (const doctype of ['ilL-Webflow-Product', 'ilL-Fixture-Template', 'ilL-Tape-Neon-Template', 'ilL-LED-Sheet-Template',
    'ilL-Driver-Template', 'ilL-Controller-Template', 'ilL-Extrusion-Kit-Template']) {
    assert.equal(typeof state.handlers[doctype].refresh, 'function', doctype);
  }
  state.handlers['ilL-Webflow-Product'].refresh(state.frm);
  assert.equal(state.buttons['Duplicate as new product'].group, 'Actions');
  for (const options of [{ roles: ['ilL Engineering'] }, { isNew: true }]) {
    const other = setup(options);
    other.handlers['ilL-Webflow-Product'].refresh(other.frm);
    assert.deepEqual(other.buttons, {});
  }
});

test('unsaved changes block duplication', () => {
  const state = setup({ dirty: true });
  state.handlers['ilL-Webflow-Product'].refresh(state.frm);
  state.buttons['Duplicate as new product'].fn();
  assert.equal(state.dialogs.length, 0);
  assert.equal(state.messages[0], 'Save before duplicating.');
});

test('creating a draft posts the choices, opens the copy and shows its readiness escaped', async () => {
  const state = setup();
  state.handlers['ilL-Webflow-Product'].refresh(state.frm);
  state.buttons['Duplicate as new product'].fn();
  const dialog = state.dialogs[0];
  assert.equal(dialog.values.new_name, 'Slim 12 copy');
  assert.equal(state.window.ProductClone.slugify(' Slim 24 / RGB+ '), 'slim-24-rgb');
  await dialog.options.primary_action({ new_name: 'Slim 24', new_slug: 'slim-24', template_code: 'SLIM-24', include_media: 0 });
  await tick();
  assert.deepEqual(state.calls[0].args, { doctype: 'ilL-Webflow-Product', name: 'slim-12', new_name: 'Slim 24', new_slug: 'slim-24', template_code: 'SLIM-24', include_media: 0 });
  assert.equal(state.calls[0].type, 'POST');
  assert.deepEqual(state.routes, [['Form', 'ilL-Webflow-Product', 'slim-24']]);
  assert.match(state.calls[1].method, /product_readiness\.preview$/);
  assert.deepEqual(state.calls[1].args, { product: 'slim-24', channel: 'portal' });
  const html = state.messages[0].message;
  assert.ok(!html.includes(HOSTILE));
  assert.ok(html.includes('&lt;img src=x onerror=alert(1)&gt;'));
});

test('templates use the template preflight and a failed call re-enables the dialog', async () => {
  const state = setup({ response: { doctype: 'ilL-Driver-Template', name: 'DRV-2', readiness: 'template' } });
  state.frm.doctype = 'ilL-Driver-Template';
  state.handlers['ilL-Driver-Template'].refresh(state.frm);
  state.buttons['Duplicate as new product'].fn();
  assert.deepEqual(Array.from(state.dialogs[0].options.fields, field => field.fieldname), ['new_name', 'template_name', 'include_media']);
  await state.dialogs[0].options.primary_action({ new_name: 'DRV-2', include_media: 1 });
  await tick();
  assert.deepEqual(state.calls[1].args, { doctype: 'ilL-Driver-Template', name: 'DRV-2' });
  const failing = setup({ response: new Error('exists') });
  failing.handlers['ilL-Webflow-Product'].refresh(failing.frm);
  failing.buttons['Duplicate as new product'].fn();
  await failing.dialogs[0].options.primary_action({ new_name: 'Slim 12', new_slug: 'slim-12', include_media: 1 });
  assert.equal(failing.dialogs[0].enabled, true);
  assert.equal(failing.routes.length, 0);
});
