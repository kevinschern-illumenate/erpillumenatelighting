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

function page(context = CONTEXT, opts = {}) {
  const json = JSON.stringify(context).replace(/</g, '\\u003c');
  const dom = new JSDOM(
    `<body><div id="importDrawingModal">
      <input type="file" id="importDrawingFile"><input type="file" id="importDrawingPlan"><a href="#" id="importDrawingReceipt"></a>
      <div id="importDrawingWarnings" hidden></div><p id="importDrawingCounts"></p>
      <div id="importDrawingPreview" hidden><table><tbody id="importDrawingRows"></tbody></table></div>
      <div id="importDrawingRemoveWrap" hidden><input type="checkbox" id="importDrawingRemove"><label id="importDrawingRemoveLabel"></label></div>
      <div id="importDrawingVersionWrap" hidden><input type="checkbox" id="importDrawingVersion"></div>
      <div id="importDrawingError" hidden></div>
      <p id="importDrawingSource" hidden></p>
      <div id="importDrawingSheets" hidden><table><tbody id="importDrawingSheetRows"></tbody></table></div>
      <div id="importDrawingLayers" hidden><table><tbody id="importDrawingLayerRows"></tbody></table></div>
      <div id="importDrawingGroups" hidden><div id="importDrawingGroupList"></div></div>
      <details id="importDrawingHistory" hidden><table><tbody id="importDrawingHistoryRows"></tbody></table></details>
      <div id="importDrawingDone" hidden><p id="importDrawingDoneText"></p><ul id="importDrawingBlockers" hidden></ul>
        <button type="button" id="importDrawingQuote"></button><button type="button" id="importDrawingFinish"></button></div>
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
  if (!opts.keepDone) w.DrawingImport.done = message => events.done.push(message);
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

test('a plotted plan PDF travels with the import', async () => {
  const { w, $, requests } = page();
  w.DrawingImport.choosePlan(new w.File(['%PDF-1.7'], 'plan.pdf', { type: 'application/pdf' }));
  await new Promise(resolve => setTimeout(resolve, 20));
  respond(await chosen(w, requests), { ...PREVIEW, rows: [PREVIEW.rows[0]], removals: [], new_version_required: false, counts: { ...PREVIEW.counts, needs_choice: 0 } });
  $('#importDrawingConfirm').trigger('click');
  const commit = requests.shift();
  assert.equal(Buffer.from(commit.args.plan_pdf, 'base64').toString(), '%PDF-1.7');
  w.DrawingImport.choosePlan(new w.File(['x'], 'plan.dwg'));
  assert.match($('#importDrawingError').text(), /PDF/);
});

// Implementation plan WP 1.3, 1.8, 1.10, 1.11.

const GROUPED = {
  ...PREVIEW,
  rows: [
    { id: 'L3-01', fixture_type: 'L3', style: 'non-pnc-sw', status: 'needs_choice', messages: [], parts: [{ part: 'build', missing: ['finish'] }] },
    { id: 'L3-02', fixture_type: 'L3', style: 'non-pnc-sw', status: 'needs_choice', messages: [], parts: [{ part: 'build', missing: ['finish'] }] },
  ],
  removals: [],
  new_version_required: false,
  counts: { ok: 0, needs_choice: 2, error: 0, add: 0, update: 0, unchanged: 0, remove: 0 },
  choice_groups: [{ family: 'LED Neon', template: 'non-pnc-sw', style: 'non-pnc-sw', keys: [{ key: 'finish', values: ['White', '<b>Black</b>'] }], runs: ['L3-01', 'L3-02'] }],
  previous_choices: { 'L3-02': { finish: 'White' } },
  source: { tool: 'autocad', version: '0.5.0' },
  sheets: [{ id: 'L1', label: 'Level 1', status: 'verified', used: true }, { id: 'L2', label: '<i>Level 2</i>', status: 'unverified', used: true }],
};

test('one group answer fills every run waiting on it; a run answer wins; remembered answers prefill', async () => {
  const { w, $, requests } = page();
  respond(await chosen(w, requests), GROUPED);
  assert.equal($('#importDrawingGroups').prop('hidden'), false);
  const select = $('#importDrawingGroupList select[data-group-key="finish"]');
  assert.equal(select.find('option').length, 3);
  assert.equal($('#importDrawingGroupList b').length, 0);
  assert.equal($('#importDrawingRows input[data-choice-run="L3-02"]').val(), 'White');
  $('#importDrawingRows input[data-choice-run="L3-02"]').val('');
  select.val('White');
  assert.deepEqual(JSON.parse(JSON.stringify(w.DrawingImport.choices())), { 'L3-01': { finish: 'White' }, 'L3-02': { finish: 'White' } });
  $('#importDrawingRows input[data-choice-run="L3-01"]').val('Black');
  assert.equal(w.DrawingImport.choices()['L3-01'].finish, 'Black');
});

test('sheets show their scale as text and the source tool is named', async () => {
  const { w, $, requests } = page();
  respond(await chosen(w, requests), GROUPED);
  assert.equal($('#importDrawingSheets').prop('hidden'), false);
  assert.equal($('#importDrawingSheetRows tr').length, 2);
  assert.equal($('#importDrawingSheetRows i').length, 0);
  assert.equal($('#importDrawingSheetRows tr[data-scale-status="unverified"]').length, 1);
  assert.match($('#importDrawingSource').text(), /autocad 0\.5\.0/);
});

test('DXF layers get a style and a Type that travel as options', async () => {
  const { w, $, requests } = page();
  const call = await chosen(w, requests, 'job.dxf', '0\nSECTION');
  respond(call, { ...PREVIEW, rows: [PREVIEW.rows[0]], removals: [], new_version_required: false, counts: { ...PREVIEW.counts, needs_choice: 0 },
    layers: [{ layer: 'ILM-LINEAR-RA01', runs: 3, family: 'Linear Fixture', template: 'RA01', needs_preset: true, fixture_type: 'D1' }] });
  const presets = requests.shift();
  assert.equal(presets.method, 'illumenate_lighting.illumenate_lighting.portal.presets.list_presets');
  respond(presets, { success: true, presets: [{ name: 'PRE-1', label: 'RA01 Black', cad_code: 'RA01-BK', available: true }, { name: 'PRE-2', label: 'Gone', available: false }] });
  assert.equal($('#importDrawingLayers').prop('hidden'), false);
  const select = $('#importDrawingLayerRows select[data-layer-preset="ILM-LINEAR-RA01"]');
  assert.equal(select.find('option').length, 2);
  select.val('PRE-1');
  $('#importDrawingLayerRows input[data-layer-type="ILM-LINEAR-RA01"]').val('L4');
  $('#importDrawingRefresh').trigger('click');
  const again = requests.shift();
  assert.deepEqual(JSON.parse(again.args.options), { presets: { 'ILM-LINEAR-RA01': 'PRE-1' }, types: { 'ILM-LINEAR-RA01': 'L4' } });
});

test('after an import the quote request is offered unless a blocker says why not', async () => {
  const { w, $, requests, events } = page(CONTEXT, { keepDone: true });
  respond(await chosen(w, requests), { ...PREVIEW, rows: [PREVIEW.rows[0]], removals: [], new_version_required: false, counts: { ...PREVIEW.counts, needs_choice: 0 } });
  $('#importDrawingConfirm').trigger('click');
  respond(requests.shift(), { success: true, schedule: 'S-1', import: 'CADI-00003', modified: 'rev-2', receipt: { import: 'CADI-00003' } });
  assert.equal(events.saved.length, 1);
  assert.equal($('#importDrawingDone').prop('hidden'), false);
  const blockers = requests.shift();
  assert.equal(blockers.method, 'illumenate_lighting.illumenate_lighting.portal.drawing_import.get_quote_blockers');
  respond(blockers, { success: true, blockers: ['<b>Scale</b> not verified'] });
  assert.equal($('#importDrawingQuote').prop('disabled'), true);
  assert.equal($('#importDrawingBlockers li').text(), '<b>Scale</b> not verified');
  w.PortalCommercial = { quote: (schedule, modified) => events.done.push({ schedule, modified }) };
  respond({ callback: requests.length ? requests.shift().callback : () => {} }, {});
  const second = page(CONTEXT, { keepDone: true });
  second.w.PortalCommercial = { quote: (schedule, modified) => second.events.done.push({ schedule, modified }) };
  second.w.DrawingImport.done({ success: true, schedule: 'S-1', import: 'CADI-00004', modified: 'rev-3' });
  respond(second.requests.shift(), { success: true, blockers: [] });
  assert.equal(second.$('#importDrawingQuote').prop('disabled'), false);
  second.$('#importDrawingQuote').trigger('click');
  assert.deepEqual(JSON.parse(JSON.stringify(second.events.done)), [{ schedule: 'S-1', modified: 'rev-3' }]);
});

test('previous imports are listed with their tool and scale', () => {
  const { w, $, requests } = page();
  w.DrawingImport.history();
  const call = requests.shift();
  assert.equal(call.method, 'illumenate_lighting.illumenate_lighting.portal.drawing_import.list_drawing_imports');
  respond(call, { success: true, imports: [{ name: 'CADI-00001', status: 'Committed', drawing_file: '<s>job</s>.dwg', drawing_rev: 2, source_tool: 'dxf', source_version: 'dxf-1', scale_status: 'unverified', scale_confirmed_by: 'ae@x', runs_added: 4 }] });
  assert.equal($('#importDrawingHistory').prop('hidden'), false);
  assert.equal($('#importDrawingHistoryRows s').length, 0);
  assert.match($('#importDrawingHistoryRows').text(), /dxf dxf-1/);
  assert.match($('#importDrawingHistoryRows').text(), /confirmed/);
});

test('a multi-run group is one row followed by its runs, and its open choice is keyed by the group', async () => {
  const { w, $, requests } = page();
  const group = {
    id: 'G-01', kind: 'group', fixture_type: 'T1', style: 'led-hd-sw', drawn_length_in: 384, server_length_in: 380,
    action: 'add', status: 'needs_choice', messages: ['Choose finish for this group'], parts: [{ part: 'group', missing: ['finish'] }],
    members: [
      { label: 'Shelf 1', run: 'T1-01', drawn_length_in: 96, server_length_in: 95, watts: 10.5, circuits: 1 },
      { label: '<b>Shelf 2</b>', run: 'T1-01', drawn_length_in: 96, server_length_in: 95, watts: 10.5, circuits: 1 },
    ],
  };
  respond(await chosen(w, requests), { ...PREVIEW, rows: [group], other_lines: [], removals: [], counts: { ...PREVIEW.counts, ok: 0, needs_choice: 1 } });
  assert.equal($('#importDrawingRows tr[data-drawing-kind="group"]').length, 1);
  const members = $('#importDrawingRows tr[data-drawing-member="G-01"]');
  assert.equal(members.length, 2);
  assert.match(members.first().text(), /Shelf 1/);
  assert.match(members.first().text(), /Drawn as T1-01/);
  assert.match(members.first().text(), /10.5 W on 1 circuit\(s\)/);
  assert.equal($('#importDrawingRows b').length, 0);
  $('#importDrawingRows input[data-choice-key="finish"]').val('White');
  $('#importDrawingRefresh').trigger('click');
  assert.deepEqual(JSON.parse(requests.shift().args.choices), { 'G-01': { finish: 'White' } });
});
