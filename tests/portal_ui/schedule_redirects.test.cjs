// Plan 11: every script that sends the browser to a schedule page encodes the schedule id,
// so a name with a space, "/", "?" or "#" still opens that schedule.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const jquery = require('jquery');
const { read } = require('./schedule_source.cjs');

const EDIT_FIXTURE = fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/public/js/portal/edit_fixture/page.js'), 'utf8');
const NAME = 'SCH 1/2?x#y';
const ENCODED = '/portal/schedules/SCH%201%2F2%3Fx%23y';

// jsdom cannot navigate, so the script runs with `window`, `location` and `setTimeout` shadowed:
// the redirect lands in nav.location.href and timers wait in nav.timers.
function load(source, exportNames, { html = '', context = {}, globals = {} } = {}) {
  const json = JSON.stringify(context).replace(/</g, '\\u003c');
  const dom = new JSDOM(
    `<body>${html}<script type="application/json" id="edit-fixture-context">${json}</script></body>`,
    { runScripts: 'outside-only', url: 'https://portal.test/portal/schedules/S-1' },
  );
  const w = dom.window;
  const requests = [];
  w.$ = w.jQuery = jquery(w);
  w.$.fn.modal = function () { return this; };
  w.__ = text => text;
  w.console = { log() {}, warn() {}, error() {} };
  w.PortalUI = { escape: value => String(value) };
  w.frappe = {
    call: args => requests.push(args),
    confirm: (message, yes) => yes(),
    msgprint() {},
    show_alert() {},
    utils: { escape_html: value => String(value) },
  };
  Object.assign(w, globals);
  const nav = { timers: [], location: { href: 'https://portal.test/portal/schedules/S-1', reload() { nav.reloaded = true; } } };
  w.__nav = nav;
  const exported = w.eval(
    '(function (window, location, setTimeout) {\n' + source + '\n;return {' + exportNames.join(', ') + '};\n})'
    + '(__nav, __nav.location, function (fn) { __nav.timers.push(fn); })',
  );
  return { dom, w, requests, nav, exported };
}

test('creating a schedule opens the new schedule by its encoded name', () => {
  const html = '<form id="createScheduleForm"><input name="schedule_name" value="x"><button type="submit"></button></form>';
  const { dom, w, requests, nav } = load(read('new'), [], { html });
  w.$('#createScheduleForm').trigger('submit');
  const create = requests.shift();
  assert.match(create.method, /portal\.create_schedule$/);
  create.callback({ message: { success: true, schedule_name: NAME } });
  assert.equal(nav.location.href, ENCODED);
  dom.window.close();
});

test('creating a version opens the new version by its encoded name', () => {
  const globals = { scheduleContext: { schedule_name: 'S-1' } };
  const { dom, requests, nav, exported } = load(read('versions'), ['confirmCreateVersion'], { globals });
  exported.confirmCreateVersion();
  const create = requests.shift();
  assert.match(create.method, /portal\.create_schedule_version$/);
  create.callback({ message: { success: true, new_schedule_name: NAME } });
  assert.equal(nav.location.href, ENCODED);
  dom.window.close();
});

test('a status change that auto-versions opens the new version by its encoded name; otherwise the page reloads', () => {
  const globals = {
    schedule_name: 'S-1',
    scheduleContext: { schedule_status: 'QUOTED', status_classes: {}, export_statuses: {}, status_labels: {}, open_offer: null },
  };
  for (const [message, href, reloaded] of [
    [{ success: true, new_status: 'DRAFT', auto_versioned: true, new_schedule_name: NAME }, ENCODED, undefined],
    [{ success: true, new_status: 'READY' }, 'https://portal.test/portal/schedules/S-1', true],
  ]) {
    const { dom, requests, nav, exported } = load(read('actions'), ['changeStatus'], { globals });
    exported.changeStatus(message.new_status);
    const update = requests.shift();
    assert.match(update.method, /portal\.update_schedule_status$/);
    update.callback({ message });
    assert.equal(nav.location.href, href);
    assert.equal(nav.reloaded, reloaded);
    dom.window.close();
  }
});

test('saving an edited fixture returns to its schedule by the encoded name', () => {
  const context = { schedule_name: NAME, line_idx: 2, configured_fixture_id: 'CF-OLD', fixture_config: null };
  const { dom, requests, nav, exported } = load(EDIT_FIXTURE, ['saveConfiguredFixture'], { context });
  requests.length = 0;
  exported.saveConfiguredFixture({ configured_fixture_id: 'CF-NEW', computed: { manufacturable_overall_length_mm: 1210 } }, () => {});
  const save = requests.shift();
  assert.equal(save.args.schedule_name, NAME, 'the API still gets the raw name');
  save.callback({ message: { success: true } });
  assert.equal(nav.timers.length, 1, 'the redirect waits for the success message');
  nav.timers.shift()();
  assert.equal(nav.location.href, ENCODED);
  dom.window.close();
});
