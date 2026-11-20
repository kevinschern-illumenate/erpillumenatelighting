"""Customer and supplier email templates: wording renders cleanly, lookups follow the rules.

Rendering uses a Jinja environment built like Frappe's (sandboxed, DebugUndefined, no
autoescape), so a template that reaches for a missing key fails here the same way it
would print ``{{ c.x }}`` in a customer's inbox.
"""

import ast
import os
import re
import types
import unittest
from unittest.mock import MagicMock, patch

import email_template_samples as samples
from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.email_templates import blocks, formatting, library

LEAKS = re.compile(r"\{\{|\{%|\bNone\b|Undefined|\[\]|\{\}")
SUPPLIER_DOCTYPES = {"Purchase Order", "Request for Quotation", "Supplier Quotation", "Purchase Receipt"}


def render(source, context_for, **top_level):
	env = samples.environment(context_for)
	return env.from_string(source).render(**top_level)


def visible_text(html):
	return re.sub(r"<[^>]+>", " ", html)


class Formatting(unittest.TestCase):
	def test_dates(self):
		self.assertEqual(formatting.fmt_date("2026-11-08"), "November 8, 2026")
		self.assertEqual(formatting.fmt_date("2026-11-08 13:00:00"), "November 8, 2026")
		self.assertEqual(formatting.fmt_short_date("2026-11-08"), "Nov 8, 2026")
		for blank in (None, "", "not a date"):
			self.assertEqual(formatting.fmt_date(blank), "")
		self.assertEqual(formatting.days_between("2026-11-18", "2026-11-21"), 3)
		self.assertEqual(formatting.days_between("2026-11-21", "2026-11-18"), -3)
		self.assertIsNone(formatting.days_between(None, "2026-11-18"))

	def test_money(self):
		self.assertEqual(formatting.fmt_money(1234.5), "$1,234.50")
		self.assertEqual(formatting.fmt_money(-12, "USD"), "-$12.00")
		self.assertEqual(formatting.fmt_money(None), "$0.00")
		self.assertEqual(formatting.fmt_money(10, "SEK"), "10.00 SEK")
		self.assertEqual(formatting.fmt_money(10, "cad"), "CA$10.00")

	def test_quantities(self):
		self.assertEqual(formatting.fmt_qty(4.0), "4")
		self.assertEqual(formatting.fmt_qty(32.5), "32.5")

	def test_ship_date_precedence_and_delivery_promise(self):
		order = {
			"ill_confirmed_delivery_date": "2026-12-12",
			"ill_estimated_ship_date": "2026-12-01",
			"ill_likely_ship_date": "2026-12-03",
			"delivery_date": "2026-12-20",
		}
		# The live production estimate wins; the confirmed date is the delivery promise, shown apart.
		self.assertEqual(formatting.ship_date(order), ("December 1, 2026", "Estimated ship date"))
		self.assertEqual(formatting.delivery_promise(order), ("December 12, 2026", "Confirmed delivery date"))
		order.pop("ill_estimated_ship_date")
		self.assertEqual(formatting.ship_date(order)[0], "December 3, 2026")
		order.pop("ill_likely_ship_date")
		self.assertEqual(formatting.ship_date(order)[0], "December 20, 2026")
		self.assertEqual(formatting.ship_date({}), ("", ""))
		self.assertEqual(formatting.delivery_promise({}), ("", ""))

	def test_hold_wording_never_shows_staff_shorthand(self):
		for reason in ("Hold for Release", "Hold for Confirmation", "Hold for Ship", "Something new"):
			message = formatting.hold_message(reason)
			self.assertTrue(message)
			self.assertNotIn("Hold for", message)
		self.assertEqual(formatting.hold_message(None), "")

	def test_overdue_stage(self):
		self.assertEqual(
			[formatting.overdue_stage(d) for d in (None, 0, 1, 14, 15, 29, 30, 90)],
			["", "", "first", "first", "second", "second", "final", "final"],
		)

	def test_line_labels_use_fixture_type_and_section(self):
		lines, more = formatting.summarize_lines(
			[
				{
					"ill_fixture_type": "A1",
					"ill_section_label": "Kitchen",
					"item_name": "Linear",
					"qty": 2,
					"uom": "Nos",
					"amount": 10,
				},
				{"item_name": "Driver", "item_code": "PS-1", "qty": 1},
				{"item_code": "X"},
			],
			limit=2,
		)
		self.assertEqual(lines[0]["label"], "A1 - Kitchen")
		self.assertEqual(lines[0]["detail"], "Linear")
		self.assertEqual(lines[1]["label"], "Driver")
		self.assertEqual(more, 1)
		no_prices, _ = formatting.summarize_lines([{"item_name": "A", "amount": 5}], with_amounts=False)
		self.assertEqual(no_prices[0]["amount"], "")

	def test_merge_same_lines_adds_up_repeated_parts(self):
		def part(**values):
			row = {
				"item_code": "EC-CA01",
				"item_name": "End cap",
				"uom": "Ea",
				"qty": 1,
				"rate": 0.18,
				"amount": 0.18,
				"schedule_date": "2026-12-01",
			}
			row.update(values)
			return row

		rows = [
			part(),
			part(item_code="CH-CA01", rate=3.8, amount=3.8),
			part(qty=2, amount=0.36),
			part(rate=0.25, amount=0.25),
			part(schedule_date="2026-12-15"),
			part(ill_section_label="Bath"),
			{"ill_section_label": "Kitchen", "qty": 0},
			part(),
		]
		merged = formatting.merge_same_lines(rows)
		self.assertEqual(len(merged), 6)
		self.assertEqual((merged[0]["item_code"], merged[0]["qty"]), ("EC-CA01", 4))
		self.assertAlmostEqual(merged[0]["amount"], 0.72)
		# A different price, required-by date or room keeps its own line; headers are left alone.
		self.assertEqual(
			[(r.get("item_code"), r["qty"]) for r in merged[1:]],
			[("CH-CA01", 1), ("EC-CA01", 1), ("EC-CA01", 1), ("EC-CA01", 1), (None, 0)],
		)
		self.assertEqual(rows[0]["qty"], 1)  # the document's own rows are not changed
		lines, more = formatting.summarize_lines(rows, merge=True)
		self.assertEqual((lines[0]["qty"], lines[0]["amount"], more), ("4", "$0.72", 0))
		self.assertEqual(len(formatting.summarize_lines(rows)[0]), 8)

	def test_text_to_html_escapes(self):
		self.assertEqual(formatting.text_to_html("Dock <3>\nCall"), "Dock &lt;3&gt;<br>Call")
		self.assertEqual(formatting.text_to_html(None), "")


