// CAD plan WP 1.2: the "Drawing styles" panel presets.js adds to the schedule's Import drawing dialog.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const jquery = require('jquery');
const { read } = require('./schedule_source.cjs');

// Mirrors frappe.call: the callback, then `always`.
function respond(call, message) {
  call.callback({ message });
  if (call.always) call.always();
}

function fail(call) {
  call.error({});
  if (call.always) call.always();
}

const CONTEXT = { schedule_name: 'S-1', presets: true, drawing_import: true, lines: [], i18n: {} };
const PRESETS = [
  { name: 'P1', label: '<img src=x onerror=alert(1)>', family: 'LED Tape', template: 'led-hd-sw', cad_code: 'HD27', cad_enabled: true, mine: true, available: true },
  { name: 'P2', label: 'Cove', family: 'LED Neon', template: '<b>non-pnc</b>', cad_code: '', cad_enabled: false, mine: true, available: false },
  { name: 'P3', label: 'Lobby', family: 'Linear Fixture', template: 'FT-1', cad_code: 'LOBBY', cad_enabled: true, mine: false, available: true },
];

function page(context = CONTEXT, modal = true) {
  const json = JSON.stringify(context).replace(/</g, '\\u003c');
  const dialog = modal ? '<div id="importDrawingModal"><div class="modal-body"><input type="file" id="importDrawingFile"></div></div>' : '';
  const dom = new JSDOM(
    `<body>${dialog}<div id="addLineModal"></div>
    <script type="application/json" id="schedule-context">${json}</script></body>`,
    { runScripts: 'outside-only', url: 'https://portal.test/portal/schedules/S-1' },
  );
  const w = dom.window;
  const requests = [];
  w.$ = w.jQuery = jquery(w);
  w.__ = text => text;
  w.frappe = { call: args => requests.push(args) };
  w.eval(read('context') + '\nvar schedule_name = scheduleContext.schedule_name;\n' + read('presets'));
  return { dom, w, $: w.$, requests };
}

function opened(env, presets = PRESETS) {
  env.$('#importDrawingModal').trigger('show.bs.modal');
  const call = env.requests.shift();
  assert.match(call.method, /portal\.presets\.list_presets$/);
  assert.equal(call.type, 'GET');
  assert.deepEqual({ ...call.args }, { schedule_name: 'S-1' });
  respond(call, { success: true, presets: presets.map(preset => ({ ...preset })) });
}

const rowOf = (env, name) => env.$('#drawingStylesRows tr').filter((_, tr) => tr.getAttribute('data-preset') === name);

test('the panel lists presets with family, template, code, switch and availability as text', () => {
  const env = page();
  assert.equal(env.$('#importDrawingModal .modal-body #drawingStyles').length, 1, 'built inside the import dialog');
  assert.equal(env.$('#drawingStyles summary').text(), 'Drawing styles');
  opened(env);
  const rows = env.$('#drawingStylesRows tr');
  assert.equal(rows.length, 3);
  assert.equal(env.$('#drawingStylesRows img, #drawingStylesRows b').length, 0, 'labels are never parsed as HTML');
  const first = rowOf(env, 'P1').find('td');
  assert.equal(first.eq(0).text(), '<img src=x onerror=alert(1)>');
  assert.equal(first.eq(1).text(), 'LED Tape');
  assert.equal(first.eq(3).find('input').val(), 'HD27');
  assert.equal(first.eq(4).find('input').prop('checked'), true);
  assert.equal(first.eq(5).text(), 'Available');
  const second = rowOf(env, 'P2').find('td');
  assert.equal(second.eq(2).text(), '<b>non-pnc</b>');
  assert.equal(second.eq(4).find('input').prop('checked'), false);
  assert.equal(second.eq(5).text(), 'No longer offered');
  const company = rowOf(env, 'P3');
  assert.match(company.text(), /from your company/);
  assert.equal(company.find('input').filter((_, input) => !input.disabled).length, 0, 'company presets are read-only');
  env.dom.window.close();
});

