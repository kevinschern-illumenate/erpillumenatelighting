// The schedule page shows where it stands and one next step (FLOW-2). Needs
// tests/portal_ui/rendered/schedule-*.html from tools/check_portal_templates.py.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { JSDOM } = require('jsdom');

const SOURCE = fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/templates/pages/schedule.html'), 'utf8');

function load(name) {
  return new JSDOM(fs.readFileSync(path.join(__dirname, `rendered/${name}.html`), 'utf8')).window.document;
}

test('a ready schedule offers one primary action and shows its commercial thread', () => {
  const doc = load('schedule-ready');
  const current = doc.querySelector('#scheduleSteps [aria-current="step"]');
  assert.equal(current.dataset.step, 'ready');
  assert.equal(doc.querySelectorAll('#scheduleSteps .is-done').length, 1);
  assert.equal(doc.querySelectorAll('#scheduleActions .btn-primary').length, 1);
  assert.equal(doc.querySelector('#nextStepPrimary').dataset.nextAction, 'quote');
  assert.equal(doc.querySelector('#nextStepSecondary').dataset.nextAction, 'order');
  assert.equal(doc.querySelectorAll('#scheduleActions .btn-success').length, 0, 'no competing green buttons');
  const request = doc.querySelector('#commercialRequests a');
  assert.equal(request.getAttribute('href'), '/portal/quote-requests/QR-1');
  assert.match(doc.querySelector('#commercialRequests').textContent, /With Sam <S>/);
  assert.match(doc.querySelector('.ill-commercial-message').textContent, /Can you confirm <b>finish<\/b>\?/);
  assert.match(doc.querySelector('#commercialOffers').textContent, /No quote issued yet/);
});

test('a draft explains why it cannot be marked ready and links to the first open line', () => {
  const doc = load('schedule-draft');
  const primary = doc.querySelector('#nextStepPrimary');
  assert.equal(primary.textContent, 'Mark ready');
  assert.ok(primary.disabled);
  assert.equal(primary.getAttribute('aria-describedby'), 'nextStepReason');
  assert.equal(doc.querySelector('#nextStepReason').textContent, 'Configure these lines first: A1, Row 2');
  const banner = doc.querySelector('#unconfiguredBanner');
  assert.match(banner.textContent, /Unconfigured lines: 2/);
  assert.equal(banner.querySelector('a').getAttribute('href'), '#line-key-1');
  assert.equal(doc.querySelector('#commercialPanel'), null);
  const menu = [...doc.querySelectorAll('[data-schedule-menu]')].map(item => item.dataset.scheduleMenu + (item.dataset.status || ''));
  assert.deepEqual(menu, ['version', 'statusREADY']);
});

test('next-step buttons and the overflow menu call the page actions', () => {
  const start = SOURCE.indexOf('// FLOW-2: the header');
  const end = SOURCE.indexOf('\n});\n', start) + 5;
  assert.ok(start > 0 && end > start);
  const calls = [];
  let handler;
  const context = {
    document: { addEventListener(type, fn) { handler = fn; } },
    changeStatus: status => calls.push('status:' + status),
    requestQuote: () => calls.push('quote'),
    createSalesOrder: () => calls.push('order'),
    createNewVersion: () => calls.push('version'),
  };
  vm.runInNewContext(SOURCE.slice(start, end), context);
  const target = attrs => ({ closest: selector => (selector in attrs ? attrs[selector] : null) });
  const click = el => handler({ target: el, preventDefault() {} });
  click(target({ '[data-next-action]': { disabled: false, dataset: { nextAction: 'ready' } } }));
  click(target({ '[data-next-action]': { disabled: true, dataset: { nextAction: 'quote' } }, '[data-schedule-menu]': null }));
  click(target({ '[data-next-action]': { disabled: false, dataset: { nextAction: 'order' } } }));
  click(target({ '[data-next-action]': null, '[data-schedule-menu]': { dataset: { scheduleMenu: 'version' } } }));
  click(target({ '[data-next-action]': null, '[data-schedule-menu]': { dataset: { scheduleMenu: 'status', status: 'DRAFT' } } }));
  assert.deepEqual(calls, ['status:READY', 'order', 'version', 'status:DRAFT']);
});