class Blocks(unittest.TestCase):
	def test_empty_inputs_render_nothing(self):
		self.assertEqual(blocks.lines_table([]), "")
		self.assertEqual(blocks.schedule_table([]), "")
		self.assertEqual(blocks.payments_table([]), "")
		self.assertEqual(blocks.button("", "Pay"), "")
		self.assertEqual(blocks.tracking({"carrier": None, "number": None}), "")
		self.assertEqual(blocks.address(""), "")

	def test_values_are_escaped(self):
		html = blocks.lines_table([{"label": "<b>x</b>", "qty": "1", "uom": "Nos", "amount": "$1.00"}])
		self.assertIn("&lt;b&gt;x&lt;/b&gt;", html)
		self.assertNotIn("<b>x</b>", html)

	def test_tracking_links_only_with_url(self):
		self.assertIn(
			'href="https://t/1"', blocks.tracking({"carrier": "UPS", "number": "1", "url": "https://t/1"})
		)
		freight = blocks.tracking({"carrier": "Freight", "number": "PRO-1", "url": None})
		self.assertIn("PRO-1", freight)
		self.assertNotIn("href", freight)

	def test_signature_uses_point_of_contact(self):
		html = blocks.signature({"name": "Sam", "email": "sam@x.example", "phone": "555", "title": "Sales"})
		for part in ("Sam", "Sales", "mailto:sam@x.example", "555", "ilLumenate Lighting"):
			self.assertIn(part, html)


class Library(unittest.TestCase):
	def test_every_template_has_a_body_unique_name_and_short_enough_name(self):
		names = [t.name for t in library.TEMPLATES]
		self.assertEqual(len(names), len(set(names)))
		for template in library.TEMPLATES:
			with self.subTest(template=template.name):
				self.assertTrue(os.path.exists(template.path))
				self.assertTrue(template.name.startswith("ilL - "))
				self.assertLessEqual(len(template.name), 140)
				self.assertTrue(template.subject.strip())
				self.assertIn("ill_email_context(doctype, name)", template.body())
				self.assertIn("c.blocks.signature", template.body())

	def test_doctype_specific_templates_name_their_doctype(self):
		for template in library.TEMPLATES:
			if template.doctype:
				self.assertIn(f" - {template.doctype} - ", template.name)

	def test_saved_replies_read_ticket_links_not_the_ticket_name(self):
		for reply in library.SAVED_REPLIES:
			with self.subTest(reply=reply.name):
				body = reply.body()
				self.assertNotIn("ill_email_context(doctype, name)", body)
				if reply.uses:
					self.assertIn(reply.uses, body)
				self.assertIn("{{ full_name }}", body)
				# The Helpdesk editor stores HTML; Jinja comparisons would be escaped.
				self.assertNotRegex(body, r"\{%[^%]*[<>][^%]*%\}")

	def test_notifications_point_at_real_templates_and_compile(self):
		for rule in library.NOTIFICATIONS:
			with self.subTest(rule=rule.name):
				template = library.BY_SLUG[rule.template]
				self.assertEqual(template.doctype, rule.document_type)
				ast.parse(rule.condition, mode="eval")
				self.assertIn(rule.event, ("Days After", "Days Before", "Value Change", "Submit"))
				if rule.event in ("Days After", "Days Before"):
					self.assertTrue(rule.date_changed)
					self.assertGreater(rule.days_in_advance, 0)
				if rule.event == "Value Change":
					self.assertTrue(rule.value_changed)

	def test_body_files_are_all_registered(self):
		registered = {os.path.basename(t.path) for t in library.TEMPLATES}
		on_disk = {f for f in os.listdir(library.BODIES) if f.endswith(".html")}
		self.assertEqual(on_disk, registered)
		helpdesk = {os.path.basename(r.path) for r in library.SAVED_REPLIES}
		self.assertEqual({f for f in os.listdir(os.path.join(library.BODIES, "helpdesk"))}, helpdesk)

	def test_customer_wording_never_shows_internal_fields(self):
		internal = (
			"ill_floor_notes",
			"ill_production_status_override",
			"ill_hold_reason",
			"ill_build_points",
			"ill_rate_notes",
			"ill_duty_rate_pct",
			"ill_additional_tariff_pct",
			"ill_purchasing_notes",
			"ill_late_reason",
		)
		for template in library.TEMPLATES:
			# Jinja comments are notes for staff and never reach the email.
			sent = re.sub(r"\{#.*?#\}", "", template.body(), flags=re.S) + template.subject
			for field in internal:
				self.assertNotIn(field, sent, template.name)


