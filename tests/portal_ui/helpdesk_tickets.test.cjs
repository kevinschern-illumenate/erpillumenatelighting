const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const script = fs.readFileSync(
  path.join(__dirname, '../../illumenate_lighting/public/js/helpdesk_tickets.js'),
  'utf8',
);

// Loads helpdesk_tickets.js with fake Desk globals and returns the registered form handlers.
function load(versions, dialogs = []) {
  const handlers = {};
  class MultiSelectDialog {
    constructor(options) {
      this.options = options;
      dialogs.push(this);
    }
  }
  vm.runInNewContext(script, {
    __: value => value,
    console,
    frappe: {
      boot: { versions },
      ui: {
        form: {
          MultiSelectDialog,
          on(doctype, callbacks) {
            handlers[doctype] = callbacks;
          },
        },
      },
      call() {},
      msgprint() {},
      show_alert() {},
    },
  });
  return handlers;
}

function form(doctype, name, buttons) {
  return {
    doctype,
    doc: { name },
    is_new: () => false,
    add_custom_button(label, fn) {
      buttons[label] = fn;
    },
    reload_doc() {},
  };
}

const CASES = [
  ['ilL-Project', 'ill_project', 'PRJ-0001'],
  ['ilL-Project-Fixture-Schedule', 'ill_fixture_schedule', 'SCH-0001'],
  ['Quotation', 'ill_quotation', 'QTN-0001'],
  ['Sales Order', 'ill_sales_order', 'SO-0001'],
  ['Sales Invoice', 'ill_sales_invoice', 'SINV-0001'],
];

for (const [doctype, fieldname, name] of CASES) {
  test(`${doctype}: the ticket picker filter is a dict keyed by ${fieldname}`, () => {
    const dialogs = [];
    const buttons = {};
    const handlers = load({ helpdesk: '1.0.0' }, dialogs);
    handlers[doctype].refresh(form(doctype, name, buttons));
    buttons['Link Helpdesk Tickets']();
    assert.equal(dialogs.length, 1);
    assert.equal(dialogs[0].options.doctype, 'HD Ticket');
    const { filters } = dialogs[0].options.get_query();
    // MultiSelectDialog reads filters as a dict; a list of lists becomes "HD Ticket.0".
    assert.equal(Array.isArray(filters), false);
    assert.equal(Object.prototype.toString.call(filters), '[object Object]');
    assert.deepEqual(Object.keys(filters), [fieldname]);
    assert.deepEqual(Array.from(filters[fieldname]), ['!=', name]);
  });
}

test('the button is not added when Helpdesk is not installed', () => {
  const buttons = {};
  const handlers = load({});
  handlers['ilL-Project'].refresh(form('ilL-Project', 'PRJ-0001', buttons));
  assert.deepEqual(Object.keys(buttons), []);
});
