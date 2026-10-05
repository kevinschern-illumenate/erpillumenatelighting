// Schedule add-line modal: the Product Category option decides the template category.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const jquery = require('jquery');

const SCHEDULE = fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/templates/pages/schedule.html'), 'utf8');

function helpers() {
  // The helpers live in the page's inline script; render their Jinja labels as plain text.
  const start = SCHEDULE.indexOf('function tapeNeonCategoryOf(');
  const end = SCHEDULE.indexOf('// Load tape/neon templates from the server');
  assert.ok(start > 0 && end > start, 'add-line category helpers are present');
  const source = SCHEDULE.slice(start, end).replace(/\{\{ _\("([^"]+)"\) \}\}/g, '$1');
  const dom = new JSDOM('<body><select id="add_product_type"></select></body>', { runScripts: 'outside-only' });
  const w = dom.window;
  w.$ = w.jQuery = jquery(w);
  w.eval(source + '; window.tapeNeonCategoryOf = tapeNeonCategoryOf; window.configureTapeNeonLabel = configureTapeNeonLabel;');
  return { dom, w, $: w.$ };
}

function option($, label, category) {
  const $option = $('<option></option>').attr('value', label).text(label);
  if (category !== undefined) $option.attr('data-tape-neon-category', category);
  return $option;
}

test('COB Tape loads COB Tape series and offers "Configure COB Tape Now"', () => {
  const { dom, w, $ } = helpers();
  const cob = option($, 'COB Tape', 'COB Tape');
  assert.equal(w.tapeNeonCategoryOf(cob), 'COB Tape');
  assert.equal(w.configureTapeNeonLabel('COB Tape'), 'Configure COB Tape Now');
  assert.equal(w.configureTapeNeonLabel('LED Tape'), 'Configure LED Tape Now');
  assert.equal(w.configureTapeNeonLabel('LED Neon'), 'Configure LED Neon Now');
  dom.window.close();
});

test('the server category wins over the group label, and older payloads fall back to the label', () => {
  const { dom, w, $ } = helpers();
  assert.equal(w.tapeNeonCategoryOf(option($, 'Flexible Strip', 'COB Tape')), 'COB Tape');
  assert.equal(w.tapeNeonCategoryOf(option($, '  └─ COB Tape')), 'COB Tape');
  assert.equal(w.tapeNeonCategoryOf(option($, 'LED Neon', '')), 'LED Neon');
  assert.equal(w.tapeNeonCategoryOf(option($, 'LED Tape')), 'LED Tape');
  dom.window.close();
});

test('series loading, the configure button and the configurator hand-off all use the option category', () => {
  const loader = SCHEDULE.slice(SCHEDULE.indexOf('function loadTapeNeonTemplates('));
  assert.match(loader.slice(0, 400), /var productCategory = tapeNeonCategoryOf\(/);
  const handoff = SCHEDULE.slice(SCHEDULE.indexOf('function configureFromAddModal('));
  assert.match(handoff.slice(0, 800), /: tapeNeonCategoryOf\(option\);/);
  assert.match(SCHEDULE, /data-tape-neon-category="' \+ \(pt\.tape_neon_category \|\| ''\) \+ '"/);
  assert.doesNotMatch(SCHEDULE, /includes\('neon'\) \? 'LED Neon' : 'LED Tape'/);
});