class Rendering(unittest.TestCase):
	VARIANTS = (
		{},
		{"no_po": True},
		{"partial": True},
		{"is_return": True},
		{"paid": True},
		{"expired": True},
		{"days_overdue": 3},
		{"days_overdue": 20},
		{"days_overdue": 45},
		{"no_pay_link": True},
		{"cancelled": True},
		{"unconfirmed": True, "no_promise": True},
		{"no_quote": True},
		{"hold": "Hold for Release", "confirmed": False},
	)

	def assert_clean(self, html, label):
		leak = LEAKS.search(visible_text(html)) or re.search(r"\{\{|\{%", html)
		self.assertIsNone(leak, f"{label}: {leak and html[max(leak.start() - 80, 0) : leak.end() + 80]}")

	def test_every_template_renders_with_full_and_empty_context(self):
		for template in library.TEMPLATES:
			doctype = template.doctype or "Sales Order"
			for variant in self.VARIANTS:
				with self.subTest(template=template.name, variant=variant):
					c = samples.rich(doctype, **variant)
					html = render(template.body(), lambda *_a, c=c: c, **samples.doc_dict(doctype, c["name"]))
					self.assert_clean(html, template.name)
					if "c.greeting_name" in template.body():
						self.assertIn("Jane", html)
					self.assertIn("sam@illumenate.lighting", html)
			with self.subTest(template=template.name, variant="missing document"):
				html = render(
					template.body(),
					lambda d, n: samples.empty(d or "", n or ""),
					**samples.doc_dict(doctype, "X"),
				)
				self.assert_clean(html, template.name)
				if "c.greeting_name" in template.body():
					self.assertIn("there", html)
				# With no document, supplier email signs off with the purchasing mailbox.
				side = "purchasing" if doctype in samples.CONTEXT.PURCHASING_DOCTYPES else "sales"
				self.assertIn(f"{side}@illumenate.lighting", html)

	def test_subjects_render_from_document_fields(self):
		for template in library.TEMPLATES:
			doctype = template.doctype or "Sales Order"
			with self.subTest(template=template.name):
				subject = render(
					template.subject, lambda *_a: samples.empty(), **samples.doc_dict(doctype, "DOC-1")
				)
				self.assert_clean(subject, template.name)
				self.assertNotIn("\n", subject)

	def test_subject_without_optional_fields(self):
		sales_order = library.BY_SLUG["so_confirmation"]
		self.assertEqual(
			render(sales_order.subject, lambda *_a: {}, doctype="Sales Order", name="SO-1"),
			"Order confirmed: SO-1",
		)
		self.assertEqual(
			render(sales_order.subject, lambda *_a: {}, doctype="Sales Order", name="SO-1", po_no="77"),
			"Order confirmed: SO-1 (your PO 77)",
		)
		expiring = library.BY_SLUG["quote_expiring"]
		self.assertEqual(render(expiring.subject, lambda *_a: {}, name="Q-1"), "Quote Q-1 pricing expires ")

	def test_order_confirmation_asks_for_po_only_when_missing(self):
		body = library.BY_SLUG["so_confirmation"].body()
		with_po = render(body, lambda *_a: samples.rich(), doctype="Sales Order", name="SO")
		without = render(body, lambda *_a: samples.rich(no_po=True), doctype="Sales Order", name="SO")
		self.assertIn("4471-B", with_po)
		self.assertNotIn("Do you have a PO number", with_po)
		self.assertIn("Do you have a PO number", without)

	def test_invoice_pay_link_and_instructions_fallback(self):
		body = library.BY_SLUG["si_invoice"].body()
		linked = render(body, lambda *_a: samples.rich("Sales Invoice"), doctype="Sales Invoice", name="SI")
		self.assertIn("https://connect.intuit.com/pay/abc", linked)
		self.assertIn("Other ways to pay", linked)
		unlinked = render(
			body,
			lambda *_a: samples.rich("Sales Invoice", no_pay_link=True),
			doctype="Sales Invoice",
			name="SI",
		)
		self.assertNotIn("intuit.com", unlinked)
		self.assertIn("How to pay", unlinked)
		self.assertIn("ilL-SAL-ORD-Acme Integration-00013", linked, "every billed Sales Order is listed")

	def test_overdue_tone_follows_days_overdue(self):
		body = library.BY_SLUG["si_overdue"].body()
		first = render(
			body,
			lambda *_a: samples.rich("Sales Invoice", days_overdue=3),
			doctype="Sales Invoice",
			name="SI",
		)
		final = render(
			body,
			lambda *_a: samples.rich("Sales Invoice", days_overdue=45),
			doctype="Sales Invoice",
			name="SI",
		)
		self.assertIn("already paid", first)
		self.assertIn("pause shipments", final)
		self.assertNotIn("pause shipments", first)

	def test_shipped_email_handles_partial_and_return(self):
		body = library.BY_SLUG["dn_shipped"].body()
		partial = render(
			body, lambda *_a: samples.rich("Delivery Note", partial=True), doctype="Delivery Note", name="DN"
		)
		self.assertIn("partial shipment", partial)
		self.assertIn("1Z999", partial)
		self.assertIn("Packing list (PDF)", partial)
		returned = render(
			body,
			lambda *_a: samples.rich("Delivery Note", is_return=True),
			doctype="Delivery Note",
			name="DN",
		)
		self.assertIn("return", returned)
		self.assertNotIn("Good news", returned)

	def test_rfq_uses_erpnext_supplier_context_and_survives_without_it(self):
		body = library.BY_SLUG["rfq_request"].body()
		full = render(
			body,
			lambda *_a: samples.rich("Request for Quotation"),
			doctype="Request for Quotation",
			name="RFQ-1",
			contact={"first_name": "Li"},
			supplier_name="Vendor Co",
			portal_link='<a href="https://p">Submit your Quotation</a>',
			update_password_link='<a href="https://p">Set Password</a>',
			user_fullname="Sam Rivera",
		)
		self.assertIn("Hello Li", full)
		# Suppliers reply by email; ERPNext's portal buttons are never printed.
		self.assertNotIn("Submit your Quotation", full)
		self.assertNotIn("Set Password", full)
		self.assertNotIn("portal_link", body)
		self.assertIn("reply to this email with your quotation", full)
		for asked in ("unit price", "lead time", "MOQ", "payment terms", "PDF"):
			self.assertIn(asked, full)
		self.assertIn("Sam Rivera", full)
		bare = render(
			body,
			lambda *_a: samples.rich("Request for Quotation"),
			doctype="Request for Quotation",
			name="RFQ-1",
		)
		self.assert_clean(bare, "rfq without supplier context")
		self.assertIn("Hello there", bare)

	def test_saved_replies_render_with_and_without_ticket_links(self):
		agent = {
			"name": "agent@illumenate.lighting",
			"doctype": "User",
			"full_name": "Alex Agent",
			"email": "agent@illumenate.lighting",
		}
		for reply in library.SAVED_REPLIES:
			with self.subTest(reply=reply.name):
				linked = render(
					reply.body(),
					lambda d, n: samples.rich(d) if n else samples.empty(d or "", ""),
					subject="Order question",
					contact="Jane Doe",
					ill_sales_order="SO-1",
					ill_sales_invoice="SI-1",
					ill_quotation="Q-1",
					**agent,
				)
				self.assert_clean(linked, reply.name)
				self.assertIn("Alex Agent", linked)
				# A ticket with no links (or a site without the link fields) asks instead of failing.
				unlinked = render(
					reply.body(), lambda d, n: samples.empty(d or "", ""), subject="Hi", **agent
				)
				self.assert_clean(unlinked, reply.name)
				self.assertIn("Hi there", unlinked)


