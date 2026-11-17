// Plan 2.1: the schedule page script lives in public/js/portal/schedule/*.js as classic scripts that
// read #schedule-context. Loaded in template order they must define every global the markup calls.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { JSDOM } = require('jsdom');
const jquery = require('jquery');
const { DIR, ORDER, TEMPLATE, read } = require('./schedule_source.cjs');

function anything() {
  const target = function () { return proxy; };
  const proxy = new Proxy(target, {
    get: (_, key) => (key === Symbol.toPrimitive ? () => '' : key === 'then' ? undefined : proxy),
  });
  return proxy;
}

function page(context, parts) {
  const json = JSON.stringify(context).replace(/</g, '\\u003c');
  const dom = new JSDOM(
    `<body><form id="createScheduleForm"><button type="submit"></button></form>
    <script type="application/json" id="schedule-context">${json}</script></body>`,
    { runScripts: 'outside-only' },
  );
  const w = dom.window;
  w.$ = w.jQuery = jquery(w);
  w.$.fn.popover = w.$.fn.modal = function () { return this; };
  for (const name of ['frappe', 'PortalUI', 'PortalUploads', 'PortalCommercial', 'PortalOrderIntake', 'PortalLineDocuments']) {
    w[name] = anything();
  }
  w.__ = text => text;
  for (const part of parts) w.eval(read(part));
  return { dom, w };
}

const CONTEXT = {
  schedule_name: 'S-1',
  schedule_modified: '2026-11-03 10:00:00.000001',
  schedule_status: 'DRAFT',
  lines: [{ line_id: 'A1', line_key: 'k-1' }],
  status_classes: { DRAFT: 'secondary' },
  export_statuses: {},
  status_labels: { DRAFT: 'Draft' },
  open_offer: null,
  can_issue_packet: false,
  dealer_customer_group: '',
  i18n: { 'Loading...': 'Chargement...' },
};

test('the template loads every schedule script, in order, and keeps no inline page script', () => {
  const files = fs.readdirSync(DIR).filter(name => name.endsWith('.js')).map(name => name.slice(0, -3)).sort();
  assert.deepEqual(files, [...ORDER, 'new'].sort());
  const loop = TEMPLATE.match(/\{% for part in (\[[^\]]+\]) %\}/);
  assert.ok(loop, 'script loop is present');
  assert.deepEqual(JSON.parse(loop[1]), ORDER.filter(name => name !== 'pricing'));
  assert.match(TEMPLATE, /\{% if show_dealer_pricing %\}\n<script src="\{\{ schedule_js \| e \}\}pricing\.js\?v=/);
  assert.match(TEMPLATE, /\{% if is_new %\}\n<script src="\{\{ schedule_js \| e \}\}new\.js\?v=/);
  assert.equal((TEMPLATE.match(/<script>/g) || []).length, 0, 'no inline <script> blocks remain');
});

test('the scripts carry no Jinja', () => {
  for (const name of [...ORDER, 'new']) {
    assert.doesNotMatch(read(name), /\{\{|\{%/, `${name}.js`);
  }
});

test('loading in template order defines every handler the markup calls and reads the context', () => {
  const { dom, w } = page(CONTEXT, ORDER);
  const handlers = new Set([...TEMPLATE.matchAll(/on[a-z]+="([A-Za-z_]+)\(/g)].map(match => match[1]));
  assert.ok(handlers.size >= 10);
  for (const name of handlers) assert.equal(typeof w[name], 'function', name);
  assert.equal(w.schedule_name, 'S-1');
  assert.equal(w.scheduleModified, CONTEXT.schedule_modified);
  assert.deepEqual(JSON.parse(JSON.stringify(w.lineData)), CONTEXT.lines);
  assert.equal(w.statusLabels.DRAFT, 'Draft');
  assert.equal(w.openOffer, null);
  assert.equal(w.REORDER_SCROLL_KEY, 'scheduleScrollY:S-1');
  assert.equal(w.dealerPricingActive, false);
  dom.window.close();
});

test('scheduleText returns the server translation and falls back to the source text', () => {
  const { dom, w } = page(CONTEXT, ['context']);
  assert.equal(w.scheduleText('Loading...'), 'Chargement...');
  assert.equal(w.scheduleText('Select Item...'), 'Select Item...');
  assert.equal(w.scheduleText('constructor'), 'constructor');
  dom.window.close();
});

test('the new-schedule script loads on its own and binds the create form', () => {
  const { dom, w } = page({}, ['new']);
  const events = w.$._data(w.document.getElementById('createScheduleForm'), 'events');
  assert.ok(events && events.submit && events.submit.length === 1);
  dom.window.close();
});
