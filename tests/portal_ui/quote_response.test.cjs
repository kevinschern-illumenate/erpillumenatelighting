const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const jquery = require('jquery');
const { JSDOM, VirtualConsole } = require('jsdom');
const tick = () => new Promise(resolve => setTimeout(resolve, 10));
const ui = fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/public/js/portal_ui.js'), 'utf8');

// Render with tools/check_portal_templates.py so this exercises the inherited layout.
function setup() {
  const calls = [], navigation = [];
  const virtualConsole = new VirtualConsole();
  virtualConsole.on('jsdomError', error => {
    if (error.message.startsWith('Not implemented: navigation')) navigation.push(error);
    else throw error;
  });
  const html = fs.readFileSync(path.join(__dirname, 'rendered/quote-detail.html'), 'utf8')
    .replace('<body>', '<body><script>' + ui + '</script>');
  const dom = new JSDOM(html, {
    runScripts: 'dangerously', virtualConsole, url: 'https://portal.test/portal/quotes/OFFER-00001',
    beforeParse(w) {
      w.__ = value => value;
      w.frappe = {
        ready: fn => fn(),
        call(options) {
          const deferred = jquery(w).Deferred();
          calls.push({ ...options, resolve: data => deferred.resolve(data), reject: data => deferred.reject(data) });
          return deferred.promise();
        },
      };
    },
  });
  const doc = dom.window.document;
  doc.getElementById('offer-po').value = 'PO-123';
  doc.getElementById('offer-date').value = '2026-11-01';
  doc.getElementById('offer-note').value = 'Please ship to the site';
  doc.getElementById('offer-ack').checked = true;
  const click = action => doc.querySelector(`[data-response="${action}"]`).click();
  const status = () => doc.getElementById('offer-response-status').textContent;
  return { dom, doc, calls, navigation, click, status };
}

test('acceptance reads the offer from the shared layout and sends one request', async t => {
  const { dom, doc, calls, navigation, click, status } = setup();
  t.after(() => dom.window.close());
  click('ACCEPT');
  await tick();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].method, 'illumenate_lighting.illumenate_lighting.portal.offers.respond');
  assert.equal(calls[0].type, 'POST');
  assert.deepEqual({ ...calls[0].args }, {
    offer_name: 'OFFER-00001', expected_hash: 'a'.repeat(64), action: 'ACCEPT',
    note: 'Please ship to the site', po_no: 'PO-123', requested_date: '2026-11-01',
  });
  assert.ok([...doc.querySelectorAll('#offer-response button')].every(button => button.disabled));
  click('ACCEPT');
  assert.equal(calls.length, 1);
  calls[0].resolve({ message: { offer: 'OFFER-00001', state: 'ACCEPTED', sales_order: 'SO-1' } });
  await tick();
  assert.equal(navigation.length, 1);
  assert.doesNotMatch(status(), /not confirmed/);
});

test('validation and network errors show a reason and preserve inputs for retry', async t => {
  const { dom, doc, calls, navigation, click, status } = setup();
  t.after(() => dom.window.close());
  click('ACCEPT');
  assert.equal(calls.length, 1);
  calls[0].reject({ responseJSON: {
    _server_messages: JSON.stringify([JSON.stringify({ message: 'This offer has <b>expired</b>' })]),
  } });
  await tick();
  assert.match(status(), /This offer has expired/);
  assert.match(status(), /entries are preserved/);
  assert.equal(doc.getElementById('offer-response-status').querySelector('b'), null);
  assert.equal(doc.getElementById('offer-po').value, 'PO-123');
  assert.equal(doc.getElementById('offer-note').value, 'Please ship to the site');
  assert.equal(doc.getElementById('offer-date').value, '2026-11-01');
  assert.equal(doc.getElementById('offer-ack').checked, true);
  click('ACCEPT');
  assert.equal(calls.length, 2);
  assert.deepEqual({ ...calls[1].args }, { ...calls[0].args });
  calls[1].reject({ status: 0 });
  await tick();
  assert.match(status(), /offline/);
  assert.equal(navigation.length, 0);
  assert.ok([...doc.querySelectorAll('#offer-response button')].every(button => !button.disabled));
});

test('an incomplete acceptance receipt leaves the form available for retry', async t => {
  const { dom, doc, calls, navigation, click, status } = setup();
  t.after(() => dom.window.close());
  click('ACCEPT');
  assert.equal(calls.length, 1);
  calls[0].resolve({ message: { offer: 'OFFER-00001', state: 'ACCEPTED' } });
  await tick();
  assert.match(status(), /not confirm/);
  assert.equal(navigation.length, 0);
  assert.equal(doc.getElementById('offer-po').value, 'PO-123');
  assert.equal(doc.querySelector('[data-response="ACCEPT"]').disabled, false);
});

test('revision and decline responses also wait for a confirmed receipt', async t => {
  for (const [action, state] of [['REQUEST_REVISION', 'REVISION_REQUESTED'], ['DECLINE', 'DECLINED']]) {
    const { dom, calls, navigation, click } = setup();
    t.after(() => dom.window.close());
    click(action);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].args.action, action);
    calls[0].resolve({ message: { offer: 'OFFER-00001', state } });
    await tick();
    assert.equal(navigation.length, 1);
  }
});
