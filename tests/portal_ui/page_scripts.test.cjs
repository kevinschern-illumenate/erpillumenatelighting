// Plan 2.2: the edit fixture and tape/neon configurator page scripts are static classic scripts that
// read their server values from a JSON context block instead of inline Jinja.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '../..');
const PAGES = path.join(ROOT, 'illumenate_lighting/templates/pages');
const JS = path.join(ROOT, 'illumenate_lighting/public/js/portal');
const EDIT_HTML = fs.readFileSync(path.join(PAGES, 'edit_fixture.html'), 'utf8');
const EDIT_JS = fs.readFileSync(path.join(JS, 'edit_fixture/page.js'), 'utf8');
const TAPE_HTML = fs.readFileSync(path.join(PAGES, 'configure_tape.html'), 'utf8');
const TAPE_JS = fs.readFileSync(path.join(JS, 'configure_tape/page.js'), 'utf8');

function dom(id, context) {
  const { JSDOM } = require('jsdom');
  const json = JSON.stringify(context).replace(/</g, '\\u003c');
  const page = new JSDOM(
    `<body><div class="ill-configurator ill-configurator-tape-neon"></div>
    <script type="application/json" id="${id}">${json}</script></body>`,
    { runScripts: 'outside-only' },
  );
  const w = page.window;
  w.$ = w.jQuery = require('jquery')(w);
  return w;
}

test('the templates keep no inline page script and load the static scripts with a version', () => {
  for (const source of [EDIT_HTML, TAPE_HTML]) {
    assert.equal((source.match(/<script>/g) || []).length, 0, 'no inline <script> blocks remain');
  }
  assert.match(EDIT_HTML, /<script type="application\/json" id="edit-fixture-context">/);
  assert.match(EDIT_HTML, /<script src="\{\{ edit_fixture_js \| e \}\}page\.js\?v=\{\{ edit_fixture_js_version \| e \}\}"><\/script>/);
  assert.match(TAPE_HTML, /<script type="application\/json" id="configure-tape-context">/);
  assert.match(TAPE_HTML, /js\/portal\/configure_tape\/page\.js\?v=\{\{ configure_tape_js_version \| e \}\}/);
  assert.doesNotMatch(EDIT_JS + TAPE_JS, /\{\{|\{%/, 'static scripts carry no Jinja');
});

test('every edit fixture string has a server translation in the context block', () => {
  const calls = new Set([...EDIT_JS.matchAll(/editFixtureText\("([^"]+)"\)/g)].map(m => m[1]));
  const block = EDIT_HTML.match(/id="edit-fixture-context">([\s\S]*?)<\/script>/)[1];
  const keys = new Set([...block.matchAll(/"([^"]+)": _\("([^"]+)"\)/g)].map(m => (assert.equal(m[1], m[2]), m[1])));
  assert.ok(calls.size > 0);
  assert.deepEqual([...keys].sort(), [...calls].sort());
});

test('configure_tape renders the shared tape/neon form instead of its own copy', () => {
  assert.match(TAPE_HTML, /\{% include "templates\/includes\/configurator_tape_neon_form\.html" %\}/);
  assert.doesNotMatch(TAPE_HTML, /id="tapeConfigForm"/);
});

test('the edit fixture script reads its context and defines the globals the markup calls', () => {
  const w = dom('edit-fixture-context', {
    schedule_name: 'S-1',
    line_idx: 2,
    configured_fixture_id: 'CF-1',
    fixture_config: { fixture_template_code: 'T<1>' },
    i18n: { Run: 'Passage' },
  });
  w.frappe = { call() {}, msgprint() {}, show_alert() {} };
  w.eval(EDIT_JS);
  assert.equal(w.eval('schedule_name'), 'S-1');
  assert.equal(w.eval('line_idx'), 2);
  assert.equal(w.eval('configured_fixture_id'), 'CF-1');
  assert.equal(w.eval('JSON.stringify(existingConfig)'), '{"fixture_template_code":"T<1>"}');
  for (const name of ['validateAndQuote', 'updateFixture', 'removeSegment', 'setEndType', 'copyToClipboard', 'copyBothToClipboard']) {
    assert.equal(typeof w[name], 'function', name);
  }
  assert.equal(w.editFixtureText('Run'), 'Passage');
  assert.equal(w.editFixtureText('Watts'), 'Watts');
  assert.equal(w.editFixtureText('constructor'), 'constructor');
});

test('the tape/neon boot passes the context to the scoped configurator', async () => {
  const w = dom('configure-tape-context', {
    product_category: 'LED Neon', is_neon: true, schedule_name: 'S-1', project_name: 'P-1', line_idx: null, can_save: true,
  });
  const seen = {};
  w.IllConfigurator = {
    TapeNeon: function (root, options) { seen.root = root; seen.options = JSON.parse(JSON.stringify(options)); this.init = () => { seen.init = true; }; },
    registerDefaultTapeNeon(inst) { seen.registered = inst; },
  };
  w.eval(TAPE_JS);
  await new Promise(resolve => w.$(resolve));
  assert.equal(seen.root, w.document.querySelector('.ill-configurator-tape-neon'));
  assert.deepEqual(seen.options, {
    product_category: 'LED Neon', is_neon: true, schedule_name: 'S-1', project_name: 'P-1', line_idx: null, can_save: true,
  });
  assert.ok(seen.registered && seen.init);
});
