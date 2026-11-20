// Draw-to-quote plan 2.7: importing an AutoCAD drawing package on the schedule page.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const jquery = require('jquery');
const { TEMPLATE, read } = require('./schedule_source.cjs');

const CONTEXT = { schedule_name: 'S-1', schedule_modified: 'rev-1', drawing_import: true, lines: [], i18n: {} };

const PREVIEW = {
  success: true,
  rows: [
    { id: 'L1-01', fixture_type: '<img src=x onerror=alert(1)>', style: 'HD 27K', drawn_length_in: 96, server_length_in: 94.49, action: 'add', status: 'ok', messages: ['Builds 94.49 in'] },
    { id: 'L3-01', fixture_type: 'L3', style: 'non-pnc-sw', drawn_length_in: 72, status: 'needs_choice', messages: ['Choose finish'], parts: [{ part: 'build', missing: ['finish'] }] },
  ],
  other_lines: [{ id: 'OTHER.X1', fixture_type: 'X1', summary: 'Acme', status: 'ok', action: 'update', messages: [] }],
  removals: [{ id: 'L9-01', fixture_type: 'L9', status: 'ok', action: 'remove', messages: ['gone'] }],
  counts: { ok: 2, needs_choice: 1, error: 0, add: 1, update: 1, unchanged: 0, remove: 1 },
  warnings: ['The drawing\'s catalog is 40 days old'],
  blocking: [],
  new_version_required: true,
};

function respond(call, message) {
  call.callback({ message });
  if (call.always) call.always();
}

function page(context = CONTEXT) {
  const json = JSON.stringify(context).replace(/</g, '\\u003c');
  const dom = new JSDOM(
    `<body><div id="importDrawingModal">
      <input type="file" id="importDrawingFile"><a href="#" id="importDrawingReceipt"></a>
      <div id="importDrawingWarnings" hidden></div><p id="importDrawingCounts"></p>
      <div id="importDrawingPreview" hidden><table><tbody id="importDrawingRows"></tbody></table></div>
      <div id="importDrawingRemoveWrap" hidden><input type="checkbox" id="importDrawingRemove"><label id="importDrawingRemoveLabel"></label></div>
      <div id="importDrawingVersionWrap" hidden><input type="checkbox" id="importDrawingVersion"></div>
      <div id="importDrawingError" hidden></div>
      <button type="button" id="importDrawingRefresh" hidden></button>
      <button type="button" id="importDrawingConfirm" disabled></button></div>
    <script type="application/json" id="schedule-context">${json}</script></body>`,
    { runScripts: 'outside-only', url: 'https://portal.test/portal/schedules/S-1' },
  );
  const w = dom.window;
  const requests = [];
  w.$ = w.jQuery = jquery(w);
  w.__ = text => text;
  w.frappe = { call: args => requests.push(args) };
  w.eval(read('context') + '\nvar schedule_name = scheduleContext.schedule_name;\n' + read('drawing_import'));
  const events = { done: [], saved: [] };
  w.DrawingImport.done = message => events.done.push(message);
  w.DrawingImport.save = (blob, name) => events.saved.push({ blob, name });
  return { w, $: w.$, requests, events };
}

async function chosen(w, requests, name = 'job.ilq.json', text = '{"schema":"ilq/2"}') {
  w.DrawingImport.choose(new w.File([text], name, { type: 'application/json' }));
  for (let i = 0; i < 50 && !requests.length; i += 1) await new Promise(resolve => setTimeout(resolve, 5));
  return requests.shift();
}

test('the template gates the drawing import and loads drawing_import.js', () => {
  assert.match(TEMPLATE, /\{% if drawing_import_enabled \| default\(false\) %\}\s*<button class="btn btn-outline-primary" type="button" id="importDrawingButton"/);
  assert.match(TEMPLATE, /\{% if drawing_import_enabled \| default\(false\) %\}\s*<div class="modal fade" id="importDrawingModal"/);
  assert.match(TEMPLATE, /"drawing_import": \(drawing_import_enabled \| default\(false\)\)/);
  assert.match(TEMPLATE, /"exports", "drawing_import", "reorder"[\],]/);
});