test('editing a code uppercases it and saves it with set_preset_cad', () => {
  const env = page();
  opened(env);
  rowOf(env, 'P2').find('.ill-style-code').val(' cove-1 ').trigger('change');
  const call = env.requests.shift();
  assert.match(call.method, /portal\.presets\.set_preset_cad$/);
  assert.equal(call.type, 'POST');
  assert.deepEqual({ ...call.args }, { preset: 'P2', schedule_name: 'S-1', cad_code: 'COVE-1' });
  respond(call, { success: true, preset: { name: 'P2', cad_code: 'COVE-1', cad_enabled: false } });
  assert.equal(rowOf(env, 'P2').find('.ill-style-code').val(), 'COVE-1');
  assert.equal(env.$('#drawingStylesResult').text(), 'Drawing style saved.');
  // Clearing the code sends an empty code.
  rowOf(env, 'P2').find('.ill-style-code').val('').trigger('change');
  assert.equal(env.requests.shift().args.cad_code, '');
  env.dom.window.close();
});

test('invalid codes are refused before any request, and failed saves revert', () => {
  const env = page();
  opened(env);
  rowOf(env, 'P1').find('.ill-style-code').val('HD 27').trigger('change');
  assert.equal(env.requests.length, 0);
  assert.match(env.$('#drawingStylesResult').text(), /letters, digits and dashes/);
  assert.ok(env.$('#drawingStylesResult').hasClass('text-danger'));
  assert.equal(rowOf(env, 'P1').find('.ill-style-code').val(), 'HD27');
  rowOf(env, 'P1').find('.ill-style-code').val('cove').trigger('change');
  fail(env.requests.shift());
  assert.equal(rowOf(env, 'P1').find('.ill-style-code').val(), 'HD27', 'the saved code comes back');
  assert.equal(env.$('#drawingStylesResult').text(), 'Could not save the drawing style.');
  env.dom.window.close();
});

test('the switch turns a style off and on for the CAD catalog', () => {
  const env = page();
  opened(env);
  rowOf(env, 'P1').find('.ill-style-enabled').prop('checked', false).trigger('change');
  const call = env.requests.shift();
  assert.deepEqual({ ...call.args }, { preset: 'P1', schedule_name: 'S-1', cad_enabled: 0 });
  respond(call, { success: true, preset: { name: 'P1', cad_code: 'HD27', cad_enabled: false } });
  assert.equal(rowOf(env, 'P1').find('.ill-style-enabled').prop('checked'), false);
  rowOf(env, 'P2').find('.ill-style-enabled').prop('checked', true).trigger('change');
  assert.equal(env.requests.shift().args.cad_enabled, 1);
  env.dom.window.close();
});

test('nothing is built without drawing import or presets, and the kill switch removes the panel', () => {
  for (const context of [{ ...CONTEXT, drawing_import: false }, { ...CONTEXT, presets: false }]) {
    const env = page(context);
    assert.equal(env.$('#drawingStyles').length, 0);
    env.$('#importDrawingModal').trigger('show.bs.modal');
    assert.equal(env.requests.length, 0);
    env.dom.window.close();
  }
  let env = page(CONTEXT, false);
  assert.equal(env.$('#drawingStyles').length, 0, 'no dialog, no panel');
  env.dom.window.close();
  env = page();
  env.$('#importDrawingModal').trigger('show.bs.modal');
  respond(env.requests.shift(), { success: true, presets: [], disabled: true });
  assert.equal(env.$('#drawingStyles').length, 0);
  env.$('#importDrawingModal').trigger('show.bs.modal');
  assert.equal(env.requests.length, 0);
  env.dom.window.close();
});

test('an empty library says how to add styles', () => {
  const env = page();
  opened(env, []);
  assert.equal(env.$('#drawingStylesRows tr').length, 0);
  assert.equal(env.$('#drawingStylesResult').text(), 'No saved presets yet. Save one from the configurator.');
  env.dom.window.close();
});
