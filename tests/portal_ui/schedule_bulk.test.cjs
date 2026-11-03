// Plan 3.3: select schedule lines and edit, delete, move, copy or request drawings in bulk.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const jquery = require('jquery');
const { TEMPLATE, read } = require('./schedule_source.cjs');

const CONTEXT = {
  schedule_name: 'S-1',
  schedule_modified: '2026-11-03 10:00:00',
  project_name: 'P-1',
  bulk_edit: true,
  line_copy: true,
  lines: [],
  i18n: { '{0} selected': '{0} sélectionnée(s)' },
};

function row(key, label) {
  return `<tr data-line-key="${key}"><td class="col-drag-handle"><input type="checkbox" class="line-select" data-line-key="${key}"></td>
    <td class="col-line-id">${label}</td></tr>`;
}

function page(context = CONTEXT) {
  const json = JSON.stringify(context).replace(/</g, '\\u003c');
  const dom = new JSDOM(
    `<body><table><thead><tr><th><input type="checkbox" id="lineSelectAll"></th></tr></thead><tbody>
      ${row('k-1', 'A1')}${row('k-2', 'B&lt;2&gt;')}${row('k-3', 'C3')}</tbody></table>
    <div id="bulkActionBar" hidden><strong id="bulkSelectionCount"></strong>
      ${['qty', 'location', 'line_id', 'notes', 'move', 'copy', 'drawings', 'delete', 'clear'].map(a => `<button data-bulk-action="${a}"></button>`).join('')}</div>
    <div id="bulkEditModal"><h5 id="bulkEditTitle"></h5><p id="bulkEditSummary"></p>
      <div data-bulk-field="qty"><input id="bulkEditQty"></div><div data-bulk-field="location"><input id="bulkEditLocation"></div>
      <div data-bulk-field="line_id"><input id="bulkEditLineId"></div><div data-bulk-field="notes"><textarea id="bulkEditNotes"></textarea></div>
      <div data-bulk-field="move"><select id="bulkEditTarget"></select></div>
      <div id="bulkEditErrors" hidden></div><button id="bulkEditConfirm"></button></div>
    <script type="application/json" id="schedule-context">${json}</script></body>`,
    { runScripts: 'outside-only', url: 'https://portal.test/portal/schedules/S-1' },
  );
  const w = dom.window;
  const requests = [];
  const messages = [];
  const confirms = [];
  const copies = [];
  w.$ = w.jQuery = jquery(w);
  w.$.fn.modal = function () { return this; };
  w.__ = text => text;
  w.frappe = {
    call: args => requests.push(args),
    msgprint: message => messages.push(message),
    confirm: (message, yes) => confirms.push({ message, yes }),
  };
  w.ScheduleCopy = { open: keys => copies.push(keys) };
  w.eval(read('context') + '\nvar schedule_name = scheduleContext.schedule_name;\n' + read('bulk'));
  const reloads = [];
  const navigations = [];
  w.ScheduleBulk.reload = () => reloads.push(true);
  w.ScheduleBulk.navigate = href => navigations.push(href);
  const select = (...keys) => {
    for (const key of keys) {
      const box = w.document.querySelector(`.line-select[data-line-key="${key}"]`);
      box.checked = true;
      box.dispatchEvent(new w.Event('change', { bubbles: true }));
    }
  };
  const act = action => w.document.querySelector(`[data-bulk-action="${action}"]`).click();
  return { dom, w, $: w.$, requests, messages, confirms, copies, reloads, navigations, select, act };
}

