// Plan 7.6: the Desk schedule form's early unconfigured-line warning.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const script = fs.readFileSync(
  path.join(__dirname, '../../illumenate_lighting/illumenate_lighting/doctype/ill_project_fixture_schedule/ill_project_fixture_schedule.js'),
  'utf8',
);
const escapeHtml = value => value.replace(/[&<>"']/g, ch => `&#${ch.charCodeAt(0)};`);
const format = (text, args = []) => text.replace(/\{(\d+)\}/g, (_, i) => args[i]);

function load(doc, { roleInfo = {} } = {}) {
  const events = {}, buttons = {}, messages = [], comments = [];
  const frappe = {
    validated: true,
    ui: { form: { on(doctype, handlers) { events[doctype] = handlers; } } },
    utils: { escape_html: escapeHtml },
    call({ callback }) { callback({ message: roleInfo }); },
    msgprint(message) { messages.push(message); },
    db: { get_value: () => Promise.resolve({ message: null }) },
  };
  vm.runInNewContext(script, { frappe, __: format, locals: {}, console });
  const frm = {
    doc,
    is_new: () => false,
    set_query() {},
    add_custom_button(label, fn, group) { buttons[`${group}/${label}`] = fn; },
    dashboard: { add_comment(html, colour) { comments.push({ html, colour }); }, set_headline_alert() {} },
    // Frappe's trigger is asynchronous; the old code read .length from this Promise.
    trigger(name) { return Promise.resolve(events['ilL-Project-Fixture-Schedule'][name](frm)); },
  };
  return { frappe, frm, events: events['ilL-Project-Fixture-Schedule'], buttons, messages, comments };
}

const lines = [
  { idx: 1, line_id: 'A<b>', manufacturer_type: 'ILLUMENATE' },
  { idx: 2, manufacturer_type: 'ILLUMENATE', product_type: 'LED Tape', variant_selections: '{}' },
  { idx: 3, manufacturer_type: 'ILLUMENATE', product_type: 'LED Sheet' },
  { idx: 4, manufacturer_type: 'OTHER' },
  { idx: 5, manufacturer_type: 'ILLUMENATE', configured_fixture: 'CF-1' },
];

test('READY with unconfigured lines is blocked and the labels are escaped', () => {
  const { frappe, frm, events, messages } = load({ status: 'READY', lines });
  events.validate(frm);
  assert.equal(frappe.validated, false);
  assert.match(messages[0].message, /A&#60;b&#62;, Row 3/);
  assert.doesNotMatch(messages[0].message, /<b>/);
});

test('fully configured schedules may be set to READY', () => {
  const { frappe, frm, events, messages } = load({ status: 'READY', lines: lines.slice(1, 2) });
  events.validate(frm);
  assert.equal(frappe.validated, true);
  assert.equal(messages.length, 0);
});

test('refresh warns about pending lines and adds the expected buttons', () => {
  const { frm, events, buttons, comments } = load({ status: 'QUOTED', lines }, { roleInfo: { is_dealer: true } });
  events.refresh(frm);
  return Promise.resolve().then(() => {
    assert.match(comments[0].html, /2 line\(s\) have pending fixture configuration: A&#60;b&#62;, Row 3/);
    assert.deepEqual(Object.keys(buttons).sort(), ['Actions/Convert to Sales Order', 'Collaborators/Create Website User']);
  });
});

test('draft schedules get no conversion button and non-dealers no user button', () => {
  const { frm, events, buttons } = load({ status: 'DRAFT', lines: [] });
  events.refresh(frm);
  assert.deepEqual(Object.keys(buttons), []);
});
