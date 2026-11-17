// Plan 2.5: portal renderers escape user data by default (html`` helper, toasts, intake scope).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const JS = path.join(__dirname, '../../illumenate_lighting/public/js');
const read = name => fs.readFileSync(path.join(JS, name), 'utf8');

const HOSTILE = ['<script>window.pwned=1</script>', '"><img src=x onerror="window.pwned=1">', "O'Brien & \"Sons\"", 'Ünïcødé — 灯具 💡'];

function setup(...scripts) {
  const dom = new JSDOM('<body><button id="go" data-loading-text="<b>Saving</b>">Go</button></body>', { runScripts: 'outside-only' });
  const w = dom.window;
  w.__ = text => text;
  w.frappe = { call() {}, show_alert() {}, utils: { escape_html: value => value } };
  for (const script of scripts) w.eval(read(script));
  return w;
}

test('html`` escapes every interpolated value and keeps text intact', () => {
  const w = setup('portal_ui.js');
  for (const value of HOSTILE) {
    const box = w.document.createElement('div');
    box.innerHTML = w.PortalUI.html`<p title="${value}">${value}</p>`;
    assert.equal(box.querySelectorAll('script, img').length, 0, value);
    assert.equal(box.querySelector('p').textContent, value);
    assert.equal(box.querySelector('p').getAttribute('title'), value);
  }
  assert.equal(w.pwned, undefined);
});

test('html`` composes nested fragments and arrays without double escaping', () => {
  const w = setup('portal_ui.js');
  const { html, raw } = w.PortalUI;
  const items = ['a<b>', 'c&d'].map(item => html`<li>${item}</li>`);
  const markup = String(html`<ul>${items}</ul>${raw('<i class="fa fa-check"></i>')}${null}${undefined}${0}`);
  assert.equal(markup, '<ul><li>a&lt;b&gt;</li><li>c&amp;d</li></ul><i class="fa fa-check"></i>0');
});

test('plain() returns text from server markup without running it', () => {
  const w = setup('portal_ui.js');
  assert.equal(w.PortalUI.plain('Project not <b>found</b>'), 'Project not found');
  assert.equal(w.PortalUI.plain('<img src=x onerror="window.pwned=1">Bad <script>window.pwned=1</script>'), 'Bad window.pwned=1');
  assert.equal(w.PortalUI.plain(HOSTILE[3]), HOSTILE[3]);
  assert.equal(w.PortalUI.plain(null), '');
  assert.equal(w.pwned, undefined);
});

test('IlluminatePortal.showToast shows the message as text', () => {
  const w = setup('portal_ui.js', 'portal.js');
  for (const value of HOSTILE) {
    w.IlluminatePortal.showToast(value, 'error');
    const toast = w.document.querySelector('.portal-toast:last-of-type');
    assert.equal(toast.querySelectorAll('script, img').length, 0);
    assert.equal(toast.querySelector('.toast-content span').textContent, value);
    assert.equal(toast.getAttribute('role'), 'alert');
    assert.ok(toast.querySelector('i.fa-exclamation-circle'));
  }
  assert.equal(w.pwned, undefined);
});

test('loading buttons show data-loading-text as text and restore the original label', () => {
  const w = setup('portal_ui.js', 'portal.js');
  w.IlluminatePortal.initLoadingStates();
  const button = w.document.getElementById('go');
  button.click();
  assert.equal(button.disabled, true);
  assert.equal(button.querySelector('b'), null);
  assert.equal(button.textContent, ' <b>Saving</b>');
  assert.ok(button.querySelector('i.fa-spinner'));
  w.IlluminatePortal.resetButton(button);
  assert.equal(button.innerHTML, 'Go');
  assert.equal(button.disabled, false);
});

test('order intake scope escapes basis and line values', async () => {
  const w = setup('portal_ui.js', 'portal_order_intake.js');
  let fields;
  w.PortalUploads = {
    call: async () => ({
      choices: {},
      defaults: {},
      scope: {
        basis: HOSTILE[0],
        lines: [
          { line_id: HOSTILE[1], qty: 2, product_type: HOSTILE[2] },
          { line_id: HOSTILE[3], qty: 1, manufacturer_type: 'OTHER' },
        ],
      },
    }),
  };
  w.PortalDialog = { create: async options => { fields = options.fields; return { show() {}, fields_dict: {} }; } };
  Object.defineProperty(w, 'crypto', { value: { randomUUID: () => 'k' }, configurable: true });
  await w.PortalOrderIntake.open({ schedule_name: 'S-1' });
  const box = w.document.createElement('div');
  box.innerHTML = fields.find(field => field.fieldname === 'scope').options;
  assert.equal(box.querySelectorAll('script, img').length, 0);
  assert.equal(box.querySelector('p').textContent, HOSTILE[0]);
  const items = [...box.querySelectorAll('li')].map(li => li.textContent);
  assert.deepEqual(items, [`${HOSTILE[1]}: 2 - ${HOSTILE[2]}`, `${HOSTILE[3]}: 1 - OTHER - EXCLUDED from sellable order`]);
  assert.equal(box.querySelector('a').getAttribute('href'), '/portal/account#companyManagement');
  assert.equal(w.pwned, undefined);
});
