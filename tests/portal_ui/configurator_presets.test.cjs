// Saved configuration presets (plan 3.6): the configurator's "Save as preset" control.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const jquery = require('jquery');

const marker = options => '<script type="application/json" id="ill-config-presets">' + JSON.stringify({ enabled: true, ...options }) + '</script>';
const FORM = '<div id="host"><input id="length" value="10"></div>';

function setup(html) {
  const dom = new JSDOM('<body>' + html + '</body>', { runScripts: 'outside-only', url: 'https://portal.test/portal/configure' });
  const w = dom.window;
  const requests = [];
  w.$ = w.jQuery = jquery(w);
  w.__ = value => value;
  w.frappe = { call: args => requests.push(args), msgprint() {}, show_alert() {} };
  for (const file of ['shared_configurator', 'presets']) {
    w.eval(fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/public/js/configurator', file + '.js'), 'utf8'));
  }
  return { dom, w, $: w.$, requests, api: w.IllConfigurator };
}

const tick = (ms = 0) => new Promise(resolve => setTimeout(resolve, ms));

async function mount(env, request = { family: 'Linear Fixture', template: 'FT-1', selections: { finish_code: 'Black' } }) {
  const inst = new env.api.Base(env.$('#host'), { schedule_name: 'SCH-1' });
  inst.exportRequest = () => request;
  await tick();
  return inst;
}

test('the control attaches only with the page marker', async () => {
  const env = setup(FORM);
  const inst = await mount(env);
  assert.equal(inst._presetSaver, undefined);
  assert.equal(env.$('.ill-preset-save').length, 0);
  env.dom.window.close();
});

test('saves the exported request under a label, shared on request', async () => {
  const env = setup(marker({ can_share: true }) + FORM);
  const inst = await mount(env);
  assert.ok(inst._presetSaver);
  const $ = env.$;
  assert.ok($('.ill-preset-form').hasClass('d-none'));
  $('.ill-preset-toggle').trigger('click');
  assert.equal($('.ill-preset-toggle').attr('aria-expanded'), 'true');
  $('.ill-preset-form').trigger('submit');
  assert.equal($('.ill-preset-status').text(), 'Name the preset.');
  assert.equal(env.requests.length, 0);
  $('.ill-preset-label').val('  <b>Lobby</b> ');
  $('.ill-preset-share').prop('checked', true);
  $('.ill-preset-form').trigger('submit');
  const call = env.requests.shift();
  assert.match(call.method, /portal\.presets\.save_preset$/);
  assert.equal(call.type, 'POST');
  assert.equal(call.args.label, '<b>Lobby</b>');
  assert.equal(call.args.shared_with_company, 1);
  assert.equal(call.args.schedule_name, 'SCH-1');
  assert.deepEqual(JSON.parse(call.args.request), { family: 'Linear Fixture', template: 'FT-1', selections: { finish_code: 'Black' } });
  assert.equal($('.ill-preset-form button[type=submit]').prop('disabled'), true);
  call.callback({ message: { success: true, preset: { name: 'P1', label: '<b>Lobby</b>' } } });
  call.always();
  assert.equal($('.ill-preset-status').text(), 'Saved preset <b>Lobby</b>.');
  assert.equal($('.ill-preset-status b').length, 0, 'labels are never parsed as HTML');
  assert.ok($('.ill-preset-form').hasClass('d-none'));
  assert.equal($('.ill-preset-form button[type=submit]').prop('disabled'), false);
  env.dom.window.close();
});

test('no share box without company sharing, and nothing to save before a product is chosen', async () => {
  const env = setup(marker({ can_share: false }) + FORM);
  await mount(env, { family: '' });
  const $ = env.$;
  assert.equal($('.ill-preset-share').length, 0);
  $('.ill-preset-label').val('Cove');
  $('.ill-preset-form').trigger('submit');
  assert.equal($('.ill-preset-status').text(), 'Choose a product before saving a preset.');
  assert.equal(env.requests.length, 0);
  env.dom.window.close();
});

test('a server-side kill switch hides the control; failures are reported', async () => {
  const env = setup(marker({}) + FORM);
  await mount(env);
  const $ = env.$;
  $('.ill-preset-label').val('Cove');
  $('.ill-preset-form').trigger('submit');
  let call = env.requests.shift();
  assert.equal(call.args.shared_with_company, 0);
  call.error({});
  call.always();
  assert.equal($('.ill-preset-status').text(), 'Could not save the preset.');
  $('.ill-preset-form').trigger('submit');
  call = env.requests.shift();
  call.callback({ message: { success: false, disabled: true } });
  assert.ok($('.ill-preset-save').hasClass('d-none'));
  env.dom.window.close();
});
