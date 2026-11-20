"""Purchasing mailbox: supplier email leaves from purchasing@, and new inbound email finds its document."""

import types
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock

from test_purchasing_board import MODULE as BOARD
from test_purchasing_board import SETTINGS as BOARD_SETTINGS
from test_purchasing_board import TODAY, lead_fn, raw_board
from test_services import ROOT, Record, load_service

MODULE = ROOT + ".email_templates.purchasing_mail"
RECIPIENTS = ROOT + ".email_templates.recipients"

MAILBOX = {"name": "Purchasing", "email_id": "purchasing@illumenate.lighting", "enable_outgoing": 1, "enable_incoming": 1}
EMAIL_ACCOUNTS = {
	"Purchasing": MAILBOX,
	"Info": {"name": "Info", "email_id": "info@illumenate.lighting", "enable_outgoing": 1, "enable_incoming": 1},
}
USERS = {"reigine@illumenate.lighting": "Reigine Yray", "admin@example.com": None}


def settings(**overrides):
	values = {
		"purchasing_contact_email": "purchasing@illumenate.lighting",
		"purchasing_email_account": "",
		"force_purchasing_sender": 1,
		"link_purchasing_replies": 1,
	}
	values.update(overrides)
	return values


class Doc(Record):
	"""A Communication or Email Queue: dict fields, attribute writes, timeline links."""

	def __setattr__(self, key, value):
		self[key] = value

	def add_link(self, link_doctype, link_name, autosave=False):
		self.setdefault("links", []).append((link_doctype, link_name))


def fake_get_value(accounts=EMAIL_ACCOUNTS, payments=None, suppliers_of=None):
	payments = payments or {}
	suppliers_of = suppliers_of or {}

	def get_value(doctype, filters, fieldname=None, as_dict=False, **kwargs):
		if doctype == "Email Account":
			if isinstance(filters, dict):
				row = next((a for a in accounts.values() if a["email_id"] == filters.get("email_id")), None)
			else:
				row = accounts.get(filters)
			return Record(row) if row else None
		if doctype == "User":
			email = filters.get("email")
			if email not in USERS:
				return None
			name = "Administrator" if email == "admin@example.com" else email
			return Record(name=name, full_name=USERS[email])
		if doctype == "Payment Entry":
			return payments.get(filters)
		return suppliers_of.get((doctype, filters))

	return get_value


@contextmanager
def mail(values=None, **db):
	stub = types.ModuleType(ROOT + ".email_templates.settings")
	stub.get_settings = lambda: dict(values or settings())
	with load_service(MODULE, {ROOT + ".email_templates.settings": stub}) as (module, frappe):
		frappe.db.get_value.side_effect = fake_get_value(**db)
		frappe.db.exists.side_effect = lambda doctype, name=None, **kw: (
			doctype == "DocType" or (doctype == "Email Account" and name in EMAIL_ACCOUNTS)
		)
		frappe.log_error = MagicMock()
		frappe.get_traceback = MagicMock(return_value="")
		yield module, frappe


QUEUED = (
	"Content-Type: multipart/alternative\n"
	"From: Info <info@illumenate.lighting>\n"
	"Reply-To: info@illumenate.lighting\n"
	"Subject: PO PUR-ORD-2026-00059\n"
	"\n"
	"From: this line is body text and stays\n"
)


class Mailbox(unittest.TestCase):
	def test_named_account_then_purchasing_contact_email_then_nothing(self):
		with mail(settings(purchasing_email_account="Info")) as (module, _):
			self.assertEqual(module.account()["email_id"], "info@illumenate.lighting")
		with mail() as (module, _):
			self.assertEqual(module.account()["name"], "Purchasing")
		with mail(accounts={"Info": EMAIL_ACCOUNTS["Info"]}) as (module, frappe):
			self.assertIsNone(module.account())
			self.assertIsNone(module.sending_account())
			frappe.db.get_value.reset_mock()
			module.account()
			frappe.db.get_value.assert_not_called()  # read once per request

	def test_sending_needs_outgoing_and_the_force_setting(self):
		with mail(settings(force_purchasing_sender=0)) as (module, _):
			self.assertIsNone(module.sending_account())
		off = {"Purchasing": dict(MAILBOX, enable_outgoing=0)}
		with mail(accounts=off) as (module, _):
			self.assertIsNone(module.sending_account())
			self.assertEqual(module.account()["name"], "Purchasing")

	def test_purchasing_documents(self):
		payments = {"PE-SUPP": "Supplier", "PE-CUST": "Customer"}
		with mail(payments=payments) as (module, _):
			for doctype in ("Purchase Order", "Request for Quotation", "Purchase Invoice", "Supplier", "ilL-Inbound-Shipment"):
				self.assertTrue(module.is_purchasing(doctype), doctype)
			self.assertTrue(module.is_purchasing("Payment Entry", "PE-SUPP"))
			self.assertFalse(module.is_purchasing("Payment Entry", "PE-CUST"))
			self.assertFalse(module.is_purchasing("Payment Entry"))
			self.assertFalse(module.is_purchasing("Sales Order", "SO-1"))
			self.assertFalse(module.is_purchasing(None))


