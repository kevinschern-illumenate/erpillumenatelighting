// Visitors and signed-in users without a company apply for dealer access inline
// (FLOW-5). Needs tests/portal_ui/rendered/dealer-access-*.html from
// tools/check_portal_templates.py.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const PORTAL_UI = fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/public/js/portal_ui.js'), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

function load(name, reply = { success: true, state: 'Pending' }) {
  const html = fs.readFileSync(path.join(__dirname, `rendered/dealer-access-${name}.html`), 'utf8')
    .replace('<body>', '<body><script>' + PORTAL_UI + '</script>');
  const calls = [];
  const dom = new JSDOM(html, {
    runScripts: 'dangerously',
    url: 'https://portal.test/portal/request-dealer-access',
    beforeParse(w) {
      w.frappe = { call(options) { calls.push(options); options.callback({ message: reply }); } };
    },
  });
  return { w: dom.window, doc: dom.window.document, calls };
}

function submit(w, form) {
  form.dispatchEvent(new w.Event('submit', { cancelable: true, bubbles: true }));
}

test('a visitor sees the application form, an SVG icon and a sign-in link, not the account page', () => {
  const { w, doc } = load('guest');
  const form = doc.getElementById('dealerApplicationForm');
  assert.ok(form);
  assert.equal(doc.querySelector('a[href="/portal/account#companyManagement"]'), null);
  assert.ok(doc.querySelector('svg.ill-dealer-access__icon[aria-hidden="true"]'));
  assert.doesNotMatch(doc.body.textContent, /\u{1F512}/u);
  assert.equal(doc.getElementById('dealerSignIn').getAttribute('href'), '/login?redirect-to=/portal/request-dealer-access');
  assert.deepEqual(
    [...form.querySelectorAll('input, textarea')].map(field => field.name),
    ['company', 'full_name', 'email', 'phone', 'website', 'territory', 'message', 'fax_number'],
  );
  const trap = doc.getElementById('dealerFax');
  assert.equal(trap.closest('[aria-hidden="true"]').className, 'ill-dealer-access__trap');
  assert.equal(trap.getAttribute('tabindex'), '-1');
  assert.equal(doc.querySelector('.ill-portal-navigation'), null, 'visitors have no portal to navigate');
  assert.equal(w.localStorage.getItem('ill-finder-claim'), 'CLAIM');
});

test('required fields are checked inline before anything is sent', () => {
  const { w, doc, calls } = load('guest');
  const form = doc.getElementById('dealerApplicationForm');
  form.elements.email.value = 'not-an-email';
  form.elements.website.value = 'studio.test';
  submit(w, form);
  assert.deepEqual(
    [...form.querySelectorAll('.is-invalid')].map(field => field.name),
    ['company', 'full_name', 'email', 'website'],
  );
  assert.equal(calls.length, 0);
});

test('a complete application is sent once and replaced by a confirmation', async () => {
  const { w, doc, calls } = load('guest');
  const form = doc.getElementById('dealerApplicationForm');
  form.elements.company.value = ' Studio Lux ';
  form.elements.full_name.value = 'Dana';
  form.elements.email.value = 'dana@studio.test';
  form.elements.territory.value = 'Pacific Northwest';
  submit(w, form);
  await tick();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].method, 'illumenate_lighting.illumenate_lighting.portal.dealer_applications.apply');
  assert.equal(calls[0].type, 'POST');
  assert.deepEqual({ ...calls[0].args }, {
    company: 'Studio Lux', full_name: 'Dana', email: 'dana@studio.test', phone: '', website: '',
    territory: 'Pacific Northwest', message: '', fax_number: '',
  });
  assert.equal(form.hidden, true);
  const done = doc.getElementById('dealerApplicationDone');
  assert.equal(done.hidden, false);
  assert.match(done.textContent, /email you at dana@studio\.test/);
});

test('a refusal is shown on the form and the form stays', async () => {
  const { w, doc } = load('guest', { success: false, error: 'Email is limited to 140 characters.' });
  const form = doc.getElementById('dealerApplicationForm');
  form.elements.company.value = 'Studio';
  form.elements.full_name.value = 'Dana';
  form.elements.email.value = 'dana@studio.test';
  submit(w, form);
  await tick();
  const error = doc.getElementById('dealerApplicationError');
  assert.equal(error.hidden, false);
  assert.equal(error.textContent, 'Email is limited to 140 characters.');
  assert.equal(form.hidden, false);
});

test('a signed-in user without a company gets the form prefilled', () => {
  const { doc } = load('signed-in');
  const form = doc.getElementById('dealerApplicationForm');
  assert.equal(form.elements.company.value, 'Studio <x>');
  assert.equal(form.elements.full_name.value, 'Dana "D"');
  assert.equal(form.elements.email.value, 'dana@studio.test');
  assert.equal(doc.getElementById('dealerSignIn'), null);
  assert.ok(doc.querySelector('.ill-portal-navigation'));
});

test('an open application shows its status instead of a second form', () => {
  const { doc } = load('pending');
  assert.equal(doc.getElementById('dealerApplicationForm'), null);
  assert.match(doc.getElementById('dealerApplicationPending').textContent, /application AR-<1>/);
  assert.equal(doc.querySelector('.ill-access-gate a[href="/portal/account"]').textContent, 'Reply on your account page');
});

test('someone who already has dealer access is sent to the portal', () => {
  const { doc } = load('approved');
  assert.equal(doc.getElementById('dealerApplicationForm'), null);
  assert.equal(doc.querySelector('a.ill-btn-primary').getAttribute('href'), '/portal');
});
