// DOM/service-boundary tests. These do not substitute for Frappe browser journeys.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const jquery = require('jquery');

function setup(html = '') {
  const dom = new JSDOM('<body>' + html + '</body>', { runScripts: 'outside-only', url: 'https://portal.test/' });
  const w = dom.window;
  const requests = [];
  w.$ = w.jQuery = jquery(w);
  w.__ = (value, args) => args ? value.replace(/\{(\d+)\}/g, (_, i) => args[i]) : value;
  w.frappe = { call: args => requests.push(args), msgprint() {}, show_alert() {} };
  for (const file of ['shared_configurator', 'fixture_group_editor', 'fixture_steps', 'tape_neon_steps', 'led_sheet_steps', 'coordinator']) {
    w.eval(fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/public/js/configurator', file + '.js'), 'utf8'));
  }
  return { dom, w, $: w.$, requests, api: w.IllConfigurator };
}

test('fixture availability distinguishes unknown setup from known stock and shortages', () => {
  const { dom, $, api } = setup('<div id="host"><div id="stockAvailability"><div id="stockItemsList"></div></div></div>');
  const inst = new api.Fixture($('#host'), {});
  inst._renderStockAvailability({ all_in_stock: true, items: [{ item_code: 'PROFILE', is_sufficient: true }] });
  assert.match(inst.$('#stockItemsList').text(), /All In Stock/);
  inst._renderStockAvailability({ availability: 'unknown', all_in_stock: false, items: [] });
  assert.equal(inst.$('#stockItemsList').text(), 'Stock availability unavailable');
  assert.notEqual(inst.$('#stockAvailability').css('display'), 'none');
  assert.equal(inst.$('#stockItemsList .text-danger').length, 0);
  inst._renderStockAvailability({ all_in_stock: false, items: [{ item_code: 'PROFILE', is_sufficient: false }] });
  assert.match(inst.$('#stockItemsList').text(), /Not In Stock/);
  assert.doesNotMatch(inst.$('#stockItemsList').text(), /unavailable/);
  dom.window.close();
});

test('embedded labels target only their instance and remount has one change handler', () => {
  const { dom, $, api } = setup(['a', 'b'].map(id => '<div id="' + id + '"><input id="power" type="checkbox"><label for="power">Power</label></div>').join(''));
  const a = new api.Base($('#a'), {});
  const b = new api.Base($('#b'), {});
  assert.notEqual(a.$('#power').attr('id'), b.$('#power').attr('id'));
  $('#b label')[0].click();
  assert.equal(b.$('#power').prop('checked'), true);
  assert.equal(a.$('#power').prop('checked'), false);
  a.destroy();
  const remount = new api.Base($('#a'), {});
  const before = remount._revision;
  remount.$('#power').trigger('change');
  assert.equal(remount._revision, before + 1);
  assert.equal($('#a label').attr('for'), remount.$('#power').attr('id'));
  dom.window.close();
});

test('each family rejects results after editing, a newer request, and teardown', () => {
  for (const family of ['Fixture', 'LedSheet', 'TapeNeon']) {
    const { dom, $, api, requests } = setup('<div id="host"><input id="dimension" value="10"><button id="validateBtn" data-action="validate">Calculate</button><button id="calculateSheet" data-action="validate">Calculate</button></div>');
    const inst = new api[family]($('#host'), { is_neon: false });
    inst._updateButtons = () => {};
    inst._displayResults = () => {};
    inst._showResults = () => {};
    inst._gatherAllSelections = () => ({ segments: [{ end_type: 'Endcap', requested_length_mm: 1000 }], delivered_output_value: 100, override_max_run_ft: '', include_power_supply: true });
    const calculate = () => family === 'TapeNeon' ? inst.doCalculate() : inst.validateConfiguration();
    const result = () => inst.currentResult || inst.lastResult;
    const response = { message: { success: true, is_valid: true } };
    calculate();
    const old = requests.at(-1);
    inst.$('#dimension').val('20').trigger('input');
    old.callback(response);
    assert.equal(result(), null, family + ': stale edit response');
    calculate();
    const first = requests.at(-1);
    calculate();
    const latest = requests.at(-1);
    latest.callback(response);
    assert.equal(result().is_valid, true, family + ': current response');
    first.callback({ message: { success: false, is_valid: false } });
    assert.equal(result().is_valid, true, family + ': older response cannot overwrite');
    inst.destroy();
    latest.callback({ message: { success: false, is_valid: false } });
    assert.equal(result().is_valid, true, family + ': teardown response');
    dom.window.close();
  }
});

test('programmatic input changes without events also invalidate an in-flight calculation', () => {
  const { dom, $, api, requests } = setup('<div id="host"><input name="length" value="10"></div>');
  const inst = new api.Base($('#host'), {});
  let accepted = false;
  inst.request({ method: 'calculate', isCurrent: inst.validationGuard(), callback() { accepted = true; } });
  inst.$name('length').val('30');
  requests[0].callback({});
  assert.equal(accepted, false);
  dom.window.close();
});

test('family event handlers are removed on close and no request starts from a destroyed instance', () => {
  const { dom, $, api, requests } = setup('<div id="host"><button id="btnCalculate">Calculate</button></div>');
  const inst = new api.TapeNeon($('#host'), {});
  let calls = 0;
  inst.doCalculate = () => calls++;
  inst._bindEvents();
  inst.$('#btnCalculate').trigger('click');
  assert.equal(calls, 1);
  inst.destroy();
  $('#host button').trigger('click');
  inst.request({ method: 'should-not-run' });
  assert.equal(calls, 1);
  assert.equal(requests.length, 0);
  dom.window.close();
});

test('template picker supports keyboard navigation, repeat mount, selection and cleanup', () => {
  const { dom, $, api } = setup('<select id="templates"><option></option><option value="A">Alpha</option><option value="B">Beta</option></select><div id="picker"></div>');
  const opts = { $select: $('#templates'), $container: $('#picker') };
  api.renderTemplateCards(opts);
  const picker = api.renderTemplateCards(opts);
  let changes = 0;
  $('#templates').on('change.test', () => changes++);
  const cards = $('#picker .ill-template-card');
  cards.first().trigger('focus').trigger($.Event('keydown', { key: 'ArrowRight' }));
  assert.equal(dom.window.document.activeElement, cards[1]);
  cards.last().trigger('click');
  assert.equal($('#templates').val(), 'B');
  assert.equal(changes, 1);
  picker.destroy();
  $('#picker .ill-template-card').first().trigger('click');
  assert.equal(changes, 1);
  dom.window.close();
});

test('tape and neon send excluded power, control protocol, and run limit to calculation and Desk save', () => {
  for (const neon of [false, true]) {
    const { dom, $, api, requests } = setup('<div id="host"><input id="includePowerSupply" type="checkbox"><input id="overrideMaxRunCheck" type="checkbox" checked><input id="overrideMaxRunInput" value="12"><select name="dimming_protocol_code"><option value="0-10V">0-10V</option></select></div>');
    let saved;
    const inst = new api.TapeNeon($('#host'), { is_neon: neon, saveHandler: data => { saved = data; } });
    inst._showResults = () => {};
    inst._collectNeonSegments = () => [{ fixture_length_value: 100 }];
    inst.doCalculate();
    const request = requests.at(-1);
    assert.equal(request.args.include_power_supply, false);
    assert.equal(request.args.dimming_protocol_code, '0-10V');
    assert.equal(request.args.override_max_run_ft, 12);
    request.callback({ message: { is_valid: true, include_power_supply: false } });
    inst.saveToSchedule();
    assert.equal(saved.selections.include_power_supply, false);
    assert.equal(saved.selections.dimming_protocol_code, '0-10V');
    assert.equal(saved.selections.override_max_run_ft, 12);
    dom.window.close();
  }
});

test('clearing a fixture template invalidates in-flight options for that template', () => {
  const { dom, $, api, requests } = setup('<div id="host"><select id="fixtureTemplateSelect"></select></div>');
  const inst = new api.Fixture($('#host'), {});
  inst._updateProgress = inst._updateSummary = inst._updateButtons = inst._clearSegments = () => {};
  let populated = false;
  inst._populateOptions = () => { populated = true; };
  inst._onTemplateSelected('ILL-SH01-SW');
  const old = requests.at(-1);
  inst._onTemplateSelected('');
  old.callback({ message: { success: true, options: {} } });
  assert.equal(populated, false);
  assert.equal(inst.isInitialized, false);
  dom.window.close();
});

test('invalid run overrides cannot silently fall back to the default', () => {
  for (const value of ['', '-1', 'Infinity', '12feet']) {
    const { dom, $, api, requests } = setup('<div id="host"><input id="overrideMaxRunCheck" type="checkbox" checked><input id="overrideMaxRunInput"></div>');
    const inst = new api.TapeNeon($('#host'), { is_neon: false });
    inst.$('#overrideMaxRunInput').val(value);
    let error;
    inst._showError = message => { error = message; };
    inst.doCalculate();
    assert.match(error, /greater than zero/);
    assert.equal(requests.length, 0);
    dom.window.close();
  }
});

test('tearing down a document adapter does not destroy an embedded picker', () => {
  const { dom, $, api } = setup('<div id="host"><select id="templates"><option></option><option value="A">Alpha</option></select><div id="picker"></div></div>');
  const legacy = new api.Base(dom.window.document, {});
  const embedded = new api.Base($('#host'), {});
  const picker = api.renderTemplateCards({ $select: embedded.$('#templates'), $container: embedded.$('#picker') });
  legacy.destroy();
  assert.equal(embedded.$('#picker').data('illTemplatePicker'), picker);
  embedded.$('.ill-template-card').trigger('click');
  assert.equal(embedded.$('#templates').val(), 'A');
  dom.window.close();
});

const TAPE_FAMILIES = ['LED Tape', 'COB Tape'];

test('rendered coordinator mounts all legacy families and retains tape reels and segment actions', () => {
  for (const category of ['Linear Fixture', 'LED Tape', 'COB Tape', 'LED Neon']) {
    const html = fs.readFileSync(path.join(__dirname, 'rendered', category.replaceAll(' ', '-') + '-coordinator.html'), 'utf8');
    const { dom, $, api, requests } = setup(html);
    const context = { product_category: category, is_tape: TAPE_FAMILIES.includes(category), is_neon: category === 'LED Neon', is_tape_neon: category !== 'Linear Fixture', has_templates: false };
    const inst = new api.Coordinator($('#portal-configurator'), context);
    inst.init();
    assert.ok(requests.length > 0, category);
    if (TAPE_FAMILIES.includes(category)) {
      assert.equal(inst.$('#tapeSegmentsList .tape-segment-card').length, 1);
      inst.$('#tapeModeReelBtn').trigger('click');
      assert.ok(inst.$('#tapeModeReelBtn').hasClass('btn-primary'));
      inst.$('#brReel50').trigger('click');
      assert.ok(inst.$('#brReel50').hasClass('active'));
      inst.$('#tapeModeCustomBtn').trigger('click');
      assert.equal(inst.$('#tapeSegmentsList .tape-segment-card').length, 1);
    }
    if (category === 'LED Neon') assert.equal(inst.$('#neonSegmentsList .neon-segment-card').length, 1);
    const count = requests.length;
    inst.destroy();
    const reopened = new api.Coordinator($('#portal-configurator'), context);
    reopened.init();
    assert.equal(requests.length - count, count, category + ': one set of loaders on reopen');
    dom.window.close();
  }
});

test('all coordinator families omit unused numeric overrides after form encoding', () => {
  for (const category of ['Linear Fixture', 'LED Tape', 'COB Tape', 'LED Neon']) {
    const html = fs.readFileSync(path.join(__dirname, 'rendered', category.replaceAll(' ', '-') + '-coordinator.html'), 'utf8');
    const { dom, $, api, requests } = setup(html);
    const inst = new api.Coordinator($('#portal-configurator'), { product_category: category, is_tape: TAPE_FAMILIES.includes(category), is_neon: category === 'LED Neon', is_tape_neon: category !== 'Linear Fixture', has_templates: false });
    inst.init();
    if (category === 'Linear Fixture') {
      inst.restoreGeometry({segments: [{requested_length_mm: 1000, end_type: 'Endcap'}]});
      inst.$name('delivered_output_value').append('<option value="100">100</option>').val('100');
    }
    const calculate = () => inst.$(category === 'Linear Fixture' ? '#calculateBtn' : '#tnCalculateBtn').prop('disabled', false).trigger('click');
    inst.$('#overrideMaxRunCheck').prop('checked', false);
    inst.$('#includePowerSupply').prop('checked', false);
    calculate();
    const blank = requests.at(-1);
    assert.match(blank.method, /validate_/);
    assert.equal(Object.hasOwn(blank.args, 'override_max_run_ft'), false, category);
    const encoded = new URLSearchParams($.param(blank.args));
    assert.equal(encoded.has('override_max_run_ft'), false, category);
    assert.equal(encoded.get('include_power_supply'), 'false');
    assert.equal(encoded.get('_skip_record_creation'), 'true');
    inst.$('#overrideMaxRunCheck').prop('checked', true);
    inst.$('#overrideMaxRunInput').val('12.5');
    calculate();
    assert.equal(requests.at(-1).args.override_max_run_ft, 12.5, category);
    for (const value of ['', '0', '-1', 'Infinity', '12feet']) {
      inst.$('#overrideMaxRunInput').val(value);
      const before = requests.length;
      calculate();
      assert.equal(requests.length, before, category + ': invalid override ' + value);
    }
    dom.window.close();
  }
});

test('embedded fixture rejects invalid enabled overrides before sending a request', () => {
  for (const value of ['', '0', '-1', 'Infinity', '12feet']) {
    const {dom, $, api, requests} = setup('<div id="host"><input id="overrideMaxRunCheck" type="checkbox" checked><input id="overrideMaxRunInput"></div>');
    const inst = new api.Fixture($('#host'), {});
    inst.$('#overrideMaxRunInput').val(value);
    inst._gatherAllSelections = () => ({segments: [{requested_length_mm: 1000, end_type: 'Endcap'}], delivered_output_value: 100, override_max_run_ft: inst._getOverrideMaxRunFt()});
    inst.validateConfiguration();
    assert.equal(requests.length, 0, value);
    dom.window.close();
  }
});

test('COB Tape configures with the tape steps and saves as its own family', () => {
  const html = fs.readFileSync(path.join(__dirname, 'rendered/COB-Tape-coordinator.html'), 'utf8');
  const { dom, $, api, requests } = setup(html);
  assert.ok($('#categorySelector .pill-option[data-category="COB Tape"]').hasClass('active'));
  const inst = new api.Coordinator($('#portal-configurator'), { product_category: 'COB Tape', is_tape: true, is_tape_neon: true, has_templates: false, selected_template: 'cob-sd-sw' });
  inst.init();
  assert.equal(inst.$('#tapeSegmentsList .tape-segment-card').length, 1);
  assert.equal(inst.$('#neonSegmentsList .neon-segment-card').length, 0);
  inst.$('#tnCalculateBtn').prop('disabled', false).trigger('click');
  assert.match(requests.at(-1).method, /validate_tape_configuration/);
  const request = inst.exportRequest();
  assert.equal(request.family, 'COB Tape');
  assert.equal(request.template, 'cob-sd-sw');
  assert.ok(Array.isArray(request.segments));
  dom.window.close();
});

test('coordinator ignores a calculation after input changes or close', () => {
  const html = fs.readFileSync(path.join(__dirname, 'rendered/LED-Tape-coordinator.html'), 'utf8');
  const { dom, $, api, requests } = setup(html);
  const inst = new api.Coordinator($('#portal-configurator'), { product_category: 'LED Tape', is_tape: true, is_tape_neon: true, has_templates: false });
  inst.init();
  const calculate = () => inst.$('#tnCalculateBtn').prop('disabled', false).trigger('click');
  const response = { message: { is_valid: false, error: 'Rejected calculation' } };
  calculate();
  const old = requests.at(-1);
  assert.match(old.method, /validate_tape_configuration/);
  inst.$('#includePowerSupply').prop('checked', false).trigger('change');
  // A material edit in the cloned template is also caught by the root handler.
  inst.$('#tapeSegmentsList input').first().val('72').trigger('input');
  old.callback(response);
  assert.notEqual(inst.$('#validationStatus').text(), 'Invalid');
  calculate();
  requests.at(-1).callback(response);
  assert.equal(inst.$('#validationStatus').text(), 'Invalid');
  calculate();
  const pending = requests.at(-1);
  inst.destroy();
  pending.callback({ message: { is_valid: true } });
  assert.equal($('#portal-configurator [data-ill-original-id="validationStatus"]').text(), 'Invalid');
  dom.window.close();
});

test('schedule saves use stable line keys, guard duplicate clicks, and reuse the key on retry', () => {
  const { dom, $, api, requests } = setup('<div id="host"></div>');
  const inst = new api.Base($('#host'), {});
  inst.setScheduleSnapshot({ modified: 'revision-1', lines: [{ idx: 0, line_key: 'line-a' }] });
  const data = { family: 'LED Sheet', schedule_name: 'S1', line_idx: 0, selections: { template: 'Sheet', include_power_supply: false } };
  let receipt;
  const callbacks = { success: value => { receipt = value; } };
  inst.saveScheduleConfiguration(data, callbacks);
  inst.saveScheduleConfiguration(data, callbacks);
  assert.equal(requests.length, 1);
  const first = requests[0];
  assert.equal(first.args.line_key, 'line-a');
  assert.equal(first.args.line_idx, null);
  assert.equal(first.args.expected_modified, 'revision-1');
  first.error();
  first.always();
  inst.saveScheduleConfiguration(data, callbacks);
  assert.equal(requests[1].args.idempotency_key, first.args.idempotency_key);
  requests[1].callback({ message: { success: true, already_existed: true, line_key: 'line-a' } });
  requests[1].always();
  assert.equal(receipt.line_key, 'line-a');
  dom.window.close();
});

test('portal Sheet save is one atomic request without creating a provisional empty line', () => {
  const { dom, $, api, requests } = setup('<div id="host"></div>');
  const inst = new api.LedSheet($('#host'), { schedule_name: 'S1', expected_modified: 'revision-1' });
  inst.lastResult = { success: true };
  inst._gatherAllSelections = () => ({ template: 'Sheet', spec: 'Snowfield', include_power_supply: false, coverage_width_value: 12, coverage_width_unit: 'in' });
  inst.addToSchedule();
  assert.equal(requests.length, 1);
  assert.match(requests[0].method, /portal.configuration.save$/);
  assert.equal(requests[0].args.line_idx, null);
  assert.equal(JSON.parse(requests[0].args.selections).coverage_width_unit, 'in');
  dom.window.close();
});


test('coordinator reopens independent tape segments and preserves excluded power and zero leader', () => {
  const html = fs.readFileSync(path.join(__dirname, 'rendered/LED-Tape-coordinator.html'), 'utf8');
  const { dom, $, api, requests } = setup(html);
  const segments = [
    { tape_length_unit: 'ft', tape_length_value: 6, start_feed_direction: 'End', start_lead_length_inches: 0, end_type: 'Jumper', end_feed_direction: 'End', end_feed_length_inches: 18 },
    { tape_length_unit: 'in', tape_length_value: 22, start_feed_direction: 'End', start_lead_length_inches: 18, end_type: 'Endcap', end_feed_direction: '', end_feed_length_inches: 0 }
  ];
  const inst = new api.Coordinator($('#portal-configurator'), { product_category: 'LED Tape', is_tape: true, is_tape_neon: true, has_templates: false,
    initial_request: { selections: { cct: '3000K', output_level: 'High', environment_rating: 'Dry', include_power_supply: false, override_max_run_ft: 8 }, segments } });
  inst.init();
  requests.find(r => r.method.endsWith('get_tape_neon_spec_init')).callback({ message: { success: true, options: { ccts: [{ value: '3000K' }], output_levels: [{ value: 'High' }], environment_ratings: [{ value: 'Dry' }] } } });
  assert.equal(inst.$('#tapeSegmentsList .tape-segment-card').length, 2);
  assert.equal(inst.$('#includePowerSupply').prop('checked'), false);
  inst.$('#tnCalculateBtn').prop('disabled', false).trigger('click');
  const calc = requests.at(-1);
  assert.match(calc.method, /validate_tape_configuration/);
  const actual = JSON.parse(calc.args.segments_json);
  assert.equal(actual[0].start_lead_length_inches, 0);
  assert.equal(actual[0].end_feed_length_inches, 18);
  assert.equal(actual[1].start_lead_length_inches, 18);
  assert.equal(actual[1].tape_length_value, 22);
  assert.equal(calc.args.include_power_supply, false);
  assert.equal(calc.args.override_max_run_ft, 8);
  dom.window.close();
});

test('coordinator jumper edits made after the next segment is added reach its inherited start', async () => {
  for (const family of ['neon', 'tape']) {
    const category = family === 'neon' ? 'LED Neon' : 'LED Tape';
    const html = fs.readFileSync(path.join(__dirname, 'rendered', category.replace(' ', '-') + '-coordinator.html'), 'utf8');
    const { dom, $, api, requests } = setup(html);
    const inst = new api.Coordinator($('#portal-configurator'), { product_category: category, is_tape: family === 'tape', is_neon: family === 'neon', is_tape_neon: true, has_templates: false });
    inst.init();
    const feedDirections = [{ value: 'End', label: 'End' }, { value: 'Back', label: 'Back' }];
    requests.find(r => r.method.endsWith('get_tape_neon_spec_init')).callback({ message: { success: true, options: { ccts: [{ value: '3000K' }], output_levels: [{ value: 'High' }], ip_ratings: [{ value: 'IP67', label: 'IP67' }], feed_directions: feedDirections } } });
    const cards = () => inst.$('#' + family + 'SegmentsList .' + family + '-segment-card');
    cards().first().find('[data-coordinator-action="set' + (family === 'neon' ? 'Neon' : 'Tape') + 'EndType-' + (family === 'neon' ? 25 : 22) + '"]').trigger('click');
    await new Promise(resolve => setTimeout(resolve, 150));
    assert.equal(cards().length, 2, family);
    // The user sets the jumper only after the next segment has been auto-added.
    cards().first().find('[name="' + family + '_end_feed_direction"]').val('Back').trigger('change');
    cards().first().find('[name="' + family + '_end_feed_length_inches"]').val('6').trigger('input');
    assert.match(cards().last().find('.' + family + '-inherited-text').text(), /Back, 6" jumper/, family);
    inst.$('#tnCalculateBtn').prop('disabled', false).trigger('click');
    const calc = requests.at(-1);
    assert.match(calc.method, family === 'neon' ? /validate_neon_configuration/ : /validate_tape_configuration/);
    const actual = JSON.parse(calc.args.segments_json);
    assert.equal(actual[0].end_feed_length_inches, 6, family);
    assert.equal(actual[1].start_feed_direction, 'Back', family);
    assert.equal(actual[1].start_lead_length_inches, 6, family);
    inst.destroy();
    dom.window.close();
  }
});

test('coordinator hands desk hosts a segment list and keeps the portal save argument unchanged', () => {
  for (const family of ['neon', 'tape']) {
    const category = family === 'neon' ? 'LED Neon' : 'LED Tape';
    const html = fs.readFileSync(path.join(__dirname, 'rendered', category.replace(' ', '-') + '-coordinator.html'), 'utf8');
    for (const desk of [true, false]) {
      const { dom, $, api, requests } = setup(html);
      const saved = [];
      const inst = new api.Coordinator($('#portal-configurator'), { product_category: category, is_tape: family === 'tape', is_neon: family === 'neon', is_tape_neon: true, has_templates: false,
        saveHandler: desk ? payload => saved.push(payload) : undefined });
      inst.init();
      requests.find(r => r.method.endsWith('get_tape_neon_spec_init')).callback({ message: { success: true, options: { ccts: [{ value: '3000K' }], output_levels: [{ value: 'High' }], ip_ratings: [{ value: 'IP67', label: 'IP67' }] } } });
      inst.$('#tnCalculateBtn').prop('disabled', false).trigger('click');
      const calc = requests.at(-1);
      calc.callback({ message: { success: true, is_valid: true, computed: {} } });
      if (!desk) {
        inst.$('#scheduleSelect').append($('<option>').val('S1')).val('S1');
        inst.$('#lineSelect').append($('<option>').val('__new__')).val('__new__');
        inst.setScheduleSnapshot({ modified: 'r1', lines: [] });
      }
      inst.$('#tnSaveBtn').prop('disabled', false).trigger('click');
      if (desk) {
        assert.equal(saved.length, 1, family);
        assert.ok(Array.isArray(saved[0].segments), family + ': desk receives a list, not encoded JSON');
        assert.deepEqual(JSON.parse(JSON.stringify(saved[0].segments)), JSON.parse(calc.args.segments_json));
      } else {
        const save = requests.at(-1);
        assert.match(save.method, /portal.configuration.save$/);
        assert.equal(save.args.segments, calc.args.segments_json, family + ': portal sends the calculated argument');
      }
      inst.destroy();
      dom.window.close();
    }
  }
});

test('reel preview is read-only and saving submits input to the atomic service', () => {
  const html = fs.readFileSync(path.join(__dirname, 'rendered/LED-Tape-coordinator.html'), 'utf8');
  const { dom, $, api, requests } = setup(html);
  const inst = new api.Coordinator($('#portal-configurator'), { product_category: 'LED Tape', is_tape: true, is_tape_neon: true, has_templates: false });
  inst.init();
  inst.$name('fixture_template_code').append($('<option>').val('led-hd-sw')).val('led-hd-sw');
  inst.$name('tn_cct').append($('<option>').val('3000K')).val('3000K');
  inst.$name('tn_output_level').append($('<option>').val('High')).val('High');
  inst.$('#tapeModeReelBtn').trigger('click');
  inst.$('#brReel50').trigger('click');
  inst.$('#brCalculateBtn').prop('disabled', false).trigger('click');
  const calc = requests.at(-1);
  assert.equal(calc.args._skip_record_creation, true);
  assert.equal(JSON.parse(calc.args.selections).ordering_mode, 'BULK_REEL');
  calc.callback({ message: { is_valid: true } });
  inst.$('#scheduleSelect').append($('<option>').val('S1')).val('S1');
  inst.$('#lineSelect').append($('<option>').val('__new__')).val('__new__');
  inst.setScheduleSnapshot({ modified: 'r1', lines: [] });
  inst.$('#brSaveBtn').prop('disabled', false).trigger('click');
  assert.match(requests.at(-1).method, /portal.configuration.save$/);
  assert.equal(JSON.parse(requests.at(-1).args.selections).tape_length_value, 50);
  assert.equal(requests.at(-1).args.configuration_result, undefined);
  dom.window.close();
});


test('group editor keeps independent geometry and only sends canonical intent on save', () => {
  const {dom, $, api, requests} = setup('<div id="host"><input id="length" value="100"><input id="leader" value="72"><button data-action="validate">Single calculate</button></div>');
  const saved = [];
  const instance = new api.Base($('#host'), {groups_enabled: true, saveHandler: value => saved.push(value)});
  instance.exportRequest = () => ({family: 'Linear Fixture', template: 'ILL-SH01-SW', selections: {
    finish_code: 'White', include_power_supply: false, override_max_run_ft: '', segments: [{requested_length_mm: Number(instance.$('#length').val()), start_leader_cable_length_mm: Number(instance.$('#leader').val()), end_type: 'Endcap'}]
  }});
  instance.restoreGeometry = geometry => {
    instance.$('#length').val(geometry.segments[0].requested_length_mm);
    instance.$('#leader').val(geometry.segments[0].start_leader_cable_length_mm);
  };
  api.attachGroupEditor(instance);
  const group = instance.groupEditor;
  group.$toggle[0].click();
  group.add();
  instance.$('#length').val('200').trigger('input');
  instance.$('#leader').val('36').trigger('input');
  group.select(0);
  assert.equal(instance.$('#length').val(), '100');
  assert.equal(instance.$('#leader').val(), '72');
  const request = group.request();
  assert.deepEqual(JSON.parse(JSON.stringify(request.members.map(m => m.input.segments[0].requested_length_mm))), [100, 200]);
  assert.equal(request.power.include_power_supply, false);
  group.calculate();
  const call = requests.at(-1);
  assert.match(call.method, /fixture_group_configurator.preview$/);
  assert.equal(JSON.parse(call.args.request).members.length, 2);
  group.renderResult = () => {};
  call.callback({message: {success: true, config_hash: 'server-result'}});
  group.save();
  assert.equal(saved.length, 1);
  assert.equal(saved[0].selections.group_request.members.length, 2);
  assert.equal(saved[0].selections.group_request.computed, undefined);
  instance.$('#length').val('300').trigger('input');
  group.save();
  assert.equal(saved.length, 1);
  assert.equal(group.$save.prop('disabled'), true);
  instance.destroy();
  assert.equal($('#host .ill-group-editor').length, 0);
  dom.window.close();
});

test('group reopen unwraps only the active member and retains the complete request', () => {
  const {dom, $, api} = setup('<div id="host"></div>');
  const group = {family: 'LED Sheet', template: 'Snowfield', shared: {spec: 'SW', options: {CCT: '3000K'}}, power: {include_power_supply: false}, members: [
    {label: 'Area A', input: {coverage_width_ft: 2, coverage_height_ft: 3}},
    {label: 'Area B', input: {coverage_width_ft: 4, coverage_height_ft: 5}}
  ]};
  const inst = new api.Base($('#host'), {initial_request: {selections: {group_request: group}}});
  assert.equal(inst.context.initial_group.members.length, 2);
  assert.equal(inst.context.initial_request.selections.coverage_width_ft, 2);
  assert.equal(inst.context.initial_request.selections.include_power_supply, false);
  assert.equal(inst.context.selected_template, 'Snowfield');
  inst.destroy();
  dom.window.close();
});

test('an endcap neon end sends no cable even when the hidden jumper input keeps its default', () => {
  const html = fs.readFileSync(path.join(__dirname, 'rendered/LED-Neon-coordinator.html'), 'utf8');
  const { dom, $, api, requests } = setup(html);
  const inst = new api.Coordinator($('#portal-configurator'), { product_category: 'LED Neon', is_neon: true, is_tape_neon: true, has_templates: false });
  inst.init();
  requests.find(r => r.method.endsWith('get_tape_neon_spec_init')).callback({ message: { success: true, options: { ccts: [{ value: '3000K' }], output_levels: [{ value: 'High' }], ip_ratings: [{ value: 'IP67', label: 'IP67' }] } } });
  const card = inst.$('#neonSegmentsList .neon-segment-card').first();
  assert.equal(card.find('[name="neon_end_type"]').val(), 'Endcap');
  assert.equal(card.find('[name="neon_end_feed_length_inches"]').val(), '12');
  inst.$('#tnCalculateBtn').prop('disabled', false).trigger('click');
  const [segment] = JSON.parse(requests.at(-1).args.segments_json);
  assert.equal(segment.end_type, 'Endcap');
  assert.equal(segment.end_feed_length_inches, 0);
  assert.equal(segment.end_feed_direction, '');
  inst.destroy();
  dom.window.close();
});

test('LED Sheet options select the panel spec; buyers are not asked for it', () => {
  const html = fs.readFileSync(path.join(__dirname, 'rendered/LED-Sheet-coordinator.html'), 'utf8');
  const { dom, $, api } = setup(html);
  const option = (option_type, attribute_link, option_code, is_default) => ({ option_type, attribute_link, option_code, is_default, msrp_adder: 0 });
  const templates = [{
    name: 'SNF-SW', template_name: 'Snowfield Static White',
    allowed_specs: [
      { name: 'SPEC-O-10', item: 'LED-SNF-SW-O-10W-SHEET', sheet_width_ft: 1, sheet_height_ft: 2, total_sheet_watts: 10 },
      { name: 'SPEC-I-10', item: 'LED-SNF-SW-I-10W-SHEET', sheet_width_ft: 1, sheet_height_ft: 2, total_sheet_watts: 10 }
    ],
    allowed_options: [option('CCT', '3000K', '30K', 1), option('Output Level', '10W', '10W', 1),
      option('Environment Rating', 'Outdoor', 'O', 1), option('Environment Rating', 'Indoor', 'I', 0), option('Finish', 'White', 'WH', 1)]
  }];
  const inst = new api.LedSheet($('#portal-configurator'), { templates, can_save: true });
  inst.init();
  inst.$('#sheetTemplate').append($('<option>').val('SNF-SW')).val('SNF-SW').trigger('change');
  assert.equal(inst.$('#sheetSpecSection .pill').length, 0, 'no panel spec picker');
  assert.equal(inst.$('#sheetSpecMatch').text(), 'LED-SNF-SW-O-10W-SHEET');
  inst.$('#sheetEnvironment').val('Indoor').trigger('change');
  assert.equal(inst.$('#sheetSpecMatch').text(), 'LED-SNF-SW-I-10W-SHEET');
  assert.equal(inst.exportRequest().selections.spec, null, 'the server derives the spec');
  inst.destroy();
  dom.window.close();
});

test('multi-run group sits beside the run controls and drives a tape coordinator end to end', async () => {
  const html = fs.readFileSync(path.join(__dirname, 'rendered/LED-Tape-coordinator.html'), 'utf8');
  const { dom, $, api, requests } = setup(html);
  const inst = new api.Coordinator($('#portal-configurator'), { product_category: 'LED Tape', is_tape: true, is_tape_neon: true, has_templates: false, groups_enabled: true, selected_template: 'TAPE-T' });
  inst.init();
  await new Promise(resolve => setTimeout(resolve, 5));
  const group = inst.groupEditor;
  const length = () => inst.$('#tapeSegmentsList [name="tape_length_value"]').first();
  const summaries = () => group.$list.find('.ill-run-summary').map((_, node) => $(node).text()).get();
  // The run list precedes the length controls; group actions replace the single-run ones.
  assert.equal(group.$panel.next().attr('data-ill-original-id'), 'tapeModeToggleCard');
  assert.equal(group.$actions.next().attr('data-ill-original-id'), 'tnActionButtons');
  assert.equal(group.$actions.is(':visible') || group.$actions.css('display') === 'none', true);
  group.$toggle[0].click();
  assert.equal(inst.$root.hasClass('ill-group-active'), true);
  assert.equal(inst.$('#tnCalculateBtn').hasClass('ill-single-action'), true);
  length().val('120').trigger('input');
  assert.deepEqual(summaries(), ["10' · 1' leader"]);
  // A new run keeps the feed settings but starts without a length, so calculation names it.
  group.add();
  assert.equal(length().val(), '');
  const before = requests.length;
  group.calculate();
  assert.equal(requests.length, before, 'an incomplete run is not sent');
  assert.match(group.$status.text(), /Run 2/);
  length().val('60').trigger('input');
  group.$list.find('.ill-run-label').eq(1).val('North wall').trigger('input');
  group.duplicate(0);
  assert.deepEqual(summaries(), ["10' · 1' leader", "5' · 1' leader", "10' · 1' leader"]);
  assert.deepEqual(Array.from(group.members, m => m.label), ['Run 1', 'North wall', 'Run 1 (copy)']);
  group.select(0);
  assert.equal(length().val(), '120');
  group.calculate();
  const call = requests.at(-1);
  assert.match(call.method, /fixture_group_configurator.preview$/);
  const sent = JSON.parse(call.args.request);
  assert.equal(sent.template, 'TAPE-T');
  assert.equal(sent.power.separate_supply_line, true);
  assert.deepEqual(sent.members.map(m => m.input.segments[0].tape_length_value), [120, 60, 120]);
  const presentation = sent.members.map((m, i) => ({member_key: 'M' + (i + 1), label: m.label}));
  call.callback({message: {success: true, presentation,
    runs: presentation.map(p => ({...p, requested_length_mm: 3048, manufactured_length_mm: 3048, segments: 1, circuits: 1, watts: 20})),
    build: {members: sent.members, total_watts: 60, voltage: '24V', output_protocol: 'PWM', power_plan: {status: 'selected',
      drivers: [{driver_item: 'PS-96', qty: 1}], requirements: [{}, {}, {}], allocations: [{run_key: 'M2:1', supply: 1, item_code: 'PS-96', output: 2, watts: 20}]}},
    pricing: {breakdown: [{member: 'M3', extended_msrp: 300}, {member: 'M1', extended_msrp: 300}, {member: 'M2', extended_msrp: 150}], msrp_unit: 750, tier_unit: 600}}});
  assert.equal(group.$save.prop('disabled'), false);
  assert.match(group.$result.text(), /North wall, circuit 1 → supply 1 \(PS-96\), output 2/);
  assert.match(group.$result.text(), /\$600\.00/);
  // Renaming a run is presentation only: the calculation stays valid and shows the new name.
  group.$list.find('.ill-run-label').eq(0).val('South wall').trigger('input');
  assert.equal(group.$save.prop('disabled'), false);
  assert.match(group.$result.text(), /South wall/);
  inst.$('#scheduleSelect').append($('<option>').val('S1')).val('S1');
  inst.$('#lineSelect').append($('<option>').val('__new__')).val('__new__');
  inst.setScheduleSnapshot({ modified: 'r1', lines: [] });
  group.save();
  const save = requests.at(-1);
  assert.match(save.method, /portal.configuration.save$/);
  const saved = JSON.parse(save.args.selections).group_request;
  assert.deepEqual(saved.members.map(m => m.label), ['South wall', 'North wall', 'Run 1 (copy)']);
  // Editing a length afterwards requires a new calculation.
  length().val('130').trigger('input');
  assert.equal(group.$save.prop('disabled'), true);
  group.$single[0].click();
  assert.equal(inst.$root.hasClass('ill-group-active'), false);
  assert.equal(inst.exportRequest().selections.group_request, undefined);
  inst.destroy();
  assert.equal($('.ill-group-editor, .ill-group-actions, .ill-group-result').length, 0);
  dom.window.close();
});

test('group run summaries read every family length format', () => {
  const { dom, api } = setup('');
  const { feetInches, summarize } = api.GroupEditor;
  assert.equal(feetInches(6248.4), "20' 6\"");
  assert.equal(feetInches(3657.6), "12'");
  assert.equal(feetInches(25.4), '1"');
  assert.equal(summarize({segments: [{requested_length_mm: 6096, start_leader_cable_length_mm: 1828.8}]}, 'Linear Fixture').text, "20' · 6' leader");
  assert.equal(summarize({segments: [{tape_length_unit: 'ft_in', tape_length_feet: 5, tape_length_inches: 6}]}, 'LED Tape').text, "5' 6\"");
  assert.equal(summarize({segments: [{fixture_length_unit: 'ft', fixture_length_value: 3, end_type: 'Jumper'}, {fixture_length_unit: 'in', fixture_length_value: 24}]}, 'LED Neon').text, "5' · 2 jumpered segments");
  assert.equal(summarize({segments: [{requested_length_mm: ''}]}, 'Linear Fixture').empty, true);
  assert.equal(summarize({coverage_width_value: 600, coverage_width_unit: 'mm', coverage_height_ft: 4}, 'LED Sheet').empty, false);
  assert.equal(summarize({coverage_width_value: '', coverage_height_ft: 4}, 'LED Sheet').empty, true);
  dom.window.close();
});

test('restoring a linear run shows inches and keeps its millimetre length', () => {
  const html = fs.readFileSync(path.join(__dirname, 'rendered/Linear-Fixture-coordinator.html'), 'utf8');
  const { dom, $, api } = setup(html);
  const inst = new api.Coordinator($('#portal-configurator'), { product_category: 'Linear Fixture', has_templates: false });
  inst.init();
  inst.restoreGeometry({segments: [{requested_length_mm: 1000, start_leader_cable_length_mm: 304.8, end_type: 'Endcap'}]});
  const card = inst.$('.segment-card').first();
  assert.equal(card.find('[name="length_unit"]').val(), 'in');
  assert.equal(inst.exportRequest().selections.segments[0].requested_length_mm, 1000);
  // A later unit change converts from inches, not from a stale unit.
  card.find('[name="length_unit"]').val('mm').trigger('change');
  assert.equal(Math.round(Number(card.find('[name="requested_length_mm"]').val())), 1000);
  inst.destroy();
  dom.window.close();
});