class FakeMeta:
	def __init__(self, fields=()):
		self.fields = set(fields)

	def has_field(self, fieldname):
		return fieldname in self.fields


class FakeDoc(Record):
	def __init__(self, doctype, name, fields=(), **values):
		super().__init__(doctype=doctype, name=name, **values)
		self["meta"] = FakeMeta(fields or values.keys())


class ContextBuilders(unittest.TestCase):
	def load(self):
		return load_service(ROOT + ".email_templates.context")

	def test_purchase_order_lines_add_up_repeated_parts_and_other_documents_do_not(self):
		with self.load() as (module, _frappe):
			rows = [
				Record(item_code="EC-CA01", item_name="End cap", qty=1, uom="Ea", rate=0.18, amount=0.18),
				Record(item_code="EC-CA01", item_name="End cap", qty=1, uom="Ea", rate=0.18, amount=0.18),
				Record(item_code="EC-CA01", item_name="End cap", qty=1, uom="Ea", rate=0.18, amount=0.18),
			]
			counts = {}
			with (
				patch.object(module, "point_of_contact", return_value=module.skeleton()["poc"]),
				patch.object(module, "_portal"),
				patch.object(module, "_job"),
				patch.object(module, "_greeting", return_value="there"),
			):
				for doctype in ("Purchase Order", "Sales Order"):
					c = module.skeleton()
					doc = FakeDoc(doctype, "DOC-1", fields=("items",), items=rows, currency="USD")
					module._common(c, doc, samples.settings())
					counts[doctype] = [line["qty"] for line in c["lines"]]
			self.assertEqual(counts["Purchase Order"], ["3"])
			self.assertEqual(counts["Sales Order"], ["1", "1", "1"])
			blocks_html = blocks.supplier_lines_table(c["lines"])
			self.assertTrue(blocks_html)

	def test_unreadable_or_missing_document_gives_empty_context(self):
		with self.load() as (module, frappe):
			frappe.db.exists.return_value = True
			frappe.has_permission.return_value = False
			with patch.object(module, "get_settings", return_value=samples.settings()):
				c = module.ill_email_context("Sales Order", "SO-1")
			self.assertFalse(c["found"])
			self.assertEqual(c["poc"]["email"], "sales@illumenate.lighting")
			frappe.get_doc.assert_not_called()

	def test_lookup_failure_is_logged_not_raised(self):
		with self.load() as (module, frappe):
			frappe.db.exists.return_value = True
			frappe.get_doc.side_effect = RuntimeError("boom")
			frappe.log_error = MagicMock()
			with patch.object(module, "get_settings", return_value=samples.settings()):
				c = module.ill_email_context("Sales Order", "SO-1")
			self.assertFalse(c["found"])
			frappe.log_error.assert_called_once()

	def test_undefined_and_blank_arguments_count_as_missing(self):
		with self.load() as (module, frappe):
			undefined = type("DebugUndefined", (), {})()
			with patch.object(module, "get_settings", return_value=samples.settings()):
				self.assertFalse(module.ill_email_context("Sales Order", undefined)["found"])
				self.assertFalse(module.ill_email_context("Sales Order", "  ")["found"])
			frappe.db.exists.assert_not_called()

	def test_point_of_contact_precedence(self):
		with self.load() as (module, frappe):
			users = {
				"sam@illumenate.lighting": Record(
					full_name="Sam Rivera",
					email="sam@illumenate.lighting",
					mobile_no="555",
					phone=None,
					user_type="System User",
					enabled=1,
				),
				"dealer@acme.example": Record(
					full_name="Dealer", email="dealer@acme.example", user_type="Website User", enabled=1
				),
				"qbo-integration@illumenate.lighting": Record(
					full_name="QBO",
					email="qbo-integration@illumenate.lighting",
					user_type="System User",
					enabled=1,
				),
			}
			contact = Record(
				full_name="Pat Lee",
				first_name="Pat",
				last_name="Lee",
				email_id="pat@illumenate.lighting",
				phone="111",
				mobile_no=None,
				designation="Inside Sales",
			)

			def get_value(doctype, name, fields=None, as_dict=False):
				if doctype == "Contact":
					return contact
				if doctype == "User":
					return users.get(name)
				return None

			frappe.db.get_value.side_effect = get_value
			with patch.object(
				module, "_service_user_emails", return_value={"qbo-integration@illumenate.lighting"}
			):
				settings = samples.settings()
				doc = FakeDoc(
					"Sales Order", "SO-1", company_contact_person="Pat Lee", owner="sam@illumenate.lighting"
				)
				self.assertEqual(module.point_of_contact(doc, settings)["name"], "Pat Lee")
				doc = FakeDoc("Sales Order", "SO-1", owner="sam@illumenate.lighting")
				self.assertEqual(module.point_of_contact(doc, settings)["email"], "sam@illumenate.lighting")
				for owner in ("dealer@acme.example", "qbo-integration@illumenate.lighting", "Administrator"):
					doc = FakeDoc("Sales Order", "SO-1", owner=owner)
					self.assertEqual(
						module.point_of_contact(doc, settings)["email"], "sales@illumenate.lighting", owner
					)
				doc = FakeDoc("Purchase Order", "PO-1", owner="Administrator")
				self.assertEqual(
					module.point_of_contact(doc, settings)["name"], "ilLumenate Lighting Purchasing"
				)

	def test_deposit_is_first_open_row_of_a_split_schedule(self):
		with self.load() as (module, _frappe):
			c = module.skeleton()
			doc = FakeDoc("Sales Order", "SO-1", transaction_date="2026-11-18")
			rows = [
				{
					"outstanding_raw": 500.0,
					"outstanding": "$500.00",
					"due_date_raw": "2026-11-18",
					"portion": "50%",
				},
				{
					"outstanding_raw": 500.0,
					"outstanding": "$500.00",
					"due_date_raw": "2026-12-18",
					"portion": "50%",
				},
			]
			self.assertEqual(module._payment_due(c, doc, rows)["label"], "Deposit")
			self.assertEqual(module._payment_due(c, doc, rows)["amount"], "$500.00")
			rows[0]["outstanding_raw"] = 0
			self.assertEqual(module._payment_due(c, doc, rows)["amount"], "")
			single = [
				{
					"outstanding_raw": 900.0,
					"outstanding": "$900.00",
					"due_date_raw": "2026-11-19",
					"portion": "100%",
				}
			]
			self.assertEqual(module._payment_due(c, doc, single)["label"], "Payment in advance")
			single[0]["due_date_raw"] = "2026-12-18"  # net terms, nothing due before production
			self.assertEqual(module._payment_due(c, doc, single)["label"], "")

	def test_pay_link_must_be_https_intuit(self):
		with self.load() as (module, _frappe):
			self.assertEqual(
				module._safe_pay_link("https://connect.intuit.com/pay/x"), "https://connect.intuit.com/pay/x"
			)
			for bad in (
				"http://connect.intuit.com/x",
				"https://intuit.com.evil.example/x",
				"javascript:alert(1)",
				None,
			):
				self.assertEqual(module._safe_pay_link(bad), "")

	def test_sales_invoice_lists_each_sales_order_once_and_counts_overdue_days(self):
		with self.load() as (module, frappe):
			frappe.utils.nowdate = lambda: "2026-12-28"
			frappe.db.get_value.return_value = None
			doc = FakeDoc(
				"Sales Invoice",
				"SI-1",
				fields=("items",),
				posting_date="2026-11-18",
				due_date="2026-12-18",
				grand_total=1000,
				rounded_total=1000,
				outstanding_amount=400,
				docstatus=1,
				is_return=0,
				currency="USD",
				company="ilLumenate Lighting",
				custom_qbo_payment_link="https://connect.intuit.com/pay/x",
				items=[
					Record(sales_order="SO-1", delivery_note="DN-1"),
					Record(sales_order="SO-2"),
					Record(sales_order="SO-1"),
				],
			)
			c = module.skeleton()
			c["docstatus"] = 1
			with (
				patch.object(module, "pdf_url", side_effect=lambda dt, n, pf=None: f"pdf:{n}"),
				patch.object(module, "_invoice_payments", return_value=[]),
				patch.object(module, "_pay_instructions", return_value=""),
			):
				module._sales_invoice(c, doc, samples.settings())
			self.assertEqual([o["name"] for o in c["sales_orders"]], ["SO-1", "SO-2"])
			self.assertEqual(c["invoice"]["days_overdue"], 10)
			self.assertEqual(c["invoice"]["overdue_stage"], "first")
			self.assertTrue(c["invoice"]["is_partly_paid"])
			self.assertEqual(c["invoice"]["paid_to_date"], "$600.00")
			self.assertEqual(c["pay_link"], "https://connect.intuit.com/pay/x")
			self.assertEqual(c["pdf"]["si"], "pdf:SI-1")

	def test_paid_invoice_offers_no_pay_link(self):
		with self.load() as (module, frappe):
			frappe.utils.nowdate = lambda: "2026-12-28"
			doc = FakeDoc(
				"Sales Invoice",
				"SI-1",
				fields=("items",),
				due_date="2026-12-18",
				grand_total=1000,
				outstanding_amount=0,
				docstatus=1,
				is_return=0,
				custom_qbo_payment_link="https://connect.intuit.com/pay/x",
				items=[],
			)
			c = module.skeleton()
			c["docstatus"] = 1
			with (
				patch.object(module, "pdf_url", return_value=""),
				patch.object(module, "_invoice_payments", return_value=[]),
				patch.object(module, "_pay_instructions", return_value=""),
			):
				module._sales_invoice(c, doc, samples.settings())
			self.assertTrue(c["invoice"]["is_paid"])
			self.assertEqual(c["pay_link"], "")
			self.assertEqual(c["invoice"]["days_overdue"], 0)

	def test_order_portal_links_encode_names_with_spaces_and_slashes(self):
		"""Customer names with spaces or "/" end up in Sales Order names; the link must stay one segment."""
		name = "ilL-SAL-ORD-Backcountry Electric / LINX Audio Visual-00001"
		encoded = "/portal/orders/ilL-SAL-ORD-Backcountry%20Electric%20%2F%20LINX%20Audio%20Visual-00001"
		tracker = types.SimpleNamespace(tracking=lambda doc: {"carrier": None, "number": None, "url": None})
		with self.load() as (module, frappe):
			frappe.get_all.return_value = []
			frappe.db.get_value.return_value = 0
			order = FakeDoc("Sales Order", name, docstatus=1, per_delivered=0)
			c = module.skeleton()
			c["docstatus"] = 1
			c["is_dealer"] = True
			with (
				patch.object(module, "pdf_url", return_value=""),
				patch.object(module, "_schedule_rows", return_value=[]),
				patch.object(module, "_payment_due", return_value={}),
				patch.object(module, "_order_shipments", return_value=[]),
				patch.object(module, "_order_invoices", return_value=[]),
				patch.object(module, "_pay_instructions", return_value=""),
			):
				module._sales_order(c, order, samples.settings())
			self.assertEqual(c["portal_url"], "https://portal.test" + encoded)

			note = FakeDoc("Delivery Note", "DN-1", items=[Record(against_sales_order=name)])
			c = module.skeleton()
			c["is_dealer"] = True
			with (
				patch.dict("sys.modules", {ROOT + ".portal.shipment_tracking": tracker}),
				patch.object(module, "pdf_url", return_value=""),
			):
				module._delivery_note(c, note, samples.settings())
			self.assertEqual(c["portal_url"], "https://portal.test" + encoded)
			self.assertNotIn(" ", c["portal_url"])

	def test_every_builder_key_exists_in_the_skeleton(self):
		"""A builder that writes a key the skeleton lacks would break templates on other documents."""
		source = open(
			"illumenate_lighting/illumenate_lighting/email_templates/context.py", encoding="utf-8"
		).read()
		with self.load() as (module, _frappe):
			skeleton = module.skeleton()
		groups = {
			"q": "quote",
			"o": "order",
			"inv": "invoice",
			"sh": "shipment",
			"p": "purchase",
			"r": "rfq",
			"sq": "supplier_quote",
			"rec": "receipt",
			"pay": "payment",
			"cust": "customer",
			"deal": "deal",
			"b": "blocks",
		}
		for var, key in groups.items():
			for written in re.findall(rf'\b{var}\["(\w+)"\]\s*(?:,|=)', source):
				self.assertIn(written, skeleton[key], f"{key}.{written}")
		for written in re.findall(r'\bc\["(\w+)"\]\s*(?:,|=)', source):
			self.assertIn(written, skeleton, written)


