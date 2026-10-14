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
  assert.match(SCHEDULE, /data-tape-neon-category="' \+ PortalUI\.escape\(pt\.tape_neon_category \|\| ''\) \+ '"/);
  assert.doesNotMatch(SCHEDULE, /includes\('neon'\) \? 'LED Neon' : 'LED Tape'/);
});

test('Extrusion Kits groups pick a kit template and hand off to the kit configurator', () => {
  const start = SCHEDULE.indexOf('function isExtrusionKitOption(');
  const end = SCHEDULE.indexOf('// Load Extrusion Kit templates from the server');
  assert.ok(start > 0 && end > start, 'kit option helper is present');
  const dom = new JSDOM('<body></body>', { runScripts: 'outside-only' });
  const w = dom.window;
  w.$ = w.jQuery = jquery(w);
  w.eval(SCHEDULE.slice(start, end) + '; window.isExtrusionKitOption = isExtrusionKitOption;');
  const $ = w.$;
  assert.equal(w.isExtrusionKitOption($('<option data-is-extrusion-kit-type="1">Kits</option>')), true);
  assert.equal(w.isExtrusionKitOption($('<option data-is-extrusion-kit-type="0">Extrusion Kits</option>')), false);
  assert.equal(w.isExtrusionKitOption($('<option>    └─ Extrusion Kits</option>')), true);
  assert.equal(w.isExtrusionKitOption($('<option>Profiles</option>')), false);
  dom.window.close();
  assert.match(SCHEDULE, /data-is-extrusion-kit-type="' \+ \(pt\.is_extrusion_kit_type \? '1' : '0'\) \+ '"/);
  const add = SCHEDULE.slice(SCHEDULE.indexOf('} else if (isKitType) {\n\t\t\t// Extrusion Kit path'));
  assert.match(add.slice(0, 700), /data\.kit_template = kitTemplate;/);
  const handoff = SCHEDULE.slice(SCHEDULE.indexOf('function configureKitFromAddModal('));
  assert.match(handoff.slice(0, 300), /startConfigurationDraft\('Extrusion Kit', template\)/);
});

test('Power Supplies groups pick a power supply template and hand off to the power supply configurator', () => {
  const start = SCHEDULE.indexOf('function isPowerSupplyOption(');
  const end = SCHEDULE.indexOf('// Load power supply (driver) templates from the server');
  assert.ok(start > 0 && end > start, 'power supply option helper is present');
  const dom = new JSDOM('<body></body>', { runScripts: 'outside-only' });
  const w = dom.window;
  w.$ = w.jQuery = jquery(w);
  w.eval(SCHEDULE.slice(start, end) + '; window.isPowerSupplyOption = isPowerSupplyOption;');
  const $ = w.$;
  assert.equal(w.isPowerSupplyOption($('<option data-is-power-supply-type="1">PSUs</option>')), true);
  assert.equal(w.isPowerSupplyOption($('<option data-is-power-supply-type="0">Power Supplies</option>')), false);
  assert.equal(w.isPowerSupplyOption($('<option>    └─ Power Supplies</option>')), true);
  assert.equal(w.isPowerSupplyOption($('<option>Drivers</option>')), true);
  assert.equal(w.isPowerSupplyOption($('<option>Profiles</option>')), false);
  dom.window.close();
  assert.match(SCHEDULE, /data-is-power-supply-type="' \+ \(pt\.is_power_supply_type \? '1' : '0'\) \+ '"/);
  const add = SCHEDULE.slice(SCHEDULE.indexOf('} else if (isPowerSupplyType) {\n\t\t\t// Power supply path'));
  assert.match(add.slice(0, 800), /data\.manufacturer_type = 'ACCESSORY';[\s\S]*data\.driver_template = driverTemplate;/);
  const handoff = SCHEDULE.slice(SCHEDULE.indexOf('function configureDriverFromAddModal('));
  assert.match(handoff.slice(0, 300), /startConfigurationDraft\('Driver', template\)/);
  // Schedule lines link to the power supply configurator: Configure until configured, then Edit Config.
  assert.match(SCHEDULE, /href="\/portal\/configure\?category=Driver&amp;schedule=\{\{ schedule\.name \| urlencode \}\}&amp;line_key=/);
});
