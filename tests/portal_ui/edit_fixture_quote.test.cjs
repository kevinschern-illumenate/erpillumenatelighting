// Edit fixture page: calculating writes no configured fixture; Update Fixture writes the one it saves.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const jquery = require('jquery');

const SCRIPT = fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/public/js/portal/edit_fixture/page.js'), 'utf8');
const ENGINE = 'illumenate_lighting.illumenate_lighting.api.configurator_engine.';
const UPDATE = 'illumenate_lighting.illumenate_lighting.api.portal.update_configured_fixture_on_schedule';

function setup() {
  const context = { schedule_name: 'SCH-1', line_idx: 2, configured_fixture_id: 'CF-OLD', fixture_config: null };
  const dom = new JSDOM(
    '<body><script type="application/json" id="edit-fixture-context">' + JSON.stringify(context) + '</script>'
    + '<span id="validationStatus" class="badge"></span><div id="partNumberPanel" style="display:none"><span id="partNumberValue"></span><span id="partDescriptionValue"></span></div>'
    + '<button id="saveBtn" disabled>Update Fixture</button></body>',
    { runScripts: 'outside-only', url: 'https://portal.test/portal/schedules/SCH-1/lines/L1/edit' },
  );
  const w = dom.window;
  const requests = [];
  const messages = [];
  w.$ = w.jQuery = jquery(w);
  w.__ = value => value;
  w.console = { log() {}, warn() {}, error() {} };
  w.PortalUI = { escape: value => String(value).replace(/</g, '&lt;') };
  w.frappe = { call: args => requests.push(args), msgprint: value => messages.push(value), show_alert() {} };
  w.eval(SCRIPT);
  requests.length = 0;
  return { dom, w, requests, messages };
}

const DATA = { fixture_template_code: 'FT-1', segments_json: '[]', delivered_output_value: 300 };
const COMPUTED = {
  total_requested_length_mm: 1200, total_requested_length_in: 47.24, manufacturable_overall_length_mm: 1200, manufacturable_overall_length_in: 47.24,
  user_segment_count: 1, segments_count: 1, runs_count: 1, total_endcaps: 2, total_mounting_accessories: 4, total_watts: 12,
  assembly_mode: 'ASSEMBLED', build_description: 'FT-1 4ft', runs: [],
};
const RESULT = { is_valid: true, configured_fixture_id: null, candidate_part_number: 'ILL-FT1-300', computed: COMPUTED, pricing: { msrp_unit: 100, tier_unit: 80, item_pricing: [] }, messages: [] };

test('calculating asks the engine not to create a configured fixture and shows the candidate part number', () => {
  const { dom, w, requests } = setup();
  w.requestQuote(ENGINE + 'validate_and_quote_multisegment_with_output', DATA);
  const quote = requests.shift();
  assert.equal(quote.method, ENGINE + 'validate_and_quote_multisegment_with_output');
  assert.ok(quote.args._skip_record_creation, 'preview only');
  assert.equal(DATA._skip_record_creation, undefined, 'the caller data is not changed');
  quote.callback({ message: RESULT });
  assert.equal(w.$('#partNumberValue').text(), 'ILL-FT1-300');
  assert.equal(w.$('#saveBtn').prop('disabled'), false);
  dom.window.close();
});

test('Update Fixture creates the record from the same inputs, then saves that record to the line', () => {
  const { dom, w, requests } = setup();
  w.requestQuote(ENGINE + 'validate_and_quote_multisegment_with_output', DATA);
  requests.shift().callback({ message: RESULT });
  w.updateFixture();
  const persist = requests.shift();
  assert.equal(persist.method, ENGINE + 'validate_and_quote_multisegment_with_output');
  assert.deepEqual({ ...persist.args }, DATA, 'same inputs, record creation on');
  assert.equal(w.$('#saveBtn').prop('disabled'), true, 'no double submit while saving');
  persist.callback({ message: { ...RESULT, configured_fixture_id: 'CF-NEW', computed: { ...COMPUTED, manufacturable_overall_length_mm: 1210 } } });
  const save = requests.shift();
  assert.equal(save.method, UPDATE);
  assert.deepEqual({ ...save.args }, { schedule_name: 'SCH-1', line_idx: 2, new_configured_fixture_id: 'CF-NEW', manufacturable_length_mm: 1210 });
  assert.equal(requests.length, 0);
  dom.window.close();
});

test('a save whose record cannot be created never touches the schedule line and re-enables the button', () => {
  for (const message of [{ ...RESULT, is_valid: false, messages: [{ text: '<b>Too long</b>' }] }, { ...RESULT, configured_fixture_id: null }, null]) {
    const { dom, w, requests, messages } = setup();
    w.requestQuote(ENGINE + 'validate_and_quote_multisegment', DATA);
    requests.shift().callback({ message: RESULT });
    w.updateFixture();
    requests.shift().callback({ message });
    assert.equal(requests.length, 0, 'update_configured_fixture_on_schedule is not called');
    assert.equal(messages.length, 1);
    assert.doesNotMatch(messages[0], /<b>/, 'server text is escaped');
    assert.equal(w.$('#saveBtn').prop('disabled'), false);
    dom.window.close();
  }
});

test('Update Fixture does nothing before a valid calculation', () => {
  const { dom, w, requests, messages } = setup();
  w.updateFixture();
  assert.equal(requests.length, 0);
  assert.equal(messages.length, 1);
  dom.window.close();
});
