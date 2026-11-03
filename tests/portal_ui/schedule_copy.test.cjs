// Plan 3.2: "Configure similar" and "Copy to another schedule" on the schedule page.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const jquery = require('jquery');
const { TEMPLATE, read } = require('./schedule_source.cjs');

const CONTEXT = {
  schedule_name: 'S-1',
  schedule_modified: '2026-11-03 10:00:00',
  line_copy: true,
  lines: [{ line_id: 'A<1>', line_key: 'k-1', qty: 4, location: 'Lobby', notes: 'keep me out' }],
  i18n: { '(similar)': '(similaire)' },
};

const MODAL = `<div id="copyLinesModal"><p id="copyLinesSummary"></p><select id="copyLinesTarget"></select>
  <button id="copyLinesConfirm" disabled></button></div>`;

function page() {
  const json = JSON.stringify(CONTEXT).replace(/</g, '\\u003c');
  const dom = new JSDOM(
    `<body><table><tr data-line-idx="0" data-line-key="k-1"><td>
      <button data-copy-action="similar" data-line-index="0"></button>
      <button data-copy-action="copy" data-line-index="0"></button></td></tr></table>${MODAL}
    <script type="application/json" id="schedule-context">${json}</script></body>`,
    { runScripts: 'outside-only', url: 'https://portal.test/portal/schedules/S-1' },
  );
  const w = dom.window;
  const requests = [];
  const messages = [];
  w.$ = w.jQuery = jquery(w);
  w.$.fn.modal = function () { return this; };
  w.__ = text => text;
  if (!(w.crypto && w.crypto.randomUUID)) Object.defineProperty(w, 'crypto', { value: { randomUUID: () => require('node:crypto').randomUUID() }, configurable: true });
  w.frappe = { call: args => requests.push(args), msgprint: message => messages.push(message) };
  w.eval(read('context') + '\nvar schedule_name = scheduleContext.schedule_name;\n' + read('copy'));
  const navigations = [];
  w.ScheduleCopy.navigate = href => navigations.push(href);
  return { dom, w, $: w.$, requests, messages, navigations };
}

test('the template offers both actions only behind the kill switch and loads copy.js', () => {
  assert.match(TEMPLATE, /\{% if line_copy_enabled \| default\(false\) %\}[\s\S]*data-copy-action="similar"[\s\S]*data-copy-action="copy"/);
  assert.match(TEMPLATE, /\{% if line\.get\('can_configure_similar'\) %\}/);
  assert.match(TEMPLATE, /"versions", "copy", "bulk", "part_number"\] %\}/);
});

test('configure similar stores the line details as an add-line draft and opens the configurator', () => {
  const { dom, w, $, navigations } = page();
  $('[data-copy-action="similar"]')[0].click();
  assert.equal(navigations.length, 1);
  const url = new URL(navigations[0], 'https://portal.test');
  assert.equal(url.pathname, '/portal/configure');
  assert.equal(url.searchParams.get('schedule'), 'S-1');
  assert.equal(url.searchParams.get('similar_to'), 'k-1');
  const draft = JSON.parse(w.sessionStorage.getItem('ill-line-draft:' + url.searchParams.get('draft')));
  assert.equal(draft.schedule, 'S-1');
  assert.deepEqual(draft.metadata, { line_id: 'A<1> (similaire)', location: 'Lobby', qty: 4, notes: '' });
  dom.window.close();
});

test('copy lists editable targets as text and posts the line keys with the target revision', () => {
  const { dom, $, requests, messages } = page();
  $('[data-copy-action="copy"]')[0].click();
  const targets = requests.shift();
  assert.match(targets.method, /line_copy\.copy_targets$/);
  assert.deepEqual({ ...targets.args }, { source_schedule: 'S-1' });
  targets.callback({ message: { success: true, schedules: [{ value: 'S-2', label: '<b>Phase 2</b>', project: 'Tower', modified: 'rev-2' }] } });
  const $select = $('#copyLinesTarget');
  assert.equal($select.find('b').length, 0);
  assert.equal($select.find('option').eq(1).text(), '<b>Phase 2</b> (Tower)');
  assert.equal($('#copyLinesConfirm').prop('disabled'), true);
  $select.val('S-2').trigger('change');
  assert.equal($('#copyLinesConfirm').prop('disabled'), false);
  $('#copyLinesConfirm').trigger('click');
  const copy = requests.shift();
  assert.match(copy.method, /line_copy\.copy_lines$/);
  assert.equal(copy.type, 'POST');
  assert.deepEqual(
    { ...copy.args, line_keys: JSON.parse(copy.args.line_keys) },
    { source_schedule: 'S-1', line_keys: ['k-1'], target_schedule: 'S-2', expected_modified: 'rev-2' },
  );
  copy.callback({ message: { success: true, schedule: 'S-2 <x>', copied: 2 } });
  assert.match(messages[0], /Copied 2 line\(s\)\./);
  assert.match(messages[0], /href="\/portal\/schedules\/S-2%20%3Cx%3E"/);
  dom.window.close();
});

test('no editable targets leaves the copy button disabled', () => {
  const { dom, $, requests } = page();
  $('[data-copy-action="copy"]')[0].click();
  requests.shift().callback({ message: { success: true, schedules: [] } });
  assert.equal($('#copyLinesTarget').prop('disabled'), true);
  assert.match($('#copyLinesTarget').text(), /No other Draft or Ready schedules/);
  assert.equal($('#copyLinesConfirm').prop('disabled'), true);
  dom.window.close();
});