class AutoSend(unittest.TestCase):
	def load(self):
		return load_service(ROOT + ".email_templates.auto_send")

	def test_nothing_is_queued_while_switched_off(self):
		with self.load() as (module, frappe):
			frappe.enqueue = MagicMock()
			with patch.object(module, "get_settings", return_value=samples.settings()):
				module.on_sales_order_submit(Record(doctype="Sales Order", name="SO-1"))
				module.on_delivery_note_submit(Record(doctype="Delivery Note", name="DN-1", is_return=0))
			frappe.enqueue.assert_not_called()

	def test_switched_on_queues_after_commit_and_skips_returns(self):
		with self.load() as (module, frappe):
			frappe.enqueue = MagicMock()
			on = samples.settings(auto_send_order_confirmation=1, auto_send_shipped=1)
			with patch.object(module, "get_settings", return_value=on):
				module.on_sales_order_submit(Record(doctype="Sales Order", name="SO-1"))
				module.on_delivery_note_submit(Record(doctype="Delivery Note", name="DN-1", is_return=1))
			frappe.enqueue.assert_called_once()
			kwargs = frappe.enqueue.call_args.kwargs
			self.assertTrue(kwargs["enqueue_after_commit"])
			self.assertEqual((kwargs["doctype"], kwargs["name"]), ("Sales Order", "SO-1"))

	def test_portal_users_are_not_emailed_twice(self):
		with self.load() as (module, _frappe):
			doc = Record(
				doctype="Sales Order", name="SO-1", contact_email="Buyer@Acme.example", customer="Acme"
			)
			with patch.object(module, "portal_addresses", return_value={"buyer@acme.example"}):
				self.assertEqual(module.customer_recipients(doc), [])
				self.assertEqual(module.customer_recipients(doc, include_portal=True), ["Buyer@Acme.example"])
			with patch.object(module, "portal_addresses", return_value=set()):
				self.assertEqual(module.customer_recipients(doc), ["Buyer@Acme.example"])

	def test_falls_back_to_the_customer_purchasing_contact(self):
		with self.load() as (module, frappe):
			frappe.get_meta.return_value = FakeMeta({"ill_purchasing_contact"})
			frappe.db.get_value.side_effect = lambda dt, name, field: {
				"Customer": "CONT-1",
				"Contact": "ap@acme.example",
			}[dt]
			doc = Record(doctype="Sales Order", name="SO-1", contact_email=None, customer="Acme")
			with patch.object(module, "portal_addresses", return_value=set()):
				self.assertEqual(module.customer_recipients(doc), ["ap@acme.example"])

	def test_send_skips_a_document_already_emailed(self):
		with self.load() as (module, frappe):
			comm = types.ModuleType("frappe.core.doctype.communication.email")
			comm.make = MagicMock()
			frappe.db.exists.return_value = True
			frappe.get_doc.return_value = Record(doctype="Sales Order", name="SO-1", docstatus=1)
			with (
				patch.dict("sys.modules", {"frappe.core.doctype.communication.email": comm}),
				patch.object(
					module, "get_settings", return_value=samples.settings(auto_send_order_confirmation=1)
				),
			):
				self.assertEqual(module.send("Sales Order", "SO-1"), [])
			comm.make.assert_not_called()


