"""The branded email card, sign-in email bodies, sender name and account email settings.

Templates render through a Jinja environment that resolves ``templates/emails/...`` from
this app the way Frappe's loader does (apps installed after Frappe are searched first).
"""

import pathlib
import re
import types
import unittest
from unittest.mock import MagicMock

import jinja2
from test_services import ROOT, Record, load_service

APP = pathlib.Path(__file__).resolve().parents[2] / "illumenate_lighting"
LEAKS = re.compile(r"\{\{|\{%|\{#|Undefined|\bNone\b")
SITE = "https://portal.test"


class _dict(dict):
	__getattr__ = dict.get


def brand_service(user_types=None, lifetime=259200):
	context = load_service(ROOT + ".email_templates.brand")
	module, frappe = context.__enter__()
	frappe._dict = _dict
	frappe.get_system_settings = MagicMock(return_value=lifetime)
	user_types = user_types or {}
	frappe.db.get_value = MagicMock(side_effect=lambda doctype, name, field, *a, **k: user_types.get(name))
	return context, module, frappe


def environment(module):
	env = jinja2.Environment(loader=jinja2.FileSystemLoader(str(APP)), undefined=jinja2.DebugUndefined)
	env.globals.update(
		ill_email_brand=module.ill_email_brand,
		ill_link_lifetime=module.ill_link_lifetime,
		ill_is_staff=module.ill_is_staff,
		_=lambda text, *a: text,
	)
	return env


