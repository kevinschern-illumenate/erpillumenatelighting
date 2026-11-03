// Plan 3.4: importing schedule lines from a CSV/Excel sheet.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const jquery = require('jquery');
const { TEMPLATE, read } = require('./schedule_source.cjs');

const CONTEXT = {
  schedule_name: 'S-1',
  schedule_modified: 'rev-1',
  schedule_import: true,
  import_columns: ['Type', 'Qty', 'Location', 'Description', 'Part Number', 'Notes', 'Length (in)'],
  lines: [],
  i18n: {},
};

const PREVIEW = {
  success: true,
  columns: ['Type', 'Qty', '<b>Where</b>', ''],
  fields: [{ field: 'line_id', label: 'Type' }, { field: 'qty', label: 'Qty' }, { field: 'location', label: 'Location' }],
  mapping: { line_id: 0, qty: 1 },
  rows: [
    { row: 2, status: 'needs_configuration', line_id: '<img src=x onerror=alert(1)>', qty: 2, location: 'Lobby', summary: 'Shallow <01>', messages: ['Matched'] },
    { row: 3, status: 'ok', line_id: 'B', qty: 1, location: '', summary: 'Acme', messages: [] },
    { row: 4, status: 'error', line_id: 'C', qty: 'two', location: '', messages: ['Quantity must be a whole number of at least 1'] },
  ],
  counts: { ok: 1, needs_configuration: 1, error: 1 },
};

function respond(call, message) {
  call.callback({ message });
  if (call.always) call.always();
}

function page(context = CONTEXT) {
  const json = JSON.stringify(context).replace(/</g, '\\u003c');
  const dom = new JSDOM(
    `<body><div id="importLinesModal">
      <input type="file" id="importLinesFile"><a href="#" id="importLinesTemplate"></a>
      <div id="importLinesMapping" hidden><div id="importLinesMappingFields"></div><button type="button" id="importLinesRefresh"></button></div>
      <p id="importLinesCounts"></p>
      <div id="importLinesPreview" hidden><table><tbody id="importLinesRows"></tbody></table></div>
      <div id="importLinesSkipWrap" hidden><input type="checkbox" id="importLinesSkip"></div>
      <div id="importLinesError" hidden></div>
      <button type="button" id="importLinesConfirm" disabled></button></div>
    <script type="application/json" id="schedule-context">${json}</script></body>`,
    { runScripts: 'outside-only', url: 'https://portal.test/portal/schedules/S-1' },
  );
  const w = dom.window;
  const requests = [];
  w.$ = w.jQuery = jquery(w);
  w.__ = text => text;
  w.frappe = { call: args => requests.push(args) };
  w.eval(read('context') + '\nvar schedule_name = scheduleContext.schedule_name;\n' + read('line_import'));
  const events = { reloads: 0, saved: [] };
  w.ScheduleImport.reload = () => { events.reloads += 1; };
  w.ScheduleImport.save = (blob, name) => events.saved.push({ blob, name });
  return { dom, w, $: w.$, requests, events };
}

function file(w, name, text, size) {
  const value = new w.File([text], name, { type: 'text/csv' });
  if (size) Object.defineProperty(value, 'size', { value: size });
  return value;
}

async function chosen(w, requests, name = 'lines.csv', text = 'Type,Qty\nA,1\n') {
  w.ScheduleImport.choose(file(w, name, text));
  for (let i = 0; i < 50 && !requests.length; i += 1) await new Promise(resolve => setTimeout(resolve, 5));
  return requests.shift();
}

test('the template gates the import and loads line_import.js', () => {
  assert.match(TEMPLATE, /\{% if schedule_import_enabled \| default\(false\) %\}\s*<button class="btn btn-outline-primary" type="button" id="importLinesButton"/);
  assert.match(TEMPLATE, /\{% if schedule_import_enabled \| default\(false\) %\}\s*<div class="modal fade" id="importLinesModal"/);
  assert.match(TEMPLATE, /"schedule_import": \(schedule_import_enabled \| default\(false\)\)/);
  assert.match(TEMPLATE, /"part_number", "line_import"\] %\}/);
});