class PdfAllowlist(unittest.TestCase):
	def test_shipping_purchasing_and_payment_documents_get_links(self):
		custom_field = types.ModuleType("frappe.custom.doctype.custom_field.custom_field")
		custom_field.create_custom_fields = MagicMock()
		extras = {"frappe.custom.doctype.custom_field.custom_field": custom_field}
		with load_service(ROOT + ".helpdesk_links", extras) as (module, frappe):
			frappe.db.exists.return_value = True
			frappe.utils.get_url = lambda path: "https://site" + path
			frappe.get_doc.return_value = MagicMock(docstatus=1, get_document_share_key=lambda: "KEY")
			for doctype in (
				"Delivery Note",
				"Packing Slip",
				"Purchase Order",
				"Request for Quotation",
				"Supplier Quotation",
				"Payment Entry",
				"Sales Invoice",
			):
				url = module.ill_print_pdf_url(doctype, "DOC-1", "Fmt")
				self.assertIn("key=KEY", url, doctype)
			self.assertEqual(module.ill_print_pdf_url("User", "Administrator"), "")
			self.assertNotIn("Delivery Note", module.LINK_FIELDS, "the ticket link map is unchanged")
			frappe.get_doc.return_value = MagicMock(docstatus=2)
			self.assertEqual(module.ill_print_pdf_url("Delivery Note", "DOC-1"), "")


