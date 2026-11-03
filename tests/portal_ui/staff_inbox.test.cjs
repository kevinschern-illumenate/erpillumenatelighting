// Plan 7.4: the staff inbox lists owned work overdue first and its quick actions call the
// server's validated writers.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');

const ROOT = path.join(__dirname, '../../illumenate_lighting');
const INBOX = fs.readFileSync(path.join(ROOT, 'public/js/desk/staff_inbox.js'), 'utf8');
const PAGE = fs.readFileSync(path.join(ROOT, 'illumenate_lighting/page/ill_portal_operations/ill_portal_operations.js'), 'utf8');
const BUNDLE = fs.readFileSync(path.join(ROOT, 'public/js/illumenate_desk.bundle.js'), 'utf8');
const plain = value => JSON.parse(JSON.stringify(value));
const tick = () => new Promise(resolve => setImmediate(resolve));
const translate = (value, args) => String(value).replace(/\{(\d)\}/g, (_, i) => args[i]);

const ROWS = [
  { queue: 'quotes', queue_label: 'Quote requests', doctype: 'ilL-Quote-Request', name: 'QR-1', title: null, customer: 'CUST-1', customer_name: '<img src=x onerror=alert(1)>', dealer_user: 'd@acme.test', assigned_to: null, due: '2026-11-08', due_state: 'overdue', age_days: 5, state: 'UNDER_REVIEW', next_action_by: 'Staff', modified: 'M1', can_wait: true },
  { queue: 'accounts', queue_label: 'Account review', doctype: 'ilL-Account-Request', name: 'AR-1', title: 'New account', customer: null, customer_name: null, dealer_user: 'new@acme.test', assigned_to: 'me@ill.test', due: null, due_state: 'none', age_days: 0, state: 'Pending', next_action_by: null, modified: 'M1', can_wait: false },
];

function setup(rows = ROWS) {
  const dom = new JSDOM('<body><div id="inbox"></div></body>', { runScripts: 'outside-only', url: 'https://erp.test/app/ill-portal-operations' });
  const w = dom.window;
  const calls = [];
  const routes = [];
  const prompts = [];
  w.__ = translate;
  w.frappe = {
    session: { user: 'me@ill.test' },
    datetime: { str_to_user: value => `user:${value}` },
    call: async options => {
      calls.push(options);
      if (options.method.endsWith('.inbox')) return { message: { rows, total: rows.length, queues: ['quotes', 'accounts'], truncated: [] } };
      return { message: { success: true } };
    },
    set_route: (...args) => routes.push(args),
    show_alert: () => {},
    prompt: (fields, callback, title, primary) => prompts.push({ fields, callback, title, primary }),
  };
  w.eval(INBOX);
  const changed = [];
  const container = w.document.getElementById('inbox');
  w.IllStaffInbox.mount(container, { onChange: () => changed.push(true) });
  return { w, dom, container, calls, routes, prompts, changed };
}

test('the inbox lists rows with due badges, dealer and assignee, and escapes user data', async () => {
  const { container, calls, dom } = setup();
  await tick();
  assert.equal(calls[0].method, 'illumenate_lighting.illumenate_lighting.portal.queues.inbox');
  assert.deepEqual(plain(calls[0].args), { view: 'all', search: '' });
  const rows = container.querySelectorAll('tbody tr');
  assert.equal(rows.length, 2);
  assert.equal(rows[0].dataset.name, 'QR-1');
  assert.equal(rows[0].querySelector('[data-due]').dataset.due, 'overdue');
  assert.match(rows[0].querySelector('[data-due]').className, /red/);
  assert.equal(container.querySelector('img'), null, 'customer names are text, not HTML');
  assert.match(rows[0].textContent, /<img src=x/);
  assert.match(rows[0].textContent, /Unassigned/);
  assert.match(rows[0].textContent, /5 d/);
  assert.match(rows[1].textContent, /new@acme\.test/);
  dom.window.close();
});

test('assign to me claims through the server with the row version, then reloads', async () => {
  const { container, calls, changed, dom } = setup();
  await tick();
  const [first, second] = container.querySelectorAll('tbody tr');
  assert.equal(second.querySelector('[data-action="claim"]'), null, 'already mine');
  first.querySelector('[data-action="claim"]').click();
  await tick(); await tick();
  const claim = calls.find(call => call.method.endsWith('.claim'));
  assert.deepEqual(plain(claim.args), { queue: 'quotes', name: 'QR-1', expected_modified: 'M1' });
  assert.equal(changed.length, 1);
  assert.equal(calls.filter(call => call.method.endsWith('.inbox')).length, 2);
  dom.window.close();
});

test('wait on dealer asks for a message and sends a customer-visible REQUEST_INFO', async () => {
  const { container, calls, prompts, dom } = setup();
  await tick();
  const [first, second] = container.querySelectorAll('tbody tr');
  assert.equal(second.querySelector('[data-action="wait"]'), null, 'account requests have no conversation');
  first.querySelector('[data-action="wait"]').click();
  assert.equal(prompts.length, 1);
  assert.equal(prompts[0].fields[0].reqd, 1);
  prompts[0].callback({ body: 'Which CCT?' });
  await tick(); await tick();
  const reply = calls.find(call => call.method.endsWith('conversations.reply'));
  assert.equal(reply.args.parent_type, 'ilL-Quote-Request');
  assert.equal(reply.args.parent_name, 'QR-1');
  assert.equal(reply.args.visibility, 'Customer');
  assert.equal(reply.args.action, 'REQUEST_INFO');
  assert.ok(reply.args.idempotency_key.length >= 8);
  dom.window.close();
});

test('reply opens the Desk form and views reload the inbox', async () => {
  const { container, calls, routes, dom } = setup();
  await tick();
  container.querySelector('[data-action="reply"]').click();
  assert.deepEqual(routes[0], ['Form', 'ilL-Quote-Request', 'QR-1']);
  container.querySelector('[data-view="overdue"]').click();
  await tick();
  assert.equal(calls.at(-1).args.view, 'overdue');
  assert.equal(container.querySelector('[data-view="overdue"]').getAttribute('aria-pressed'), 'true');
  dom.window.close();
});

test('an empty inbox says nothing is waiting', async () => {
  const { container, dom } = setup([]);
  await tick();
  assert.match(container.textContent, /Nothing is waiting on you/);
  dom.window.close();
});

test('the operations page mounts the inbox from the Desk bundle', () => {
  assert.match(BUNDLE, /import "\.\/desk\/staff_inbox\.js";/);
  assert.match(PAGE, /window\.IllStaffInbox\.mount\(inboxEl/);
  assert.doesNotMatch(INBOX, /innerHTML/);
});
