// Plan 3.7: "Recently used" product cards in the schedule's Add Line dialog.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { JSDOM } = require('jsdom');
const jquery = require('jquery');
const { TEMPLATE, read } = require('./schedule_source.cjs');

const CONTEXT = { schedule_name: 'S-1', recent_products: true, lines: [], i18n: {} };
const PRODUCTS = [
  { family: 'fixture', doctype: 'ilL-Fixture-Template', name: 'FT-1', template_code: 'ILL-FT1', template_name: '<img src=x onerror=alert(1)>', category: '', image: '/files/ft1.jpg', image_alt: 'FT hero' },
  { family: 'tape_neon', doctype: 'ilL-Tape-Neon-Template', name: 'TN-1', template_code: 'TN1', template_name: 'Neon One', category: 'LED Neon', image: '', image_alt: '' },
  { family: 'driver', doctype: 'ilL-Driver-Template', name: 'DRV-GONE', template_code: 'DRV', template_name: 'Old driver', category: '', image: '', image_alt: '' },
];
const CATEGORIES = `<option value="">Select</option>
  <option value="Linear Fixtures" data-is-fixture-type="1" data-is-tape-neon-type="0" data-tape-neon-category="" data-is-power-supply-type="0">Linear</option>
  <option value="LED Tape Group" data-is-fixture-type="0" data-is-tape-neon-type="1" data-tape-neon-category="LED Tape" data-is-power-supply-type="0">Tape</option>
  <option value="Neon Group" data-is-fixture-type="0" data-is-tape-neon-type="1" data-tape-neon-category="LED Neon" data-is-power-supply-type="0">Neon</option>
  <option value="Power Supplies" data-is-fixture-type="0" data-is-tape-neon-type="0" data-tape-neon-category="" data-is-power-supply-type="1">PSU</option>`;
const TEMPLATES = {
  'Linear Fixtures': ['#add_fixture_template', ['FT-1', 'FT-2']],
  'Neon Group': ['#add_tape_neon_template', ['TN-1']],
  'Power Supplies': ['#add_driver_template', ['DRV-1']],
};

function page(context = CONTEXT) {
  const json = JSON.stringify(context).replace(/</g, '\\u003c');
  const dom = new JSDOM(
    `<body><div id="addLineModal"><form id="addLineForm">
      <select name="manufacturer_type"><option value="ILLUMENATE">ilL</option><option value="OTHER">Other</option></select>
      <div class="form-group ill-add-recent d-none"><div id="addLineRecentList"></div><small id="addLineRecentResult"></small></div>
      <select id="add_product_type"><option value="">Select</option></select>
      <select id="add_fixture_template"></select><select id="add_tape_neon_template"></select>
      <select id="add_led_sheet_template"></select><select id="add_kit_template"></select><select id="add_driver_template"></select>
    </form></div>
    <script type="application/json" id="schedule-context">${json}</script></body>`,
    { runScripts: 'outside-only', url: 'https://portal.test/portal/schedules/S-1' },
  );
  const w = dom.window;
  const requests = [];
  w.$ = w.jQuery = jquery(w);
  w.__ = text => text;
  w.frappe = { call: args => requests.push(args) };
  w.eval(read('context') + '\nvar schedule_name = scheduleContext.schedule_name;\n' + read('recent'));
  const $ = w.$;
  const chosen = [];
  // Stand-in for lines.js: a category change empties the picker, then fills it after a server round trip.
  $('#add_product_type').on('change', function () {
    const entry = TEMPLATES[this.value];
    if (!entry) return;
    $(entry[0]).html('<option value="">Loading...</option>');
    setTimeout(() => $(entry[0]).html('<option value="">Select</option>' + entry[1].map(n => `<option value="${n}">${n}</option>`).join('')), 5);
  });
  ['#add_fixture_template', '#add_tape_neon_template', '#add_driver_template'].forEach(sel => {
    $(sel).on('change', function () { chosen.push([sel, this.value]); });
  });
  return { dom, w, $, requests, chosen };
}

function opened(env, products = PRODUCTS) {
  env.$('#addLineModal').trigger('show.bs.modal');
  const call = env.requests.shift();
  assert.match(call.method, /portal\.recent_products\.recent_products$/);
  assert.equal(call.type, 'GET');
  assert.deepEqual({ ...call.args }, { schedule_name: 'S-1' });
  call.callback({ message: { success: true, products } });
}

const settle = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(check, ms = 500) {
  const end = Date.now() + ms;
  while (!check() && Date.now() < end) await settle(5);
}

test('the template gates the cards and loads recent.js', () => {
  assert.match(TEMPLATE, /\{% if recent_products_enabled \| default\(false\) %\}\s*<div class="form-group ill-add-recent d-none">/);
  assert.match(TEMPLATE, /"recent_products": \(recent_products_enabled \| default\(false\)\)/);
  assert.match(TEMPLATE, /"presets", "recent"[\],]/);
});