class HelpdeskSubjectLinks(unittest.TestCase):
	def load(self):
		custom_field = types.ModuleType("frappe.custom.doctype.custom_field.custom_field")
		custom_field.create_custom_fields = MagicMock()
		return load_service(
			ROOT + ".helpdesk_links", {"frappe.custom.doctype.custom_field.custom_field": custom_field}
		)

	def ticket(self, subject, **links):
		ticket = Record(subject=subject, **links)
		ticket.set = lambda field, value: ticket.__setitem__(field, value)
		return ticket

	def test_reply_to_our_email_links_the_document_in_its_subject(self):
		existing = {
			("Sales Order", "ilL-SAL-ORD-Backcountry Electric / LINX Audio Visual-00003"),
			("Quotation", "ilL-SAL-QTN--00002"),
			("Sales Invoice", "ilL-ACC-SINV-Cascade Integration-00023"),
			("Sales Order", "ilL-SAL-ORD-Tech Integrated-00005"),
		}
		with self.load() as (module, frappe):
			frappe.db.exists.side_effect = lambda doctype, name: (doctype, name) in existing
			ticket = self.ticket(
				"Re: Order confirmed: ilL-SAL-ORD-Backcountry Electric / LINX Audio Visual-00003 (your PO 4471-B)"
			)
			module.link_from_subject(ticket)
			self.assertEqual(
				ticket.get("ill_sales_order"), "ilL-SAL-ORD-Backcountry Electric / LINX Audio Visual-00003"
			)
			ticket = self.ticket("Re: Following up on quote ilL-SAL-QTN--00002")
			module.link_from_subject(ticket)
			self.assertEqual(ticket.get("ill_quotation"), "ilL-SAL-QTN--00002")
			ticket = self.ticket("RE: Past due: invoice ilL-ACC-SINV-Cascade Integration-00023 ($565.93)")
			module.link_from_subject(ticket)
			self.assertEqual(ticket.get("ill_sales_invoice"), "ilL-ACC-SINV-Cascade Integration-00023")
			# An amendment suffix that does not exist falls back to the base number.
			ticket = self.ticket("Re: ilL-SAL-ORD-Tech Integrated-00005-1")
			module.link_from_subject(ticket)
			self.assertEqual(ticket.get("ill_sales_order"), "ilL-SAL-ORD-Tech Integrated-00005")

	def test_unknown_numbers_and_linked_tickets_are_left_alone(self):
		with self.load() as (module, frappe):
			frappe.db.exists.return_value = False
			ticket = self.ticket("Re: ilL-SAL-ORD-Nobody-00099")
			module.link_from_subject(ticket)
			self.assertIsNone(ticket.get("ill_sales_order"))
			frappe.db.exists.return_value = True
			ticket = self.ticket("Re: ilL-SAL-ORD-Acme-00001", ill_quotation="Q-1")
			module.link_from_subject(ticket)
			self.assertIsNone(ticket.get("ill_sales_order"))


class Hooks(unittest.TestCase):
	def test_jinja_methods_and_doc_events_are_registered(self):
		hooks = open("illumenate_lighting/hooks.py", encoding="utf-8").read()
		for method in ("ill_email_context", "ill_tracking", "ill_money", "ill_date"):
			self.assertIn(f"email_templates.context.{method}", hooks)
		for handler in (
			"auto_send.on_sales_order_submit",
			"auto_send.on_delivery_note_submit",
			"recipients.fill_purchase_order_email",
			"recipients.fill_rfq_supplier_emails",
		):
			self.assertIn(handler, hooks)
		self.assertIn(
			'"Request for Quotation": "illumenate_lighting.illumenate_lighting.email_templates.rfq.ILLRequestForQuotation"',
			hooks,
		)
		self.assertIn("illumenate_lighting.patches.rfq_reply_by_email", open("illumenate_lighting/patches.txt").read())
		self.assertIn(
			"illumenate_lighting.patches.seed_email_templates", open("illumenate_lighting/patches.txt").read()
		)


if __name__ == "__main__":
	unittest.main()