class Brand(unittest.TestCase):
	def setUp(self):
		context, self.brand, self.frappe = brand_service(
			{"dana@dealer.test": "Website User", "kevin@illumenate.test": "System User"}
		)
		self.addCleanup(context.__exit__, None, None, None)
		self.env = environment(self.brand)

	def card(self, content, **params):
		values = dict(
			subject="Subject",
			header=None,
			content=content,
			footer="<!--unsubscribe link here-->",
			print_html=None,
			with_container=True,
		)
		values.update(params)
		return self.env.get_template("templates/emails/standard.html").render(**values)

	def test_link_lifetime_wording(self):
		self.assertEqual(self.brand.describe_seconds(259200), "72 hours")
		self.assertEqual(self.brand.describe_seconds(3600), "1 hour")
		self.assertEqual(self.brand.describe_seconds(1200), "20 minutes")
		self.assertEqual(self.brand.describe_seconds(60), "1 minute")
		self.assertEqual(self.brand.describe_seconds(None), "")
		self.assertEqual(self.brand.ill_link_lifetime(), "72 hours")

	def test_card_carries_logo_contact_and_frappe_footer_markers(self):
		html = self.card("<p>Body</p>")
		self.assertIsNone(LEAKS.search(html), LEAKS.search(html))
		self.assertIn(SITE + "/assets/illumenate_lighting/images/email/wordmark-white.png", html)
		self.assertIn("PO Box 297, Bothell WA 98041", html)
		self.assertIn("(425) 381-2447", html)
		self.assertIn("tel:+14253812447", html)
		self.assertIn("mailto:sales@illumenate.lighting", html)
		self.assertIn("#172E48", html)
		self.assertIn("#FDC757", html)
		# Frappe swaps the unsubscribe placeholder in the footer; it must survive the card.
		self.assertIn("<!--unsubscribe link here-->", html)
		self.assertIn("<p>Body</p>", html)

	def test_notification_header_goes_in_the_card(self):
		html = self.card(
			"<p>Body</p>", header='<h1 class="email-header-title">Assignment</h1>', with_container=False
		)
		self.assertIn("ill-header", html)
		self.assertIn("Assignment", html)
		self.assertIn("wordmark-white.png", html)

	def test_composer_email_without_container_keeps_frappe_plain_layout(self):
		html = self.card("<p>Hi Sam</p>", with_container=False)
		self.assertNotIn("wordmark-white.png", html)
		self.assertNotIn("PO Box 297", html)
		self.assertIn("<p>Hi Sam</p>", html)

	def test_automatic_template_marker_puts_a_notification_in_the_card(self):
		from illumenate_lighting.illumenate_lighting.email_templates import library

		automatic = library.automatic_slugs()
		self.assertIn("so_confirmation", automatic)
		self.assertIn("si_overdue", automatic)
		self.assertNotIn("quote_sent", automatic)
		self.assertTrue(library.BY_SLUG["si_overdue"].body().startswith(library.CARD_MARKER))
		self.assertFalse(library.BY_SLUG["quote_sent"].body().startswith(library.CARD_MARKER))
		# A Notification arrives with no header and no container, only the marked body.
		html = self.card(library.CARD_MARKER + "<p>Invoice</p>", with_container=False)
		self.assertIn("wordmark-white.png", html)

	def test_auth_wrapper_uses_the_card(self):
		html = self.env.get_template("templates/emails/auth_email.html").render(
			subject="Password Reset", header=None, content="<p>Reset</p>", footer="", print_html=None
		)
		self.assertIn("wordmark-white.png", html)
		self.assertIn("<p>Reset</p>", html)

	def body(self, name, **args):
		html = self.env.get_template(f"templates/emails/{name}.html").render(**args)
		self.assertIsNone(LEAKS.search(html), (name, LEAKS.search(html)))
		return html

	def test_welcome_for_a_dealer_states_the_link_lifetime(self):
		html = self.body(
			"new_user", first_name="Dana", user="dana@dealer.test", link=SITE + "/update-password?key=K"
		)
		self.assertIn("Welcome to the ilLumenate dealer portal", html)
		self.assertIn("Hi Dana,", html)
		self.assertIn("Set your password", html)
		self.assertIn("<strong>72 hours</strong>", html)
		self.assertIn("dana@dealer.test", html)
		self.assertEqual(html.count(SITE + "/update-password?key=K"), 3)

	def test_welcome_for_staff_and_unnamed_users(self):
		html = self.body("new_user", first_name="user", user="kevin@illumenate.test", link="L")
		self.assertIn("staff account", html)
		self.assertIn("Hi there,", html)

	def test_welcome_escapes_names(self):
		html = self.body("new_user", first_name="<b>x</b>", user="dana@dealer.test", link="L")
		self.assertIn("Hi &lt;b&gt;x&lt;/b&gt;,", html)

	def test_password_reset_sign_in_link_and_two_factor(self):
		reset = self.body(
			"password_reset", first_name="Dana", user="dana@dealer.test", link="L", expiry_minutes=4320
		)
		self.assertIn("Reset your password", reset)
		self.assertIn("72 hours", reset)
		link = self.body("login_with_email_link", link="L", minutes=10, app_name="ilLumenate Lighting")
		self.assertIn("10 minutes", link)
		self.assertIn("Sign in", link)
		self.assertIn("1 minute.", self.body("login_with_email_link", link="L", minutes=1, app_name="x"))
		setup = self.body("two_factor_setup", qrcode_link=SITE + "/qrcode?k=1")
		self.assertIn("Show my QR code", setup)
		self.assertIn(SITE + "/qrcode?k=1", setup)
		code = self.body("verification_code", code="482913", minutes=5)
		self.assertIn("482913", code)
		self.assertIn("5 minutes", code)

	def test_portal_email_escapes_and_drops_blank_rows(self):
		html = self.brand.portal_email(
			"Title <x>",
			paragraphs=["Para", None],
			details=[("Carrier", "FedEx"), ("Tracking", None)],
			action=("Track", "https://track.test/?a=1&b=<2>"),
			secondary=("View order", SITE + "/portal/orders/SO-1"),
			preference_note="shipping updates",
		)
		self.assertIn("Title &lt;x&gt;", html)
		self.assertIn("FedEx", html)
		self.assertNotIn("Tracking", html)
		self.assertIn('href="https://track.test/?a=1&amp;b=&lt;2&gt;"', html)
		self.assertIn(SITE + "/portal/account", html)
		self.assertIn("shipping updates", html)
		self.assertIsNone(LEAKS.search(html))


RAW = (
	"MIME-Version: 1.0\r\n"
	"Subject: Password Reset\r\n"
	"From: Info <info@illumenate.test>\r\n"
	"To: <!--recipient-->\r\n"
	"Reply-To: Sales <sales@illumenate.test>\r\n"
	"\r\n"
	"From: this line is body text and must stay\r\n"
)


