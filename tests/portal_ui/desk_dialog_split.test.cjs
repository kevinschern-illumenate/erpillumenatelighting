// Plan 7.5: desk_dialog.js was split verbatim into desk/dialog/*.js. The bundle loads them in order and
// the public IllDesk API and the controller's methods are unchanged.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const JS = path.join(__dirname, '../../illumenate_lighting/public/js');
const PARTS = ['state', 'family_steps', 'pricing', 'save'];
const source = part => fs.readFileSync(path.join(JS, 'desk/dialog', `${part}.js`), 'utf8');

function load() {
  const context = { __: value => value };
  context.window = context;
  PARTS.forEach(part => vm.runInNewContext(source(part), context));
  return context;
}

test('the Desk bundle loads the dialog parts in order and the old file is gone', () => {
  const bundle = fs.readFileSync(path.join(JS, 'illumenate_desk.bundle.js'), 'utf8');
  const positions = PARTS.map(part => bundle.indexOf(`import "./desk/dialog/${part}.js";`));
  assert.ok(positions.every(position => position >= 0), positions.join());
  assert.deepEqual([...positions].sort((a, b) => a - b), positions);
  assert.equal(fs.existsSync(path.join(JS, 'desk/desk_dialog.js')), false);
  assert.doesNotMatch(bundle, /desk_dialog\.js/);
});

test('the public API and every controller step survive the split', () => {
  const { IllDesk } = load();
  for (const name of ['addConfiguratorButton', 'openConfiguratorDialog', 'reconfigureSelectedRow']) {
    assert.equal(typeof IllDesk[name], 'function', name);
  }
  const proto = IllDesk._dialog.DialogController.prototype;
  for (const name of [
    'start', 'call', 'renderProjectStep', 'advanceFromProject', 'renderLineStep', 'advanceFromLine',
    'renderConfigureStep', 'mountConfigurator', 'mountCatalogConfigurator', 'teardownConfigurator',
    'onConfiguratorSave', 'applyRowToForm', 'renderDone',
  ]) {
    assert.equal(typeof proto[name], 'function', name);
  }
  assert.equal(IllDesk._dialog.DESK_API, 'illumenate_lighting.illumenate_lighting.api.desk_configurator.');
});

test('each later part reads the shared helpers from state.js instead of redefining them', () => {
  for (const part of PARTS.slice(1)) {
    const text = source(part);
    assert.match(text, /var D = IllDesk\._dialog;/);
    assert.doesNotMatch(text, /\n\tfunction \w+\(/, `${part} defines no top-level helpers`);
  }
});