class OutgoingCommunication(unittest.TestCase):
	def sent(self, **kw):
		base = {
			"communication_medium": "Email",
			"sent_or_received": "Sent",
			"reference_doctype": "Purchase Order",
			"reference_name": "PUR-ORD-2026-00059",
		}
		base.update(kw)
		return Doc(base)

	def test_a_buyer_sends_from_the_mailbox_under_their_own_name(self):
		with mail() as (module, _):
			doc = self.sent(sender="reigine@illumenate.lighting", sender_full_name="Reigine Yray")
			self.assertTrue(module.use_purchasing_sender(doc))
			self.assertEqual(doc.sender, "purchasing@illumenate.lighting")
			self.assertEqual(doc.sender_full_name, "Reigine Yray")
			self.assertEqual(doc.email_account, "Purchasing")

	def test_name_comes_from_the_user_when_the_composer_gave_none(self):
		with mail() as (module, _):
			doc = self.sent(sender="reigine@illumenate.lighting")  # RFQ "Send Supplier Emails"
			module.use_purchasing_sender(doc)
			self.assertEqual(doc.sender_full_name, "Reigine Yray")

	def test_automatic_mail_carries_the_mailbox_name(self):
		with mail() as (module, _):
			for sender in ("Info <info@illumenate.lighting>", "Administrator <admin@example.com>"):
				doc = self.sent(sender=sender)
				module.use_purchasing_sender(doc)
				self.assertEqual(doc.sender, "purchasing@illumenate.lighting")
				self.assertEqual(doc.sender_full_name, "Purchasing", sender)

	def test_other_mail_is_left_alone(self):
		cases = [
			self.sent(reference_doctype="Sales Order", reference_name="SO-1", sender="sales@illumenate.lighting"),
			self.sent(sent_or_received="Received", sender="vendor@acme.com"),
			self.sent(communication_medium="Phone", sender="reigine@illumenate.lighting"),
		]
		with mail() as (module, _):
			for doc in cases:
				before = dict(doc)
				self.assertFalse(module.use_purchasing_sender(doc))
				self.assertEqual(dict(doc), before)
		with mail(settings(force_purchasing_sender=0)) as (module, _):
			doc = self.sent(sender="reigine@illumenate.lighting")
			self.assertFalse(module.use_purchasing_sender(doc))
			self.assertEqual(doc.sender, "reigine@illumenate.lighting")

	def test_hook_dispatches_and_never_raises(self):
		with mail() as (module, frappe):
			doc = self.sent(sender="reigine@illumenate.lighting")
			module.on_communication_before_insert(doc)
			self.assertEqual(doc.sender, "purchasing@illumenate.lighting")
			frappe.db.get_value.side_effect = RuntimeError("database down")
			frappe.local = types.SimpleNamespace()
			module.on_communication_before_insert(self.sent(sender="reigine@illumenate.lighting"))
			frappe.log_error.assert_called_once()


