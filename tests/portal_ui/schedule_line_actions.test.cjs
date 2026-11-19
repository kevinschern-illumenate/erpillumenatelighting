// Health item 6: a double click on Duplicate, Delete's confirm or the edit Save sent the same change
// twice, and the second write failed with Frappe's raw "has been modified" error. One request at a time.
const { test, afterEach } = require('node:test');
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const jquery = require('jquery');
const { read } = require('./schedule_source.cjs');

const opened = [];
afterEach(() => { while (opened.length) opened.pop().window.close(); });

function page() {
  const json = JSON.stringify({ schedule_name: 'S-1', schedule_modified: '2026-11-18 09:00:00', lines: [{ line_id: 'A1', manufacturer_type: 'ILLUMENATE' }], i18n: {} });
  const dom = new JSDOM(
    `<body><table><tr data-line-idx="0" data-line-key="k-1"></tr></table>
    <input id="edit_line_idx" value="0"><input id="edit_line_id" value="A1"><input id="edit_qty" value="2">
    <input id="edit_location" value=""><input id="edit_notes" value="">
    <script type="application/json" id="schedule-context">${json}</script></body>`,
    { runScripts: 'outside-only', url: 'https://portal.test/portal/schedules/S-1' },
  );
  opened.push(dom);
  const w = dom.window;
  w.$ = w.jQuery = jquery(w);
  w.$.fn.popover = w.$.fn.modal = function () { return this; };
  const requests = [];
  const confirms = [];
  const messages = [];
  w.frappe = {
    call: args => requests.push(args),
    confirm: (text, yes) => confirms.push(yes),
    msgprint: text => messages.push(text),
  };
  w.__ = text => text;
  w.eval(read('context') + '\n' + read('lines'));
  return { w, requests, confirms, messages };
}

test('a double click on Duplicate sends one frozen request; a failure frees the next click', () => {
  const { w, requests, messages } = page();
  w.duplicateLine(0);
  w.duplicateLine(0);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].method, 'illumenate_lighting.illumenate_lighting.api.portal.duplicate_schedule_line');
  assert.equal(requests[0].freeze, true);
  assert.equal(requests[0].args.line_key, 'k-1');
  requests[0].callback({ message: { success: false, error: 'Nope' } });
  requests[0].always();
  assert.deepEqual(messages, ['Nope']);
  w.duplicateLine(0);
  assert.equal(requests.length, 2);
});

test('a double click on the delete confirmation sends one request', () => {
  const { w, requests, confirms } = page();
  w.deleteLine(0);
  assert.equal(confirms.length, 1);
  confirms[0]();
  confirms[0]();
  assert.equal(requests.length, 1);
  assert.equal(requests[0].method, 'illumenate_lighting.illumenate_lighting.api.portal.delete_schedule_line');
  assert.equal(requests[0].freeze, true);
  w.deleteLine(0);
  assert.equal(confirms.length, 1, 'no second confirmation while the delete is in flight');
  requests[0].always();
  w.deleteLine(0);
  assert.equal(confirms.length, 2);
});

test('a double click on the edit Save sends one request, and any line action waits for it', () => {
  const { w, requests } = page();
  w.saveEditLine();
  w.saveEditLine();
  w.duplicateLine(0);
  assert.equal(requests.length, 1);
  assert.equal(requests[0].method, 'illumenate_lighting.illumenate_lighting.api.portal.update_schedule_line');
  assert.equal(requests[0].freeze, true);
  assert.equal(requests[0].args.line_data.qty, '2');
  requests[0].always();
  w.saveEditLine();
  assert.equal(requests.length, 2);
});
