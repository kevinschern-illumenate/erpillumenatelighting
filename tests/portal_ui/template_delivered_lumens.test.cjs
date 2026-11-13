// Delivered Lumens on the fixture template: only the template's lens columns show (owner, 2026-11-13).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const code = fs.readFileSync(path.join(__dirname, '../../illumenate_lighting/public/js/template_delivered_lumens.js'), 'utf8');

test('lens columns without values are hidden, the others shown', () => {
  const handlers = {}, props = {};
  let refreshed = 0;
  const context = { frappe: { ui: { form: { on: (name, events) => { handlers[name] = events; } } } } };
  context.window = context;
  vm.runInNewContext(code, context);
  const grid = {
    update_docfield_property(field, prop, value) { props[`${field}.${prop}`] = value; },
    refresh() { refreshed += 1; },
  };
  const frm = {
    fields_dict: { delivered_lumens: { grid } },
    doc: { delivered_lumens: [{ output_level: '100 lm/ft', white: '112' }, { output_level: '750 lm/ft', white: '—' }] },
  };
  handlers['ilL-Fixture-Template'].refresh(frm);
  assert.equal(props['white.in_list_view'], 1);
  assert.equal(props['white.hidden'], 0);
  for (const lens of ['frosted', 'clear', 'black']) {
    assert.equal(props[`${lens}.in_list_view`], 0);
    assert.equal(props[`${lens}.hidden`], 1);
  }
  assert.equal(refreshed, 1);
});
