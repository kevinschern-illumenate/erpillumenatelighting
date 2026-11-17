// Durable configurator drafts (plan 3.1): DOM/service-boundary tests.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { JSDOM } = require('jsdom');
const jquery = require('jquery');

const MARKER = '<script type="application/json" id="ill-draft-autosave">{"enabled": true, "product_type": "Fixture"}</script>';
const FORM = '<div id="host"><select id="projectSelect"><option>P</option></select><input id="length" value="10"></div>';

function setup(html, query = '') {
  const dom = new JSDOM('<body>' + html + '</body>', { runScripts: 'outside-only', url: 'https://portal.test/portal/configure' + query });
  const w = dom.window;
  const requests = [];
  const fetches = [];
  const navigations = [];
  w.$ = w.jQuery = jquery(w);
  w.__ = value => value;
  if (!(w.crypto && w.crypto.randomUUID)) Object.defineProperty(w, 'crypto', { value: { randomUUID: () => require('node:crypto').randomUUID() }, configurable: true });
  w.frappe = { call: args => requests.push(args), msgprint() {}, show_alert() {}, csrf_token: 'tok' };
  w.fetch = (url, options) => { fetches.push({ url, options }); return Promise.resolve({}); };
  for (const file of ['shared_configurator', 'draft_autosave']) {
    w.eval(fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/public/js/configurator', file + '.js'), 'utf8'));
  }
  w.IllConfigurator.DraftAutosave.debounceMs = 5;
  w.IllConfigurator.DraftAutosave.navigate = href => navigations.push(href);
  return { dom, w, $: w.$, requests, fetches, navigations, api: w.IllConfigurator };
}

const tick = (ms = 0) => new Promise(resolve => setTimeout(resolve, ms));

async function mount(env, context = { schedule_name: 'SCH-1', line_key: 'line-1' }) {
  const inst = new env.api.Base(env.$('#host'), context);
  inst.exportRequest = () => ({ family: 'Fixture', template: 'TPL-1', length_mm: 10 });
  await tick();
  return inst;
}

function userInput(env, selector) {
  const node = env.$('#host').find(selector)[0];
  assert.ok(node, `no element for ${selector}`);
  node.dispatchEvent(new env.w.Event('input', { bubbles: true }));
}

test('autosave does not attach without the page marker or a schedule', async () => {
  let env = setup(FORM);
  let inst = await mount(env);
  assert.equal(inst._draftAutosave, undefined);
  assert.equal(env.requests.length, 0);
  env.dom.window.close();
  env = setup(MARKER + FORM);
  inst = await mount(env, {});
  assert.ok(!inst._draftAutosave);
  env.dom.window.close();
});

test('offers a server draft and debounces user edits into save_draft', async () => {
  const env = setup(MARKER + FORM);
  const inst = await mount(env);
  assert.ok(inst._draftAutosave);
  const get = env.requests.shift();
  assert.match(get.method, /line_drafts\.get_draft$/);
  assert.deepEqual({ ...get.args }, { schedule_name: 'SCH-1', product_type: 'Fixture', line_key: 'line-1' });
  get.callback({ message: { success: true, draft: null } });

  userInput(env, '[data-ill-original-id="projectSelect"]');
  await tick(20);
  assert.equal(env.requests.length, 0, 'project/schedule pickers are not draft edits');
  env.$('#host').find('input').trigger('input');
  await tick(20);
  assert.equal(env.requests.length, 0, 'programmatic changes are not draft edits');

  userInput(env, 'input');
  userInput(env, 'input');
  assert.equal(env.$('.ill-draft-status').attr('data-state'), 'unsaved');
  await tick(20);
  assert.equal(env.requests.length, 1, 'debounced to one save');
  const save = env.requests.shift();
  assert.match(save.method, /line_drafts\.save_draft$/);
  assert.equal(save.type, 'POST');
  assert.deepEqual(JSON.parse(save.args.draft), { request: { family: 'Fixture', template: 'TPL-1', length_mm: 10 }, metadata: {} });
  save.callback({ message: { success: true, saved_on: '2026-11-03 10:00:00' } });
  save.always();
  assert.equal(env.$('.ill-draft-status').attr('data-state'), 'saved');
  env.dom.window.close();
});

test('failed saves fall back to sessionStorage', async () => {
  const env = setup(MARKER + FORM);
  await mount(env);
  env.requests.shift().callback({ message: {} });
  userInput(env, 'input');
  await tick(20);
  const save = env.requests.shift();
  save.error();
  save.always();
  assert.equal(env.$('.ill-draft-status').attr('data-state'), 'local');
  const local = JSON.parse(env.w.sessionStorage.getItem('ill-config-draft:SCH-1|line-1|Fixture'));
  assert.equal(local.draft.request.template, 'TPL-1');
  env.dom.window.close();
});

test('restore prompt escapes content and reuses the resume path', async () => {
  const env = setup(MARKER + FORM);
  await mount(env);
  env.requests.shift().callback({ message: { success: true, saved_on: '<img src=x onerror=alert(1)>', draft: { request: { template: 'TPL-9' }, metadata: { line_id: 'A1' } } } });
  const $prompt = env.$('.ill-draft-prompt');
  assert.equal($prompt.hasClass('d-none'), false);
  assert.equal($prompt.find('img').length, 0);
  assert.match($prompt.text(), /<img src=x/);
  $prompt.find('.ill-draft-restore').trigger('click');
  assert.equal(env.navigations.length, 1);
  const url = new URL(env.navigations[0]);
  const view = JSON.parse(env.w.sessionStorage.getItem('ill-config-view:' + url.searchParams.get('resume')));
  assert.deepEqual(view.request, { template: 'TPL-9' });
  assert.equal(view.schedule, 'SCH-1');
  assert.equal(view.expected_modified, null);
  const meta = JSON.parse(env.w.sessionStorage.getItem('ill-line-draft:' + url.searchParams.get('draft')));
  assert.deepEqual(meta.metadata, { line_id: 'A1' });
  assert.equal(url.searchParams.get('template'), 'TPL-9');
  env.dom.window.close();
});

test('a resumed page does not prompt again', async () => {
  const env = setup(MARKER + FORM, '?resume=abc');
  const inst = await mount(env);
  assert.ok(inst._draftAutosave);
  assert.equal(env.requests.length, 0);
  env.dom.window.close();
});

test('saving the line discards the draft with a keepalive request and stops autosave', async () => {
  const env = setup(MARKER + FORM);
  const inst = await mount(env);
  env.requests.shift().callback({ message: {} });
  userInput(env, 'input');
  inst._draftAutosave.discard(true);
  await tick(20);
  assert.equal(env.requests.length, 0, 'pending autosave cancelled');
  assert.equal(env.fetches.length, 1);
  assert.match(env.fetches[0].url, /line_drafts\.discard_draft$/);
  assert.equal(env.fetches[0].options.keepalive, true);
  assert.equal(env.fetches[0].options.headers['X-Frappe-CSRF-Token'], 'tok');
  assert.deepEqual(JSON.parse(env.fetches[0].options.body), { schedule_name: 'SCH-1', product_type: 'Fixture', line_key: 'line-1' });
  userInput(env, 'input');
  await tick(20);
  assert.equal(env.requests.length, 0);
  env.dom.window.close();
});

test('an in-flight save is followed by another discard once the line is saved', async () => {
  const env = setup(MARKER + FORM);
  const inst = await mount(env);
  env.requests.shift().callback({ message: {} });
  userInput(env, 'input');
  await tick(20);
  const save = env.requests.shift();
  inst._draftAutosave.discard(true);
  save.callback({ message: { success: true } });
  save.always();
  assert.equal(env.fetches.length, 2);
  env.dom.window.close();
});

test('the kill switch response removes the autosave UI', async () => {
  const env = setup(MARKER + FORM);
  const inst = await mount(env);
  env.requests.shift().callback({ message: {} });
  userInput(env, 'input');
  await tick(20);
  const save = env.requests.shift();
  save.callback({ message: { success: false, disabled: true } });
  save.always();
  assert.equal(env.$('.ill-draft-status').length, 0);
  assert.equal(inst._draftAutosave, null);
  userInput(env, 'input');
  await tick(20);
  assert.equal(env.requests.length, 0);
  env.dom.window.close();
});
