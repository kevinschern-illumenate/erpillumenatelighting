// Desk sees the portal: inline threads with an unread count, portal links and
// list indicators (DESK-4, DESK-5).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { JSDOM } = require('jsdom');

const js = name => fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/public/js', name), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));
const translate = (value, args) => String(value).replace(/\{(\d)\}/g, (_, i) => args[i]);

function desk(script) {
  const forms = {};
  const context = {
    __: translate,
    window: {},
    frappe: {
      ui: { form: { on: (doctype, handlers) => { (forms[doctype] = forms[doctype] || []).push(handlers); } } },
      listview_settings: {},
    },
  };
  context.window = context;
  vm.runInNewContext(js(script), context);
  return { forms, context };
}

function form(doctype, doc) {
  const buttons = [];
  return { doctype, doc: { name: 'X-1', ...doc }, is_new: () => false, add_custom_button: (label, action) => buttons.push({ label, action }), buttons };
}

test('staff see how many customer messages are unanswered', async () => {
  const dom = new JSDOM('<body><div id="t" data-parent-type="ilL-Quote-Request" data-parent-name="QR-1"></div></body>', { runScripts: 'outside-only', url: 'https://erp.test/app' });
  const w = dom.window;
  w.__ = translate;
  w.frappe = { call: async () => ({ message: { messages: [], status: 'REQUESTED', next_action_by: 'Staff', is_staff: true, can_reply: true, new_from_customer: 2, total: 0, page: 1, page_size: 20 } }) };
  w.PortalUploads = { uploadAll: async () => [], call: async () => ({ success: true }) };
  w.eval(js('portal_conversation.js'));
  const root = w.document.getElementById('t');
  w.PortalConversation(root); await tick();
  assert.equal(root.querySelector('.ill-thread__unread').textContent, '2 new customer message(s)');
  dom.window.close();
});

test('portal-originated records open their portal page; others get no button', () => {
  const { forms, context } = desk('desk_portal_links.js');
  const cases = [
    ['ilL-Project', { name: 'P 1' }, '/portal/projects/P%201'],
    ['ilL-Quote-Request', { name: 'QR-1' }, '/portal/quote-requests/QR-1'],
    ['ilL-Quote-Offer', { name: 'OFFER-1' }, '/portal/quotes/OFFER-1'],
    ['ilL-Order-Intake', { name: 'OI-1', sales_order: 'SO-1' }, '/portal/orders/SO-1'],
    ['Issue', { name: 'ISS-1', ill_portal_request_key: 'k' }, '/portal/support/ISS-1'],
    ['Issue', { name: 'ISS-2' }, null],
    ['Sales Order', { name: 'SO-2' }, null],
    ['Sales Order', { name: 'SO-3', ill_fixture_schedule: 'S-1' }, '/portal/orders/SO-3'],
  ];
  for (const [doctype, doc, expected] of cases) {
    const frm = form(doctype, doc);
    forms[doctype].forEach(handlers => handlers.refresh(frm));
    assert.deepEqual(JSON.parse(JSON.stringify(frm.buttons.map(b => b.label))), expected ? ['Open in portal'] : [], doctype + ' ' + doc.name);
    if (expected) {
      const opened = [];
      context.open = (...args) => opened.push(args);
      frm.buttons[0].action();
      assert.deepEqual(opened[0], [expected, '_blank', 'noopener']);
    }
  }
});

test('list indicators say who the next step waits on', () => {
  const { context } = desk('portal_request_list.js');
  // Values cross the vm boundary; compare them as plain data.
  const plain = value => JSON.parse(JSON.stringify(value));
  const settings = context.frappe.listview_settings['ilL-Quote-Request'];
  assert.ok(settings.add_fields.includes('ill_next_action_by'));
  assert.deepEqual(plain(settings.get_indicator({ state: 'REQUESTED', ill_next_action_by: 'Staff' })), ['Waiting on staff', 'orange', 'ill_next_action_by,=,Staff']);
  assert.deepEqual(plain(settings.get_indicator({ state: 'INFORMATION_NEEDED', ill_next_action_by: 'Customer' })), ['Waiting on customer', 'blue', 'ill_next_action_by,=,Customer']);
  assert.deepEqual(plain(settings.get_indicator({ state: 'ISSUED', ill_next_action_by: 'Customer' })), ['Issued', 'green', 'state,=,ISSUED']);
  const drawings = context.frappe.listview_settings['ilL-Document-Request'];
  assert.deepEqual(plain(drawings.get_indicator({ status: 'Cancelled' })), ['Cancelled', 'red', 'status,=,Cancelled']);
});

test('the conversation is inline on the form and rebuilt for the record on screen', () => {
  const { forms, context } = desk('desk_conversation.js');
  const dom = new JSDOM('<body><div id="dash"></div></body>');
  const $ = selector => {
    const nodes = typeof selector === 'string' ? [...dom.window.document.querySelectorAll(selector)] : [selector];
    return { remove: () => nodes.forEach(n => n.remove()), find: s => $(nodes[0].querySelector(s) || dom.window.document.createElement('x')), 0: nodes[0] };
  };
  const mounted = [];
  context.frappe.require = (_files, done) => done();
  context.PortalConversation = root => mounted.push({ ...root.dataset });
  const dashboard = dom.window.document.getElementById('dash');
  const frm = form('ilL-Quote-Request', { name: 'QR-1' });
  frm.dashboard = {
    wrapper: { find: s => $(s) },
    add_section(html, label, css) {
      const section = dom.window.document.createElement('div');
      section.className = css; section.innerHTML = html; section.dataset.label = label; dashboard.append(section);
      return { find: s => ({ 0: section.querySelector(s) }) };
    },
    show() {},
  };
  forms['ilL-Quote-Request'][0].refresh(frm);
  frm.doc.name = 'QR-2';
  forms['ilL-Quote-Request'][0].refresh(frm);
  assert.equal(dashboard.querySelectorAll('.ill-desk-thread-section').length, 1);
  assert.equal(dashboard.querySelector('.ill-desk-thread-section').dataset.label, 'Portal conversation');
  assert.deepEqual(mounted.map(m => m.parentName), ['QR-1', 'QR-2']);
  const emailIssue = form('Issue', { name: 'ISS-9' });
  emailIssue.dashboard = frm.dashboard;
  forms.Issue[0].refresh(emailIssue);
  assert.equal(mounted.length, 2, 'email-only Issues have no portal thread');
});