class Sender(unittest.TestCase):
	def setUp(self):
		context, self.brand, _frappe = brand_service()
		self.addCleanup(context.__exit__, None, None, None)
		self.account = Record(name="Info", email_id="info@illumenate.test")

	def queue(self, sender, message=RAW, **values):
		queue = Record(sender=sender, message=message, **values)
		queue.get_email_account = lambda: self.account
		return queue

	def test_default_account_sender_becomes_the_brand(self):
		queue = self.queue("Info <info@illumenate.test>")
		self.assertTrue(self.brand.rebrand_sender(queue))
		self.assertEqual(queue.sender, "ilLumenate Lighting <info@illumenate.test>")
		self.assertIn("\r\nFrom: ilLumenate Lighting <info@illumenate.test>\r\n", queue.message)
		self.assertIn("From: this line is body text and must stay", queue.message)
		self.assertIn("Reply-To: Sales <sales@illumenate.test>", queue.message)

	def test_welcome_mail_from_the_staff_member_who_made_the_user_becomes_the_brand(self):
		message = RAW.replace(
			"From: Info <info@illumenate.test>", "From: Kevin Schern\r\n <kevin@illumenate.test>"
		)
		queue = self.queue("Kevin Schern <kevin@illumenate.test>", message, redact_message_after_send=1)
		self.assertTrue(self.brand.rebrand_sender(queue))
		self.assertEqual(queue.sender, "ilLumenate Lighting <info@illumenate.test>")
		self.assertNotIn("kevin@", queue.message.split("\r\n\r\n")[0])

	def test_a_person_sending_from_the_composer_keeps_their_name(self):
		message = RAW.replace("Info <info@illumenate.test>", "Jay Divine <jay@illumenate.test>")
		queue = self.queue("Jay Divine <jay@illumenate.test>", message, reference_doctype="Quotation")
		self.assertFalse(self.brand.rebrand_sender(queue))
		self.assertEqual(queue.message, message)

	def test_redacted_mail_about_a_document_is_left_alone(self):
		queue = self.queue(
			"Jay Divine <jay@illumenate.test>", redact_message_after_send=1, reference_doctype="Quotation"
		)
		self.assertFalse(self.brand.rebrand_sender(queue))

	def test_unix_newlines_and_missing_account(self):
		queue = self.queue("Info <info@illumenate.test>", RAW.replace("\r\n", "\n"))
		self.brand.rebrand_sender(queue)
		self.assertIn("\nFrom: ilLumenate Lighting <info@illumenate.test>\n", queue.message)
		self.account = None
		self.assertFalse(self.brand.rebrand_sender(self.queue("Info <info@illumenate.test>")))


class AccountSettings(unittest.TestCase):
	def service(self):
		context = load_service(ROOT + ".email_templates.system_emails")
		module, frappe = context.__enter__()
		self.addCleanup(context.__exit__, None, None, None)
		return module, frappe

	def test_template_bodies_ship_without_their_comment(self):
		module, _frappe = self.service()
		for _name, _subject, filename, _field in module.SYSTEM_TEMPLATES:
			text = module.body(filename)
			self.assertFalse(text.startswith("{#"), filename)
			self.assertIn('{% from "templates/emails/ill_macros.html" import', text)

	def test_settings_point_at_templates_with_72_hour_links(self):
		module, frappe = self.service()
		values = module.apply_settings()
		self.assertEqual(values["reset_password_link_expiry_duration"], 259200)
		self.assertEqual(values["welcome_email_template"], "ilL - Welcome")
		self.assertEqual(values["reset_password_template"], "ilL - Password reset")
		self.assertEqual(values["app_name"], "ilLumenate Lighting")
		self.assertEqual(frappe.db.set_single_value.call_count, 4)

	def test_two_factor_moves_from_everyone_to_desk_roles(self):
		module, frappe = self.service()
		frappe.db.get_value = MagicMock(return_value=1)
		frappe.get_all = MagicMock(return_value=["System Manager", "Sales User"])
		changed = module.staff_only_two_factor()
		self.assertEqual(changed, ["All", "System Manager", "Sales User"])
		frappe.db.set_value.assert_any_call("Role", "All", "two_factor_auth", 0)
		frappe.db.set_value.assert_any_call("Role", "Sales User", "two_factor_auth", 1)
		filters = frappe.get_all.call_args.kwargs["filters"]
		self.assertEqual(filters["desk_access"], 1)
		self.assertEqual(filters["name"], ["not in", ("All", "Guest")])

	def test_templates_are_created_once_and_never_overwritten_by_default(self):
		module, frappe = self.service()
		frappe.db.exists = MagicMock(return_value=True)
		self.assertEqual(module.ensure_templates(), [])
		frappe.db.exists = MagicMock(return_value=False)
		doc = MagicMock()
		frappe.new_doc = MagicMock(return_value=doc)
		self.assertEqual(module.ensure_templates(), ["ilL - Welcome", "ilL - Password reset"])
		self.assertEqual(doc.insert.call_count, 2)