test('a package is previewed with runs, choices, removals and warnings as text only', async () => {
  const { w, $, requests } = page();
  const call = await chosen(w, requests);
  assert.equal(call.method, 'illumenate_lighting.illumenate_lighting.portal.drawing_import.preview_drawing_import');
  assert.equal(call.args.schedule, 'S-1');
  assert.equal(call.args.filename, 'job.ilq.json');
  respond(call, PREVIEW);
  assert.equal($('#importDrawingRows tr').length, 4);
  assert.equal($('#importDrawingRows img').length, 0);
  assert.match($('#importDrawingRows tr').first().text(), /<img src=x/);
  assert.equal($('#importDrawingRows input[data-choice-key="finish"]').length, 1);
  assert.equal($('#importDrawingWarnings').prop('hidden'), false);
  assert.equal($('#importDrawingRemoveWrap').prop('hidden'), false);
  assert.equal($('#importDrawingVersionWrap').prop('hidden'), false);
  assert.equal($('#importDrawingRefresh').prop('hidden'), false);
  assert.equal($('#importDrawingConfirm').prop('disabled'), true);
});

test('choices are sent with the next preview and the import needs every confirmation', async () => {
  const { w, $, requests, events } = page();
  respond(await chosen(w, requests), PREVIEW);
  $('#importDrawingRows input[data-choice-key="finish"]').val('White');
  $('#importDrawingRefresh').trigger('click');
  const again = requests.shift();
  assert.deepEqual(JSON.parse(again.args.choices), { 'L3-01': { finish: 'White' } });
  const ready = { ...PREVIEW, rows: [PREVIEW.rows[0]], counts: { ...PREVIEW.counts, needs_choice: 0 } };
  respond(again, ready);
  assert.equal($('#importDrawingConfirm').prop('disabled'), true);
  $('#importDrawingRemove').prop('checked', true).trigger('change');
  assert.equal($('#importDrawingConfirm').prop('disabled'), true);
  $('#importDrawingVersion').prop('checked', true).trigger('change');
  assert.equal($('#importDrawingConfirm').prop('disabled'), false);
  $('#importDrawingConfirm').trigger('click');
  const commit = requests.shift();
  assert.equal(commit.method, 'illumenate_lighting.illumenate_lighting.portal.drawing_import.commit_drawing_import');
  assert.equal(commit.args.expected_modified, 'rev-1');
  assert.equal(commit.args.confirm_removals, 1);
  assert.equal(commit.args.new_version, 1);
  respond(commit, { success: true, schedule: 'S-1-v2', receipt: { import: 'CADI-00001', runs: [] } });
  assert.equal(events.saved[0].name, 'illumenate_receipt_CADI-00001.json');
  assert.equal(events.done[0].schedule, 'S-1-v2');
});

test('errors block the import and server refusals are shown', async () => {
  const { w, $, requests } = page();
  respond(await chosen(w, requests), { ...PREVIEW, counts: { ...PREVIEW.counts, error: 1, needs_choice: 0 }, removals: [], new_version_required: false });
  assert.equal($('#importDrawingConfirm').prop('disabled'), true);
  const second = page();
  respond(await chosen(second.w, second.requests), { ...PREVIEW, rows: [PREVIEW.rows[0]], removals: [], new_version_required: false, counts: { ...PREVIEW.counts, needs_choice: 0 } });
  second.$('#importDrawingConfirm').trigger('click');
  const commit = second.requests.shift();
  respond(commit, { success: false, error: 'The schedule changed' });
  assert.equal(second.$('#importDrawingError').text(), 'The schedule changed');
});

test('only package files under 5 MB are read', async () => {
  const { w, $, requests } = page();
  w.DrawingImport.choose(new w.File(['x'], 'job.dwg'));
  assert.match($('#importDrawingError').text(), /ILQUOTE/);
  const big = new w.File(['x'], 'job.json');
  Object.defineProperty(big, 'size', { value: 6 * 1024 * 1024 });
  w.DrawingImport.choose(big);
  assert.match($('#importDrawingError').text(), /5 MB/);
  assert.equal(requests.length, 0);
});

test('the last receipt can be downloaded again', () => {
  const { $, requests, events } = page();
  $('#importDrawingReceipt').trigger('click');
  const call = requests.shift();
  assert.equal(call.method, 'illumenate_lighting.illumenate_lighting.portal.drawing_import.get_drawing_receipt');
  respond(call, { success: true, receipt: { import: 'CADI-00002' } });
  assert.equal(events.saved[0].name, 'illumenate_receipt_CADI-00002.json');
});
