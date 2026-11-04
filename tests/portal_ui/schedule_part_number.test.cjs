// Plan 3.5: "Add by part number" in the schedule's Add Line dialog.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const jquery = require('jquery');
const { TEMPLATE, read } = require('./schedule_source.cjs');

// Mirrors frappe.call: the callback, then `always` re-enables the button.
function respond(call, message) {
  call.callback({ message });
  if (call.always) call.always();
}

const CONTEXT = { schedule_name: 'S-1', part_number_decode: true, lines: [], i18n: {} };

function page(context = CONTEXT) {
  const json = JSON.stringify(context).replace(/</g, '\\u003c');
  const dom = new JSDOM(
    `<body><form id="addLineForm"><input name="line_id" value="A<1>"><input name="qty" value="3">
      <input name="location" value="Lobby"><textarea name="notes"></textarea>
      <input id="addLinePartNumber"><button type="button" id="addLinePartNumberGo"></button>
      <small id="addLinePartNumberResult"></small></form>
    <script type="application/json" id="schedule-context">${json}</script></body>`,
    { runScripts: 'outside-only', url: 'https://portal.test/portal/schedules/S-1' },
  );
  const w = dom.window;
  const requests = [];
  w.$ = w.jQuery = jquery(w);
  w.__ = text => text;
  if (!(w.crypto && w.crypto.randomUUID)) Object.defineProperty(w, 'crypto', { value: { randomUUID: () => require('node:crypto').randomUUID() }, configurable: true });
  w.frappe = { call: args => requests.push(args) };
  w.eval(read('context') + '\nvar schedule_name = scheduleContext.schedule_name;\n' + read('part_number'));
  const navigations = [];
  w.SchedulePartNumber.navigate = href => navigations.push(href);
  return { dom, w, $: w.$, requests, navigations };
}

test('the template shows the box only behind the kill switch and loads part_number.js', () => {
  assert.match(TEMPLATE, /\{% if part_number_decode_enabled \| default\(false\) %\}\s*<div class="form-group ill-add-by-pn">/);
  assert.match(TEMPLATE, /"part_number_decode": \(part_number_decode_enabled \| default\(false\)\)/);
  assert.match(TEMPLATE, /"bulk", "part_number", "line_import"[\],]/);
});

test('a decoded part number opens the configurator with the dialog details as the draft', () => {
  const { dom, w, $, requests, navigations } = page();
  $('#addLinePartNumber').val('  ill-sh01-s-d  ');
  $('#addLinePartNumberGo').trigger('click');
  const call = requests.shift();
  assert.match(call.method, /portal\.part_number\.decode_part_number$/);
  assert.deepEqual({ ...call.args }, { part_number: 'ill-sh01-s-d', schedule: 'S-1' });
  respond(call, { success: true, status: 'partial', template: 'FT-1', part_number: 'ILL-SH01-S-D' });
  const url = new URL(navigations[0], 'https://portal.test');
  assert.equal(url.pathname, '/portal/configure');
  assert.equal(url.searchParams.get('pn'), 'ILL-SH01-S-D');
  assert.equal(url.searchParams.get('schedule'), 'S-1');
  assert.equal(url.searchParams.get('category'), 'Linear Fixture');
  const id = url.searchParams.get('draft');
  assert.equal(w.sessionStorage.getItem('ill-line-draft-last:S-1'), id);
  const draft = JSON.parse(w.sessionStorage.getItem('ill-line-draft:' + id));
  assert.deepEqual(draft.metadata, { line_id: 'A<1>', location: 'Lobby', qty: 3, notes: '' });
  dom.window.close();
});

test('Enter decodes, and failures are explained as text without navigating', () => {
  const { dom, w, $, requests, navigations } = page();
  $('#addLinePartNumber').val('ILL-ZZ');
  $('#addLinePartNumber')[0].dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
  respond(requests.shift(), { success: true, status: 'unknown', template: null, unmatched: [{ answer: '<b>ZZ</b>', reason: 'no fixture with this series is offered' }] });
  assert.equal($('#addLinePartNumberResult b').length, 0);
  assert.match($('#addLinePartNumberResult').text(), /No product matches this part number\. <b>ZZ<\/b> \(no fixture/);
  $('#addLinePartNumberGo').trigger('click');
  respond(requests.shift(), { success: true, status: 'ambiguous', candidates: [{ label: 'One' }, { label: 'Two' }] });
  assert.match($('#addLinePartNumberResult').text(), /several products: One, Two\./);
  $('#addLinePartNumberGo').trigger('click');
  respond(requests.shift(), { success: false, error: 'LS-48 is not a fixture part number' });
  assert.equal($('#addLinePartNumberResult').text(), 'LS-48 is not a fixture part number');
  assert.equal(navigations.length, 0);
  $('#addLinePartNumber').val('');
  $('#addLinePartNumberGo').trigger('click');
  assert.equal(requests.length, 0);
  dom.window.close();
});

test('the kill switch leaves the dialog alone', () => {
  const { dom, $, requests } = page({ ...CONTEXT, part_number_decode: false });
  $('#addLinePartNumber').val('ILL-X');
  $('#addLinePartNumberGo').trigger('click');
  assert.equal(requests.length, 0);
  dom.window.close();
});