class PortalShipmentEmail(unittest.TestCase):
	def test_shipment_email_lists_tracking_and_links_the_order(self):
		tracker = types.SimpleNamespace(
			tracking=lambda dn: {"carrier": "FedEx", "number": "7781", "url": "https://fedex.test/7781"}
		)
		with load_service(ROOT + ".portal.notifications", {ROOT + ".portal.shipment_tracking": tracker}) as (
			module,
			frappe,
		):
			frappe.utils.format_date = lambda value: "November 6, 2026"
			order = Record(name="SO-1", po_no="PO <9>", per_delivered=40, ill_fixture_schedule="SCH-1")
			frappe.get_doc.return_value = order
			frappe.db.get_value = MagicMock(return_value="Glick Residence")
			module.order_recipients = MagicMock(return_value={"buyer@example.com"})
			module.notify_user = MagicMock()
			note = Record(name="DN-1", is_return=0, posting_date="2026-11-06")
			note.items = [Record(against_sales_order="SO-1")]  # shadows dict.items, like a Document
			module.notify_shipment(note)
			args = module.notify_user.call_args.args
			self.assertEqual(args[2], "Your order has shipped: SO-1")
			body = args[3]
			for text in (
				"Part of your order is on the way",
				"Glick Residence",
				"PO &lt;9&gt;",
				"FedEx",
				"https://fedex.test/7781",
				"Track shipment",
				SITE + "/portal/orders/SO-1",
				"November 6, 2026",
				"shipping updates",
			):
				self.assertIn(text, body)
			self.assertIsNone(LEAKS.search(body))

	def test_order_links_encode_names_with_spaces_and_slashes(self):
		name = "ilL-SAL-ORD-Backcountry Electric / LINX Audio Visual-00001"
		encoded = (
			SITE + "/portal/orders/ilL-SAL-ORD-Backcountry%20Electric%20%2F%20LINX%20Audio%20Visual-00001"
		)
		tracker = types.SimpleNamespace(tracking=lambda dn: {"carrier": None, "number": None, "url": None})
		with load_service(ROOT + ".portal.notifications", {ROOT + ".portal.shipment_tracking": tracker}) as (
			module,
			frappe,
		):
			frappe.utils.format_date = lambda value: "November 6, 2026"
			order = Record(name=name, per_delivered=100)
			frappe.get_doc.return_value = order
			frappe.db.get_value = MagicMock(return_value=None)
			module.order_recipients = MagicMock(return_value={"buyer@example.com"})
			module.notify_user = MagicMock()
			note = Record(name="DN-1", is_return=0)
			note.items = [Record(against_sales_order=name)]
			module.notify_shipment(note)
			shipped = module.notify_user.call_args.args[3]
			module.notify_order_review(order, Record(name="REQ-1", state="APPROVED", modified="m"))
			reviewed = module.notify_user.call_args.args[3]
		for body in (shipped, reviewed):
			links = [href for href in re.findall(r'href="([^"]*)"', body) if "/portal/orders/" in href]
			self.assertIn(encoded, links)
			for href in links:
				self.assertNotIn(" ", href)


if __name__ == "__main__":
	unittest.main()