test('a sheet is previewed with its mapping and rows as text only', async () => {
  const { dom, w, $, requests } = page();
  const call = await chosen(w, requests);
  assert.match(call.method, /schedule_import\.preview_schedule_import$/);
  assert.equal(call.type, 'POST');
  assert.deepEqual({ ...call.args }, {
    schedule: 'S-1', filename: 'lines.csv', content: Buffer.from('Type,Qty\nA,1\n').toString('base64'), mapping: '',
  });
  respond(call, PREVIEW);
  assert.equal($('#importLinesMapping').prop('hidden'), false);
  assert.equal($('#importLinesField-line_id').val(), '0');
  assert.equal($('#importLinesField-location').val(), '');
  assert.deepEqual([...$('#importLinesField-location option').map((_, o) => o.textContent).get()], ['Not imported', 'Type', 'Qty', '<b>Where</b>', 'Column 4']);
  assert.equal($('#importLinesMappingFields b').length, 0);
  assert.equal($('#importLinesRows tr').length, 3);
  assert.equal($('#importLinesRows img').length, 0);
  assert.equal($('#importLinesRows tr').eq(0).find('td').eq(1).text(), '<img src=x onerror=alert(1)>');
  assert.equal($('#importLinesRows tr').eq(0).find('.badge').text(), 'Needs configuration');
  assert.equal($('#importLinesRows tr').eq(0).find('td').eq(5).text(), 'Shallow <01> · Matched');
  assert.equal($('#importLinesCounts').text(), '1 ready, 1 need configuration, 1 with errors.');
  assert.equal($('#importLinesSkipWrap').prop('hidden'), false);
  assert.equal($('#importLinesConfirm').prop('disabled'), true, 'errors block the import until skipped');

  $('#importLinesField-location').val('2');
  $('#importLinesRefresh').trigger('click');
  const again = requests.shift();
  assert.deepEqual(JSON.parse(again.args.mapping), { line_id: 0, qty: 1, location: 2 });
  dom.window.close();
});

test('skipping errors enables the import, which re-sends the sheet and reloads', async () => {
  const { dom, w, $, requests, events } = page();
  respond(await chosen(w, requests), PREVIEW);
  $('#importLinesSkip').prop('checked', true).trigger('change');
  assert.equal($('#importLinesConfirm').prop('disabled'), false);
  assert.equal($('#importLinesConfirm').text(), 'Import 2 line(s)');
  $('#importLinesConfirm').trigger('click');
  const call = requests.shift();
  assert.match(call.method, /commit_schedule_import$/);
  assert.equal(call.args.expected_modified, 'rev-1');
  assert.equal(call.args.skip_errors, 1);
  assert.deepEqual(JSON.parse(call.args.mapping), { line_id: 0, qty: 1 });
  assert.equal(call.args.content, Buffer.from('Type,Qty\nA,1\n').toString('base64'));
  respond(call, { success: false, error: 'Row 3: <b>Gone</b>', rows: [{ row: 3, status: 'error', line_id: 'B', messages: ['<b>Gone</b>'] }] });
  assert.equal($('#importLinesError').text(), 'Row 3: <b>Gone</b>');
  assert.equal($('#importLinesError b').length, 0);
  assert.equal(events.reloads, 0);
  $('#importLinesConfirm').trigger('click');
  respond(requests.shift(), { success: true, count: 2 });
  assert.equal(events.reloads, 1);
  dom.window.close();
});

test('wrong or oversized files are refused before upload, and failures are shown', async () => {
  const { dom, w, $, requests } = page();
  w.ScheduleImport.choose(file(w, 'lines.pdf', 'x'));
  assert.equal($('#importLinesError').text(), 'Upload a .csv or .xlsx file.');
  w.ScheduleImport.choose(file(w, 'lines.xlsx', 'x', 2 * 1024 * 1024));
  assert.equal($('#importLinesError').text(), 'The file is larger than 1 MB.');
  assert.equal(requests.length, 0);
  respond(await chosen(w, requests, 'lines.XLSX', 'PK'), { success: false, error: 'The Excel file could not be read' });
  assert.equal($('#importLinesError').text(), 'The Excel file could not be read');
  assert.equal($('#importLinesConfirm').prop('disabled'), true);
  dom.window.close();
});

test('the template download is the import header', async () => {
  const { dom, w, $, events } = page();
  $('#importLinesTemplate').trigger('click');
  assert.equal(events.saved[0].name, 'schedule-import-template.csv');
  const text = await new Promise(resolve => {
    const reader = new w.FileReader();
    reader.onload = () => resolve(reader.result);
    reader.readAsText(events.saved[0].blob);
  });
  assert.equal(text, '"Type","Qty","Location","Description","Part Number","Notes","Length (in)"\r\n');
  dom.window.close();
});

test('the kill switch leaves the page alone', () => {
  const { dom, $, events } = page({ ...CONTEXT, schedule_import: false });
  $('#importLinesTemplate').trigger('click');
  assert.equal(events.saved.length, 0);
  dom.window.close();
});
