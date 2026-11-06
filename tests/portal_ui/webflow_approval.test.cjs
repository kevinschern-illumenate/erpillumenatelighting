// Webflow approvals banner on the Webflow Product and the Desk browser alerts (plan 4.19).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const jquery = require('jquery');
const { JSDOM } = require('jsdom');

const JS = path.join(__dirname, '../../illumenate_lighting/public/js');
const banner = fs.readFileSync(path.join(JS, 'webflow_approval.js'), 'utf8');
const alerts = fs.readFileSync(path.join(JS, 'desk/webflow_alerts.js'), 'utf8');
const API = 'illumenate_lighting.illumenate_lighting.webflow_approvals.';
const HOSTILE = '<img src=x onerror=alert(1)>';
const flush = async () => {
  for (let i = 0; i < 5; i += 1) await new Promise(resolve => setImmediate(resolve));
};

function setup(t, pending) {
  const dom = new JSDOM('<html><body><div class="form"></div></body></html>');
  t.after(() => dom.window.close());
  const $ = jquery(dom.window);
  const handlers = {}, calls = [], alertsShown = [], intros = [];
  let reloads = 0;
  const frm = {
    doc: { name: 'kit-ra01' },
    $wrapper: $(dom.window.document.querySelector('.form')),
    is_new: () => false,
    set_intro(html, color) {
      intros.push([html, color]);
      this.$wrapper.html(html || '');
    },
    reload_doc() { reloads += 1; },
  };
  const context = {
    $,
    window: {},
    __: (text, args) => String(text).replace(/\{(\d+)\}/g, (_m, i) => String((args || [])[i])),
    frappe: {
      ui: { form: { on(doctype, callbacks) { handlers[doctype] = callbacks; } } },
      utils: { escape_html: value => String(value).replace(/</g, '&lt;').replace(/>/g, '&gt;') },
      confirm(_message, yes) { yes(); },
      show_alert(message) { alertsShown.push(message); },
      xcall(method, args) {
        calls.push({ method, args });
        if (method === API + 'get_pending') return Promise.resolve(pending);
        if (method === API + 'approve') return Promise.resolve({ state: 'Approved', sync: { jobs: ['J1'] } });
        return Promise.resolve({ state: 'Rejected', restored: true });
      },
    },
  };
  vm.runInNewContext(banner, context);
  handlers['ilL-Webflow-Product'].refresh(frm);
  return { frm, calls, alertsShown, intros, reloads: () => reloads };
}

const PENDING = {
  name: 'WFA-00001',
  product: 'kit-ra01',
  action: 'Restore',
  from_status: 'Archived',
  to_status: 'Published',
  summary: `Restore kit-ra01 to Published on staging-illumenate.webflow.io ${HOSTILE}`,
  requested_by: 'owner@example.com',
  can_decide: true,
};

test('a pending approval shows an orange banner with the summary, Approve and Reject', async t => {
  const { frm, intros } = setup(t, PENDING);
  await flush();
  const [html, color] = intros.at(-1);
  assert.equal(color, 'orange');
  assert.match(html, /Restore kit-ra01 to Published on staging-illumenate\.webflow\.io/);
  assert.doesNotMatch(html, /<img/);
  assert.equal(frm.$wrapper.find('[data-ill-approval="approve"]').length, 1);
  assert.equal(frm.$wrapper.find('[data-ill-approval="reject"]').length, 1);
});

test('Approve and Reject call the server for this approval and reload the form', async t => {
  for (const action of ['approve', 'reject']) {
    const { frm, calls, reloads, alertsShown } = setup(t, PENDING);
    await flush();
    frm.$wrapper.find(`[data-ill-approval="${action}"]`).trigger('click');
    await flush();
    assert.equal(calls.at(-1).method, API + action);
    assert.equal(calls.at(-1).args.name, 'WFA-00001');
    assert.equal(reloads(), 1);
    assert.equal(alertsShown.at(-1).indicator, 'green');
  }
});

test('no banner without a pending approval; no buttons for a user who cannot decide', async t => {
  const none = setup(t, null);
  await flush();
  assert.deepEqual(none.intros, []);
  const readOnly = setup(t, { ...PENDING, can_decide: false });
  await flush();
  assert.equal(readOnly.frm.$wrapper.find('[data-ill-approval]').length, 0);
});

test('the Desk bundle listens for Webflow alerts and shows a browser notification', () => {
  const bundle = fs.readFileSync(path.join(JS, 'illumenate_desk.bundle.js'), 'utf8');
  assert.match(bundle, /import "\.\/desk\/webflow_alerts\.js";/);
  const listeners = {}, notices = [], shown = [];
  class Notification {
    constructor(title, options) { notices.push({ title, options }); }
    close() {}
  }
  Notification.permission = 'granted';
  const root = {
    Notification,
    frappe: {
      realtime: { on(event, fn) { listeners[event] = fn; }, off() {} },
      show_alert(message) { shown.push(message); },
      utils: { escape_html: value => String(value) },
    },
  };
  root.window = root;
  vm.runInNewContext(alerts, { window: root, Promise });
  listeners.ill_webflow_alert({ title: 'Webflow approval needed: Restore kit-ra01', body: 'b', route: '/app/x' });
  assert.equal(notices.length, 1);
  assert.equal(notices[0].title, 'Webflow approval needed: Restore kit-ra01');
  assert.equal(shown.length, 1);
});
