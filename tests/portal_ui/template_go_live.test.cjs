// The popup when a template without a Webflow Product is set to Active + Live (plan 4.5, owner 2026-11-08).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const code = fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/public/js/template_webflow_link.js'), 'utf8');
const KIT = 'ilL-Extrusion-Kit-Template';
const flush = async () => { for (let i = 0; i < 8; i += 1) await new Promise(resolve => setImmediate(resolve)); };
const DEFAULTS = { link_field: 'kit_template', product_name: 'Rainier [AN]', product_slug: 'kit-ra03', product_types: ['Extrusion Kit'], product_type: 'Extrusion Kit', brands: ['illumenate'] };

function setup() {
  const handlers = {}, calls = [], dialogs = [], messages = [];
  class Dialog {
    constructor(options) { this.options = options; dialogs.push(this); }
    show() { this.shown = true; }
    hide() { this.hidden = true; if (this.onhide) this.onhide(); }
    disable_primary_action() {}
    enable_primary_action() {}
  }
  const frappe = {
    ui: { Dialog, form: { on: (name, events) => { (handlers[name] = handlers[name] || []).push(events); } } },
    xcall: (method, args) => {
      calls.push([method.split('.').pop(), JSON.parse(JSON.stringify(args))]);
      return Promise.resolve(method.endsWith('go_live_defaults') ? DEFAULTS : 'kit-ra03');
    },
    msgprint: message => messages.push(message),
  };
  const context = { frappe, __: (text, args) => String(text).replace(/\{(\d+)\}/g, (_, i) => args[i]), Promise };
  context.window = context;
  vm.runInNewContext(code, context);
  const saved = [];
  const frm = {
    doctype: KIT, doc: { name: 'KIT-RA03', product_status: 'Active', webflow_product: null },
    is_new: () => false,
    set_value(field, value) { this.doc[field] = value; (handlers[KIT] || []).forEach(h => h[field] && h[field](this)); return Promise.resolve(); },
    save() { saved.push({ ...this.doc }); return Promise.resolve(); },
    add_custom_button() {},
  };
  const fire = event => (handlers[KIT] || []).forEach(h => h[event] && h[event](frm));
  return { frm, fire, calls, dialogs, saved, messages };
}

test('setting Active + Live without a product opens the popup; Cancel puts the status back', async () => {
  const { frm, fire, calls, dialogs } = setup();
  fire('refresh');
  await frm.set_value('product_status', 'Active + Live');
  await flush();
  assert.equal(calls[0][0], 'go_live_defaults');
  assert.equal(dialogs.length, 1);
  dialogs[0].options.secondary_action();
  await flush();
  assert.equal(frm.doc.product_status, 'Active');
  assert.equal(dialogs.length, 1); // reverting does not reopen it
});

test('Create new creates the product, then links it with the template save', async () => {
  const { frm, fire, calls, dialogs, saved } = setup();
  fire('refresh');
  await frm.set_value('product_status', 'Active + Live');
  await flush();
  dialogs[0].options.primary_action({ choice: 'Create new', product_name: 'Rainier [AN]', product_slug: 'kit-ra03', product_type: 'Extrusion Kit' });
  await flush();
  assert.deepEqual(calls[1], ['create_webflow_product', { template_doctype: KIT, template_id: 'KIT-RA03', product_name: 'Rainier [AN]', product_slug: 'kit-ra03', product_type: 'Extrusion Kit' }]);
  assert.equal(saved.length, 1);
  assert.equal(saved[0].webflow_product, 'kit-ra03');
  assert.equal(saved[0].product_status, 'Active + Live');
  assert.equal(frm.doc.product_status, 'Active + Live'); // closing after success does not revert
});

test('Link existing saves with the chosen product; a linked template needs no popup', async () => {
  const { frm, fire, dialogs, saved } = setup();
  fire('refresh');
  await frm.set_value('product_status', 'Active + Live');
  await flush();
  dialogs[0].options.primary_action({ choice: 'Link existing', product: 'kit-old' });
  await flush();
  assert.equal(saved[0].webflow_product, 'kit-old');
  frm.doc.product_status = 'Active';
  fire('refresh');
  await frm.set_value('product_status', 'Active + Live');
  await flush();
  assert.equal(dialogs.length, 1);
});