class OutgoingQueue(unittest.TestCase):
	def queue(self, **kw):
		base = {
			"sender": "Info <info@illumenate.lighting>",
			"email_account": "Info",
			"reference_doctype": "Purchase Order",
			"reference_name": "PUR-ORD-2026-00059",
			"message": QUEUED,
		}
		base.update(kw)
		return Doc(base)

	def test_notification_mail_moves_to_the_mailbox(self):
		with mail() as (module, _):
			queue = self.queue()
			self.assertTrue(module.use_purchasing_account(queue))
			self.assertEqual(queue.email_account, "Purchasing")
			self.assertEqual(queue.sender, "Purchasing <purchasing@illumenate.lighting>")
			head, body = queue.message.split("\n\n", 1)
			self.assertIn("From: Purchasing <purchasing@illumenate.lighting>", head)
			self.assertIn("Reply-To: purchasing@illumenate.lighting", head)
			self.assertNotIn("info@", head)
			self.assertEqual(body, "From: this line is body text and stays\n")

	def test_a_persons_name_is_kept(self):
		with mail() as (module, _):
			queue = self.queue(sender="Reigine Yray <reigine@illumenate.lighting>", email_account="Reigine Yray")
			module.use_purchasing_account(queue)
			self.assertEqual(queue.sender, "Reigine Yray <purchasing@illumenate.lighting>")

	def test_already_from_the_mailbox_or_not_purchasing(self):
		with mail() as (module, _):
			queue = self.queue(sender="Reigine Yray <purchasing@illumenate.lighting>", email_account="Purchasing")
			self.assertFalse(module.use_purchasing_account(queue))
			queue = self.queue(sender="purchasing@illumenate.lighting", email_account=None)
			self.assertTrue(module.use_purchasing_account(queue))
			self.assertEqual(queue.email_account, "Purchasing")
			self.assertEqual(queue.message, QUEUED)  # same address: headers untouched
			queue = self.queue(reference_doctype="Sales Order", reference_name="SO-1")
			self.assertFalse(module.use_purchasing_account(queue))
			self.assertEqual(queue.message, QUEUED)

	def test_queue_override_moves_mail_before_branding(self):
		source = (ROOT.replace(".", "/") + "/portal/email_queue.py")
		with open(source, encoding="utf-8") as handle:
			text = handle.read()
		self.assertLess(text.index("use_purchasing_account(self)"), text.index("rebrand_sender(self)"))


