// The email composer picks the purchasing mailbox as From on purchasing documents
// (public/js/desk/purchasing_sender.js, email_templates/purchasing_mail.py).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const SOURCE = fs.readFileSync(
  path.join(__dirname, '../../illumenate_lighting/public/js/desk/purchasing_sender.js'),
  'utf8',
);
const MAILBOX = 'purchasing@illumenate.lighting';

// Frappe v16's composer, cut down to the parts the patch relies on: get_fields() preselects the
// buyer's own address when it is one of their accounts, and set_content() reads the signature
// of the account it is given (the default outgoing one when given nothing).
class CoreComposer {
  constructor(opts) {
    Object.assign(this, opts);
    if (!this.doc) this.doc = (this.frm && this.frm.doc) || {};
    this.make();
  }

  make() {
    this.fields = this.get_fields();
    this.dialog_sender = this.sender || '';
    this.set_content();
  }

  get_fields() {
    this.user_email_accounts = this.accounts;
    if (this.user_email_accounts.includes(this.session_email)) this.sender = this.session_email;
    return ['sender', 'recipients'];
  }

  set_content(sender_email) {
    this.signature_from = sender_email || 'default outgoing';
  }
}

function load({ boot, ready = true } = {}) {
  const handlers = {};
  const frappe = { boot: boot === undefined ? { ill_purchasing_mail: { email: MAILBOX, doctypes: ['Purchase Order', 'Supplier'], payment_entry: 'Payment Entry' } } : boot };
  if (ready) frappe.views = { CommunicationComposer: CoreComposer };
  const context = {
    frappe,
    document: {},
    $: () => ({ on(event, fn) { handlers[event] = fn; } }),
  };
  context.window = context;
  vm.runInNewContext(SOURCE, context);
  return { context, frappe, handlers };
}

const compose = (frappe, doc, accounts = ['reigine@illumenate.lighting', MAILBOX]) =>
  new frappe.views.CommunicationComposer({ doc, accounts, session_email: 'reigine@illumenate.lighting' });

test('a purchasing document picks the mailbox over the buyer\'s own account', () => {
  const { frappe } = load();
  const composer = compose(frappe, { doctype: 'Purchase Order', name: 'PUR-ORD-2026-00059' });
  assert.equal(composer.dialog_sender, MAILBOX);
  assert.equal(composer.signature_from, MAILBOX);
});

test('a supplier payment counts, a customer payment and a sales document do not', () => {
  const { frappe } = load();
  assert.equal(compose(frappe, { doctype: 'Payment Entry', party_type: 'Supplier' }).dialog_sender, MAILBOX);
  const customer = compose(frappe, { doctype: 'Payment Entry', party_type: 'Customer' });
  assert.equal(customer.dialog_sender, 'reigine@illumenate.lighting');
  assert.equal(customer.signature_from, 'default outgoing');
  assert.equal(compose(frappe, { doctype: 'Sales Order' }).dialog_sender, 'reigine@illumenate.lighting');
});

test('the mailbox is only picked when it is in the buyer\'s From list', () => {
  const { frappe } = load();
  const composer = compose(frappe, { doctype: 'Purchase Order' }, ['reigine@illumenate.lighting']);
  assert.equal(composer.dialog_sender, 'reigine@illumenate.lighting');
  const mixedCase = compose(frappe, { doctype: 'Supplier' }, ['Purchasing@Illumenate.Lighting']);
  assert.equal(mixedCase.dialog_sender, 'Purchasing@Illumenate.Lighting');
});

test('no mailbox in boot leaves the composer as Frappe made it', () => {
  const { frappe } = load({ boot: {} });
  assert.equal(compose(frappe, { doctype: 'Purchase Order' }).dialog_sender, 'reigine@illumenate.lighting');
});

test('the patch waits for the desk and is applied once', () => {
  const { context, frappe, handlers } = load({ ready: false });
  assert.equal(typeof handlers.app_ready, 'function');
  frappe.views = { CommunicationComposer: CoreComposer };
  handlers.app_ready();
  const patched = frappe.views.CommunicationComposer;
  assert.notEqual(patched, CoreComposer);
  context.illPurchasingSender.patch();
  assert.equal(frappe.views.CommunicationComposer, patched);
  assert.equal(compose(frappe, { doctype: 'Purchase Order' }).dialog_sender, MAILBOX);
});
