// Plan 3.6: "Start from a saved preset" in the schedule's Add Line dialog.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const jquery = require('jquery');
const { TEMPLATE, read } = require('./schedule_source.cjs');

// Mirrors frappe.call: the callback, then `always`.
function respond(call, message) {
  call.callback({ message });
  if (call.always) call.always();
}

const CONTEXT = { schedule_name: 'S-1', presets: true, lines: [], i18n: {} };
const PRESETS = [
  { name: 'P1', label: '<b>Lobby</b>', family: 'Linear Fixture', template: 'FT-1', shared: true, mine: true, available: true },
  { name: 'P2', label: 'Cove', family: 'LED Tape', template: 'TN-1', shared: true, mine: false, available: false },
];

function page(context = CONTEXT) {
  const json = JSON.stringify(context).replace(/</g, '\\u003c');
  const dom = new JSDOM(
    `<body><div id="addLineModal"><form id="addLineForm"><input name="line_id" value="A1"><input name="qty" value="2">
      <input name="location" value="Lobby"><textarea name="notes"></textarea>
      <div class="ill-add-from-preset"><select id="addLinePreset"><option value="">Choose</option></select>
      <button type="button" id="addLinePresetGo"></button><button type="button" id="addLinePresetDelete" disabled></button>
      <small id="addLinePresetResult"></small></div></form></div>
    <script type="application/json" id="schedule-context">${json}</script></body>`,
    { runScripts: 'outside-only', url: 'https://portal.test/portal/schedules/S-1' },
  );
  const w = dom.window;
  const requests = [];
  w.$ = w.jQuery = jquery(w);
  w.__ = text => text;
  if (!(w.crypto && w.crypto.randomUUID)) Object.defineProperty(w, 'crypto', { value: { randomUUID: () => require('node:crypto').randomUUID() }, configurable: true });
  w.frappe = { call: args => requests.push(args) };
  w.eval(read('context') + '\nvar schedule_name = scheduleContext.schedule_name;\n' + read('presets'));
  const navigations = [];
  const confirms = [];
  w.SchedulePresets.navigate = href => navigations.push(href);
  w.SchedulePresets.confirm = message => { confirms.push(message); return true; };
  return { dom, w, $: w.$, requests, navigations, confirms };
}

function opened(env) {
  env.$('#addLineModal').trigger('show.bs.modal');
  const call = env.requests.shift();
  assert.match(call.method, /portal\.presets\.list_presets$/);
  assert.equal(call.type, 'GET');
  assert.deepEqual({ ...call.args }, { schedule_name: 'S-1' });
  respond(call, { success: true, presets: PRESETS });
}

test('the template gates the picker and loads presets.js', () => {
  assert.match(TEMPLATE, /\{% if presets_enabled \| default\(false\) %\}\s*<div class="form-group ill-add-from-preset">/);
  assert.match(TEMPLATE, /"presets": \(presets_enabled \| default\(false\)\)/);
  assert.match(TEMPLATE, /"line_import", "presets"[\],]/);
});

test('opening the dialog lists presets as text, marking shared and withdrawn ones', () => {
  const env = page();
  opened(env);
  const options = env.$('#addLinePreset option').toArray().slice(1);
  assert.deepEqual(options.map(o => o.value), ['P1', 'P2']);
  assert.equal(options[0].textContent, '<b>Lobby</b> — Linear Fixture (shared)');
  assert.equal(env.$('#addLinePreset b').length, 0, 'labels are never parsed as HTML');
  assert.equal(options[1].textContent, 'Cove — LED Tape (from your company, no longer offered)');
  env.dom.window.close();
});

test('choosing a preset opens the configurator with the dialog details as the draft', () => {
  const env = page();
  opened(env);
  env.$('#addLinePresetGo').trigger('click');
  assert.equal(env.$('#addLinePresetResult').text(), 'Choose a preset.');
  assert.equal(env.navigations.length, 0);
  env.$('#addLinePreset').val('P2').trigger('change');
  assert.equal(env.$('#addLinePresetDelete').prop('disabled'), true, 'company presets cannot be deleted here');
  env.$('#addLinePresetGo').trigger('click');
  const url = new URL(env.navigations[0], 'https://portal.test');
  assert.equal(url.pathname, '/portal/configure');
  assert.equal(url.searchParams.get('category'), 'LED Tape');
  assert.equal(url.searchParams.get('preset'), 'P2');
  assert.equal(url.searchParams.get('schedule'), 'S-1');
  const draft = JSON.parse(env.w.sessionStorage.getItem('ill-line-draft:' + url.searchParams.get('draft')));
  assert.deepEqual(draft.metadata, { line_id: 'A1', location: 'Lobby', qty: 2, notes: '' });
  env.dom.window.close();
});

test('own presets can be deleted after confirmation', () => {
  const env = page();
  opened(env);
  env.$('#addLinePreset').val('P1').trigger('change');
  assert.equal(env.$('#addLinePresetDelete').prop('disabled'), false);
  env.$('#addLinePresetDelete').trigger('click');
  assert.equal(env.confirms[0], 'Delete preset <b>Lobby</b>?');
  const call = env.requests.shift();
  assert.match(call.method, /portal\.presets\.delete_preset$/);
  assert.equal(call.type, 'POST');
  assert.deepEqual({ ...call.args }, { preset: 'P1', schedule_name: 'S-1' });
  respond(call, { success: true });
  assert.deepEqual(env.$('#addLinePreset option').toArray().slice(1).map(o => o.value), ['P2']);
  assert.equal(env.$('#addLinePresetResult').text(), 'Preset deleted.');
  env.dom.window.close();
});

test('the server kill switch hides the picker, and the page flag binds nothing', () => {
  let env = page();
  env.$('#addLineModal').trigger('show.bs.modal');
  respond(env.requests.shift(), { success: true, presets: [], disabled: true });
  assert.ok(env.$('.ill-add-from-preset').hasClass('d-none'));
  env.dom.window.close();
  env = page({ ...CONTEXT, presets: false });
  env.$('#addLineModal').trigger('show.bs.modal');
  env.$('#addLinePresetGo').trigger('click');
  assert.equal(env.requests.length, 0);
  assert.equal(env.navigations.length, 0);
  env.dom.window.close();
});