class Incoming(unittest.TestCase):
	def test_document_names_in_order(self):
		with mail() as (module, _):
			tokens = module.name_tokens("Re: PO#PUR-ORD-2026-00059, amended PUR-ORD-2026-00060-1. e-mail ISO-9001 x-ray")
			self.assertEqual(tokens, ["PUR-ORD-2026-00059", "PUR-ORD-2026-00060-1", "ISO-9001"])
			self.assertEqual(module.name_tokens(None), [])

	def test_subject_beats_body_and_live_beats_cancelled(self):
		def get_all(doctype, filters=None, **kw):
			wanted = {t.lower() for t in filters["name"][1]}
			rows = {
				"Purchase Order": [Record(name="PUR-ORD-2026-00059", docstatus=1), Record(name="PUR-ORD-2026-00050", docstatus=2)],
				"Purchase Receipt": [Record(name="MAT-PRE-2026-00007", docstatus=1)],
			}.get(doctype, [])
			return [r for r in rows if r.name.lower() in wanted]

		with mail() as (module, frappe):
			frappe.get_all.side_effect = get_all
			body = "<p>About <b>pur-ord-2026-00059</b> and MAT-PRE-2026-00007</p>"
			self.assertEqual(
				module.find_reference("Shipping update MAT-PRE-2026-00007", body),
				("Purchase Receipt", "MAT-PRE-2026-00007"),
			)
			self.assertEqual(module.find_reference("Shipping update", body), ("Purchase Order", "PUR-ORD-2026-00059"))
			self.assertEqual(
				module.find_reference("PUR-ORD-2026-00050 replaced by PUR-ORD-2026-00059", ""),
				("Purchase Order", "PUR-ORD-2026-00059"),
			)
			self.assertIsNone(module.find_reference("Hello", "<p>No numbers here</p>"))

	def suppliers(self, frappe, contacts=None, links=None):
		frappe.get_meta.return_value.has_field.return_value = True
		rows = {
			"Supplier": [
				Record(name="Acme LED", email_id="sales@acme.com", ill_purchasing_email="orders@acme.com"),
				Record(name="Glow Co", email_id="glowco@gmail.com", ill_purchasing_email=""),
				Record(name="Twin A", email_id="a@twins.com", ill_purchasing_email=""),
				Record(name="Twin B", email_id="b@twins.com", ill_purchasing_email=""),
			],
			"Contact Email": contacts or [],
			"Dynamic Link": links or [],
		}

		def get_all(doctype, filters=None, pluck=None, **kw):
			found = rows.get(doctype, [])
			return [r.link_name for r in found] if pluck else found

		frappe.get_all.side_effect = get_all

	def test_supplier_by_address_then_company_domain(self):
		with mail() as (module, frappe):
			self.suppliers(frappe)
			self.assertEqual(module.supplier_for_address("Orders@Acme.com"), "Acme LED")
			self.assertEqual(module.supplier_for_address("newperson@acme.com"), "Acme LED")
			self.assertEqual(module.supplier_for_address("glowco@gmail.com"), "Glow Co")
			self.assertIsNone(module.supplier_for_address("someone@gmail.com"))  # free mail
			self.assertIsNone(module.supplier_for_address("c@twins.com"))  # two suppliers share it
			self.assertIsNone(module.supplier_for_address("kevin@acme.com", own_domain="acme.com"))
			self.assertIsNone(module.supplier_for_address("not-an-address"))

	def test_supplier_by_a_contacts_domain(self):
		with mail() as (module, frappe):
			self.suppliers(
				frappe,
				contacts=[Record(parent="CONT-1", email_id="ops@brightpaint.com")],
				links=[Record(link_name="Acme LED")],
			)
			self.assertEqual(module.supplier_for_address("billing@brightpaint.com"), "Acme LED")

	def received(self, **kw):
		base = {
			"communication_medium": "Email",
			"sent_or_received": "Received",
			"email_account": "Purchasing",
			"sender": "newperson@acme.com",
			"subject": "Confirmation PUR-ORD-2026-00059",
			"content": "<p>Confirmed</p>",
		}
		base.update(kw)
		return Doc(base)

	def test_new_email_is_linked_to_its_document_and_supplier(self):
		with mail() as (module, frappe):
			self.suppliers(frappe)
			module.find_reference = MagicMock(return_value=("Purchase Order", "PUR-ORD-2026-00059"))
			doc = self.received()
			module.on_communication_before_insert(doc)
			self.assertEqual((doc.reference_doctype, doc.reference_name), ("Purchase Order", "PUR-ORD-2026-00059"))
			self.assertEqual(doc.links, [("Supplier", "Acme LED")])

	def test_a_reply_keeps_its_thread_and_gets_the_documents_supplier(self):
		suppliers_of = {("Purchase Order", "PUR-ORD-2026-00001"): "Glow Co"}
		with mail(suppliers_of=suppliers_of) as (module, frappe):
			self.suppliers(frappe)
			module.find_reference = MagicMock()
			doc = self.received(
				sender="someone@gmail.com", reference_doctype="Purchase Order", reference_name="PUR-ORD-2026-00001"
			)
			self.assertTrue(module.link_inbound(doc))
			module.find_reference.assert_not_called()
			self.assertEqual(doc.reference_name, "PUR-ORD-2026-00001")
			self.assertEqual(doc.links, [("Supplier", "Glow Co")])

	def test_other_inboxes_and_the_setting(self):
		with mail() as (module, _frappe):
			module.find_reference = MagicMock(return_value=("Purchase Order", "PUR-ORD-2026-00059"))
			self.assertFalse(module.link_inbound(self.received(email_account="Sales")))
			self.assertFalse(module.link_inbound(self.received(sent_or_received="Sent")))
			module.find_reference.assert_not_called()
		with mail(settings(link_purchasing_replies=0)) as (module, _frappe):
			module.find_reference = MagicMock()
			doc = self.received()
			self.assertFalse(module.link_inbound(doc))
			self.assertNotIn("reference_name", doc)