test('the template gates selection, the bar and the modal behind the kill switch and loads bulk.js', () => {
  assert.match(TEMPLATE, /has-bulk-select\{% endif %\}/);
  assert.match(TEMPLATE, /\{% if bulk_edit_enabled \| default\(false\) %\}<input type="checkbox" id="lineSelectAll"/);
  assert.match(TEMPLATE, /\{% if bulk_edit_enabled \| default\(false\) %\}\s*<input type="checkbox" class="line-select" data-line-key="\{\{ \(line\.get\('line_key'\)/);
  assert.match(TEMPLATE, /\{% if bulk_edit_enabled \| default\(false\) %\}\s*<div id="bulkActionBar"[^>]* hidden>/);
  assert.match(TEMPLATE, /\{% if line_copy_enabled \| default\(false\) %\}\s*<button[^>]*data-bulk-action="copy"/);
  assert.match(TEMPLATE, /\{% if bulk_edit_enabled \| default\(false\) %\}\s*<div class="modal fade" id="bulkEditModal"/);
  assert.match(TEMPLATE, /"bulk_edit": \(bulk_edit_enabled \| default\(false\)\)/);
});

test('selecting lines shows the bar, counts them and tracks select-all', () => {
  const { dom, w, $, select } = page();
  assert.equal($('#bulkActionBar').prop('hidden'), true);
  select('k-1', 'k-2');
  assert.equal($('#bulkActionBar').prop('hidden'), false);
  assert.equal($('#bulkSelectionCount').text(), '2 sélectionnée(s)');
  const all = w.document.getElementById('lineSelectAll');
  assert.equal(all.indeterminate, true);
  assert.equal($('tr[data-line-key="k-1"]').hasClass('table-active'), true);
  all.checked = true;
  all.dispatchEvent(new w.Event('change', { bubbles: true }));
  assert.deepEqual([...w.ScheduleBulk.keys()], ['k-1', 'k-2', 'k-3']);
  assert.equal(all.indeterminate, false);
  w.document.querySelector('[data-bulk-action="clear"]').click();
  assert.equal(w.ScheduleBulk.keys().length, 0);
  assert.equal($('#bulkActionBar').prop('hidden'), true);
  dom.window.close();
});

test('a field edit shows only that field and posts every key with the page revision', () => {
  const { dom, $, requests, reloads, select, act } = page();
  select('k-1', 'k-3');
  act('location');
  assert.equal($('[data-bulk-field="location"]').prop('hidden'), false);
  assert.equal($('[data-bulk-field="qty"]').prop('hidden'), true);
  assert.match($('#bulkEditSummary').text(), /Applies to 2 selected line/);
  $('#bulkEditLocation').val('Level 2');
  $('#bulkEditConfirm').trigger('click');
  const call = requests.shift();
  assert.match(call.method, /portal\.bulk_lines\.bulk_update_lines$/);
  assert.equal(call.type, 'POST');
  assert.deepEqual(
    { ...call.args, line_keys: JSON.parse(call.args.line_keys), changes: JSON.parse(call.args.changes) },
    { schedule: 'S-1', line_keys: ['k-1', 'k-3'], changes: { location: 'Level 2' }, expected_modified: '2026-11-03 10:00:00' },
  );
  call.callback({ message: { success: true, count: 2 } });
  assert.equal(reloads.length, 1);
  dom.window.close();
});

test('a bad quantity is caught before posting and server errors render as text', () => {
  const { dom, $, requests, reloads, select, act } = page();
  select('k-1', 'k-2');
  act('qty');
  $('#bulkEditQty').val('2.5');
  $('#bulkEditConfirm').trigger('click');
  assert.equal(requests.length, 0);
  assert.equal($('#bulkEditErrors').prop('hidden'), false);
  $('#bulkEditQty').val('3');
  $('#bulkEditConfirm').trigger('click');
  const call = requests.shift();
  assert.deepEqual({ ...JSON.parse(call.args.changes) }, { qty: '3' });
  call.callback({ message: { success: false, error: 'No lines were changed.', errors: [{ line: '<img src=x onerror=alert(1)>', error: 'Locked' }] } });
  assert.equal(reloads.length, 0);
  assert.equal($('#bulkEditErrors img').length, 0);
  assert.equal($('#bulkEditErrors li').text(), '<img src=x onerror=alert(1)>: Locked');
  assert.equal($('#bulkEditErrors p').text(), 'No lines were changed.');
  dom.window.close();
});

test('delete asks first, then posts the delete action', () => {
  const { dom, requests, confirms, select, act } = page();
  select('k-2');
  act('delete');
  assert.equal(requests.length, 0);
  assert.match(confirms[0].message, /Delete 1 selected line/);
  confirms[0].yes();
  assert.deepEqual({ ...JSON.parse(requests[0].args.changes) }, { action: 'delete' });
  assert.deepEqual([...JSON.parse(requests[0].args.line_keys)], ['k-2']);
  dom.window.close();
});

test('move lists editable targets as text and sends the target revision', () => {
  const { dom, $, requests, select, act } = page();
  select('k-1');
  act('move');
  const targets = requests.shift();
  assert.match(targets.method, /line_copy\.copy_targets$/);
  assert.deepEqual({ ...targets.args }, { source_schedule: 'S-1' });
  targets.callback({ message: { schedules: [{ value: 'S-2', label: '<b>Phase 2</b>', project: 'Tower', modified: 'rev-2' }] } });
  assert.equal($('#bulkEditTarget b').length, 0);
  assert.equal($('#bulkEditTarget option').eq(1).text(), '<b>Phase 2</b> (Tower)');
  $('#bulkEditConfirm').trigger('click');
  assert.equal(requests.length, 0, 'a target is required');
  $('#bulkEditTarget').val('S-2');
  $('#bulkEditConfirm').trigger('click');
  assert.deepEqual(
    { ...JSON.parse(requests[0].args.changes) },
    { action: 'move', target_schedule: 'S-2', target_modified: 'rev-2' },
  );
  dom.window.close();
});

test('copy hands the selection to the copy dialog and drawings opens a prefilled request', () => {
  const { dom, copies, navigations, select, act } = page();
  select('k-1', 'k-2');
  act('copy');
  assert.deepEqual([...copies[0]], ['k-1', 'k-2']);
  act('drawings');
  const url = new URL(navigations[0], 'https://portal.test');
  assert.equal(url.pathname, '/portal/drawings');
  assert.equal(url.searchParams.get('project'), 'P-1');
  assert.equal(url.searchParams.get('fixture_reference'), 'Schedule S-1: A1, B<2>');
  dom.window.close();
});

test('the kill switch leaves the page untouched', () => {
  const { dom, $, select } = page({ ...CONTEXT, bulk_edit: false });
  select('k-1');
  assert.equal($('#bulkActionBar').prop('hidden'), true);
  dom.window.close();
});