test('cards show the hero image, family and text-only names', () => {
  const env = page();
  assert.ok(env.$('.ill-add-recent').hasClass('d-none'), 'hidden until there is something to show');
  opened(env);
  assert.ok(!env.$('.ill-add-recent').hasClass('d-none'));
  const cards = env.$('#addLineRecentList .ill-recent-card');
  assert.equal(cards.length, 3);
  const img = cards.eq(0).find('img')[0];
  assert.equal(img.getAttribute('src'), '/files/ft1.jpg');
  assert.equal(img.getAttribute('alt'), 'FT hero');
  assert.equal(cards.eq(0).find('.ill-recent-card-name').text(), PRODUCTS[0].template_name);
  assert.equal(env.$('#addLineRecentList img').length, 1, 'names are never parsed as HTML');
  assert.equal(cards.eq(0).find('.ill-recent-card-family').text(), 'Linear Fixture');
  assert.equal(cards.eq(1).find('.ill-recent-card-family').text(), 'LED Neon', 'tape/neon show their category');
  assert.equal(cards.eq(1).find('img').length, 0);
  assert.equal(cards.eq(1).find('.fa-lightbulb-o').length, 1, 'placeholder without an image');
  env.dom.window.close();
});

test('an empty or failed list keeps the section hidden', () => {
  const env = page();
  opened(env, []);
  assert.ok(env.$('.ill-add-recent').hasClass('d-none'));
  env.$('#addLineModal').trigger('show.bs.modal');
  env.requests.shift().error();
  assert.ok(env.$('.ill-add-recent').hasClass('d-none'));
  env.dom.window.close();
});

test('choosing a card selects its category, then its template once the picker loads', async () => {
  const env = page();
  opened(env);
  env.$('select[name="manufacturer_type"]').val('OTHER');
  // Categories arrive after the card list, like loadProductCategories.
  setTimeout(() => env.$('#add_product_type').html(CATEGORIES), 5);
  env.$('#addLineRecentList .ill-recent-card').eq(1).trigger('click');
  assert.equal(env.$('select[name="manufacturer_type"]').val(), 'ILLUMENATE');
  await until(() => env.chosen.length);
  assert.equal(env.$('#add_product_type').val(), 'Neon Group', 'the category matching the tape/neon family');
  assert.deepEqual(env.chosen, [['#add_tape_neon_template', 'TN-1']]);
  assert.equal(env.$('#addLineRecentResult').text(), 'Neon One selected.');
  env.dom.window.close();
});

test('a template the picker no longer lists is reported, not chosen', async () => {
  const env = page();
  env.w.ScheduleRecent.WAIT_MS = 60;
  opened(env);
  env.$('#add_product_type').html(CATEGORIES);
  env.$('#addLineRecentList .ill-recent-card').eq(2).trigger('click');
  assert.equal(env.$('#add_product_type').val(), 'Power Supplies');
  await until(() => env.$('#addLineRecentResult').hasClass('text-danger'));
  assert.equal(env.$('#addLineRecentResult').text(), 'This product is no longer offered.');
  assert.deepEqual(env.chosen, []);
  env.dom.window.close();
});

test('a family without a matching category is reported', async () => {
  const env = page();
  env.w.ScheduleRecent.WAIT_MS = 30;
  opened(env, [{ ...PRODUCTS[1], category: 'COB Tape' }]);
  env.$('#add_product_type').html(CATEGORIES);
  env.$('#addLineRecentList .ill-recent-card').eq(0).trigger('click');
  await until(() => env.$('#addLineRecentResult').hasClass('text-danger'));
  assert.equal(env.$('#addLineRecentResult').text(), 'This product is not in the Add Line categories.');
  assert.equal(env.$('#add_product_type').val(), '');
  env.dom.window.close();
});

test('closing the dialog cancels a pending choice', async () => {
  const env = page();
  env.w.ScheduleRecent.WAIT_MS = 30;
  opened(env);
  env.$('#addLineRecentList .ill-recent-card').eq(0).trigger('click');
  env.$('#addLineModal').trigger('hide.bs.modal');
  env.$('#add_product_type').html(CATEGORIES);
  await settle(60);
  assert.equal(env.$('#add_product_type').val(), '');
  assert.equal(env.$('#addLineRecentResult').text(), 'Loading...', 'no late error either');
  env.dom.window.close();
});

test('switched off, nothing is requested', () => {
  const env = page({ ...CONTEXT, recent_products: false });
  env.$('#addLineModal').trigger('show.bs.modal');
  assert.equal(env.requests.length, 0);
  env.dom.window.close();
});