class Desk(unittest.TestCase):
	def test_unlinked_count_and_its_list(self):
		with mail() as (module, frappe):
			frappe.db.count.return_value = 3
			found = module.unlinked_mail()
			self.assertEqual(found["count"], 3)
			filters = frappe.db.count.call_args.args[1]
			self.assertEqual(filters["email_account"], "Purchasing")
			self.assertEqual(filters["reference_name"], ["is", "not set"])
			self.assertEqual(filters["status"], "Open")
			self.assertTrue(found["route"].startswith("/app/communication?email_account=Purchasing&"))
			self.assertIn("reference_name=%5B%22is%22%2C%20%22not%20set%22%5D", found["route"])
		incoming_off = {"Purchasing": dict(MAILBOX, enable_incoming=0)}
		with mail(accounts=incoming_off) as (module, _):
			self.assertIsNone(module.unlinked_mail())

	def test_boot_tells_the_composer_only_when_mail_is_forced(self):
		with mail() as (module, frappe):
			frappe.session = Record(user="reigine@illumenate.lighting")
			boot = types.SimpleNamespace()
			module.extend_bootinfo(boot)
			self.assertEqual(boot.ill_purchasing_mail["email"], "purchasing@illumenate.lighting")
			self.assertIn("Purchase Order", boot.ill_purchasing_mail["doctypes"])
			self.assertEqual(boot.ill_purchasing_mail["payment_entry"], "Payment Entry")
		with mail(settings(force_purchasing_sender=0)) as (module, frappe):
			boot = types.SimpleNamespace()
			module.extend_bootinfo(boot)
			self.assertFalse(hasattr(boot, "ill_purchasing_mail"))

	def test_board_decision_opens_the_unlinked_list(self):
		with load_service(BOARD) as (pb, _):
			raw = raw_board()
			raw["mail"] = {"count": 2, "route": "/app/communication?x=1"}
			board = pb.assemble(raw, BOARD_SETTINGS, TODAY, lead_fn, money=True)
			found = [d for d in board["decisions"] if d["id"] == "mail_unlinked"]
			self.assertEqual(found[0]["count"], 2)
			self.assertEqual(found[0]["href"], "/app/communication?x=1")
			self.assertTrue(all("href" not in d for d in board["decisions"] if d["id"] != "mail_unlinked"))
			raw["mail"] = {}
			board = pb.assemble(raw, BOARD_SETTINGS, TODAY, lead_fn, money=False)
			self.assertFalse([d for d in board["decisions"] if d["id"] == "mail_unlinked"])


class SupplierPurchasingEmail(unittest.TestCase):
	def test_pick_order(self):
		with load_service(RECIPIENTS) as (module, _):
			pick = module.pick_purchasing_email
			contacts = {"C-1": [("ops@acme.com", 0), ("buyer@acme.com", 1)], "C-2": [("ap@acme.com", 1)]}
			self.assertEqual(pick(" sales@acme.com ", "C-1", contacts), "sales@acme.com")
			self.assertEqual(pick("", "C-1", contacts), "buyer@acme.com")
			self.assertIsNone(pick("", None, contacts))  # two addresses, no primary contact: a guess
			self.assertEqual(pick("", None, {"C-1": [("Only@acme.com", 0)], "C-2": [("only@acme.com", 1)]}), "Only@acme.com")
			self.assertIsNone(pick("", None, {}))

	def test_backfill_fills_blanks_only(self):
		with load_service(RECIPIENTS) as (module, frappe):
			frappe.get_meta.return_value.has_field.return_value = True
			rows = {
				"Supplier": [
					Record(name="Acme", email_id="sales@acme.com", supplier_primary_contact=None, ill_purchasing_email=""),
					Record(name="Glow", email_id="", supplier_primary_contact="C-9", ill_purchasing_email=None),
					Record(name="Done", email_id="x@done.com", supplier_primary_contact=None, ill_purchasing_email="po@done.com"),
					Record(name="Blank", email_id="", supplier_primary_contact=None, ill_purchasing_email=""),
				],
				"Dynamic Link": [Record(parent="C-9", link_name="Glow")],
				"Contact Email": [Record(parent="C-9", email_id="orders@glow.com", is_primary=1)],
			}
			frappe.get_all.side_effect = lambda doctype, **kw: rows[doctype]
			self.assertEqual(module.backfill_purchasing_emails(), {"Acme": "sales@acme.com", "Glow": "orders@glow.com"})
			written = {c.args[1]: c.args[3] for c in frappe.db.set_value.call_args_list}
			self.assertEqual(written, {"Acme": "sales@acme.com", "Glow": "orders@glow.com"})
			self.assertTrue(all(c.kwargs["update_modified"] is False for c in frappe.db.set_value.call_args_list))

	def test_supplier_save_fills_a_blank_from_the_primary_contact(self):
		with load_service(RECIPIENTS) as (module, frappe):
			frappe.log_error = MagicMock()

			class Supplier(Record):
				meta = types.SimpleNamespace(has_field=lambda field: True)

				def set(self, key, value):
					self[key] = value

			doc = Supplier(email_id="sales@acme.com", ill_purchasing_email="")
			module.fill_supplier_purchasing_email(doc)
			self.assertEqual(doc.ill_purchasing_email, "sales@acme.com")
			doc = Supplier(email_id="sales@acme.com", ill_purchasing_email="po@acme.com")
			module.fill_supplier_purchasing_email(doc)
			self.assertEqual(doc.ill_purchasing_email, "po@acme.com")


if __name__ == "__main__":
	unittest.main()
