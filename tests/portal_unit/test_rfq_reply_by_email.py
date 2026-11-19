"""RFQ emails: suppliers reply by email, with no portal link and no Website User / password email."""

import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from jinja2 import DebugUndefined
from jinja2.sandbox import SandboxedEnvironment
from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.email_templates import library

CORE = "erpnext.buying.doctype.request_for_quotation.request_for_quotation"


class CoreRequestForQuotation(Record):
	"""ERPNext v16's send path, cut down to the calls the override touches."""

	def get_link(self):
		raise AssertionError("Please add Request for Quotation to the sidebar in Portal Settings.")

	def update_supplier_contact(self, rfq_supplier, link):
		raise AssertionError("ERPNext would create a Website User here")

	def set(self, key, value):
		self[key] = value

	def send_to_supplier(self):
		for row in self.suppliers:
			update_password_link, contact = self.update_supplier_contact(row, self.get_link())
			self.supplier_rfq_mail(row, update_password_link, self.get_link())
			if not row.contact:
				row.contact = contact

	def supplier_rfq_mail(self, data, update_password_link, rfq_link, preview=False):
		args = {
			"supplier_name": data.supplier_name,
			"update_password_link": f'<a href="{update_password_link}">Set Password</a>',
			"portal_link": f'<a href="{rfq_link}"> Submit your Quotation </a>',
			"user_fullname": "Sam Rivera",
		}
		source = self.mfs_html if self.use_html else self.message_for_supplier
		rendered = SandboxedEnvironment(undefined=DebugUndefined).from_string(source).render(**args)
		self.sent.append({"to": data.email_id, "message": rendered, "preview": preview})
		return {"message": rendered}


def load_rfq():
	core = types.ModuleType(CORE)
	core.RequestForQuotation = CoreRequestForQuotation
	return load_service(ROOT + ".email_templates.rfq", {CORE: core})


def rfq(message, suppliers, use_html=1):
	doc_fields = {"mfs_html": message} if use_html else {"message_for_supplier": message}
	return dict(use_html=use_html, suppliers=suppliers, sent=[], **doc_fields)


OLD_STYLE = (
	"<p>Hello {{ supplier_name }},</p>\n"
	"{% if portal_link is defined and portal_link %}<p>{{ portal_link }}</p>{% endif %}\n"
	"<p>{{ portal_link | safe }} {{update_password_link}}</p>\n"
	"<p>Thank you, {{ user_fullname }}</p>"
)


class StripPortalLinks(unittest.TestCase):
	def test_variables_inside_tags_become_empty_and_text_is_untouched(self):
		with load_rfq() as (module, _frappe):
			stripped = module.strip_portal_links(OLD_STYLE + " portal_link in prose")
		self.assertNotRegex(stripped, r"\{[{%][^}]*\b(portal_link|update_password_link)\b")
		self.assertIn("portal_link in prose", stripped)
		self.assertIn("{{ supplier_name }}", stripped)
		with load_rfq() as (module, _frappe):
			self.assertIsNone(module.strip_portal_links(None))
			self.assertEqual(module.strip_portal_links(""), "")


class SendToSupplier(unittest.TestCase):
	def send(self, message, row, use_html=1, existing_contacts=(), linked=False):
		with load_rfq() as (module, frappe):
			frappe.get_all.return_value = list(existing_contacts)
			frappe.db.exists.return_value = linked
			contact = MagicMock()
			contact.name = "New Contact"
			frappe.new_doc = MagicMock(return_value=contact)
			frappe.log_error = MagicMock()
			frappe.get_traceback = lambda: ""
			doc = module.ILLRequestForQuotation(rfq(message, [row], use_html))
			doc.send_to_supplier()
			return doc, frappe, contact

	def row(self, **values):
		return Record(
			{"supplier": "Linea", "supplier_name": "Linea Co", "email_id": "q@linea.test", **values}
		)

	def test_old_message_sends_without_portal_buttons_and_is_not_changed(self):
		doc, frappe, _contact = self.send(OLD_STYLE, self.row(contact="Cathy"))
		message = doc.sent[0]["message"]
		self.assertNotIn("Submit your Quotation", message)
		self.assertNotIn("Set Password", message)
		self.assertNotIn("{{", message)
		self.assertIn("Hello Linea Co", message)
		self.assertIn("Sam Rivera", message)
		self.assertEqual(doc.mfs_html, OLD_STYLE)
		frappe.new_doc.assert_not_called()

	def test_plain_text_message_is_stripped_too(self):
		doc, _frappe, _contact = self.send("Hi {{ portal_link }}", self.row(contact="Cathy"), use_html=0)
		self.assertEqual(doc.sent[0]["message"], "Hi ")
		self.assertEqual(doc.message_for_supplier, "Hi {{ portal_link }}")

	def test_new_supplier_email_gets_a_contact_and_no_user(self):
		doc, frappe, contact = self.send("Hi", self.row())
		frappe.new_doc.assert_called_once_with("Contact")
		self.assertEqual(contact.first_name, "Linea Co")
		contact.append.assert_any_call("links", {"link_doctype": "Supplier", "link_name": "Linea"})
		contact.append.assert_any_call("email_ids", {"email_id": "q@linea.test", "is_primary": 1})
		contact.insert.assert_called_once_with(ignore_permissions=True)
		self.assertEqual(doc.suppliers[0].contact, "New Contact")
		for call in frappe.get_doc.call_args_list + frappe.new_doc.call_args_list:
			self.assertNotEqual(call.args[:1], ("User",))

	def test_existing_contact_for_the_email_is_reused(self):
		doc, frappe, _contact = self.send("Hi", self.row(), existing_contacts=["Cathy"], linked=True)
		frappe.new_doc.assert_not_called()
		self.assertEqual(doc.suppliers[0].contact, "Cathy")

	def test_contact_failure_still_sends(self):
		with load_rfq() as (module, frappe):
			frappe.get_all.side_effect = RuntimeError("db")
			frappe.log_error = MagicMock()
			frappe.get_traceback = lambda: ""
			doc = module.ILLRequestForQuotation(rfq("Hi", [self.row()]))
			doc.send_to_supplier()
		self.assertEqual(len(doc.sent), 1)
		frappe.log_error.assert_called_once()


class Patch(unittest.TestCase):
	# The RFQ body as shipped before this change; the live template and draft RFQs hold this text.
	OLD = (Path(__file__).parent / "fixtures" / "rfq_request_portal_link.html").read_text(encoding="utf-8")

	def run_patch(self, template, drafts):
		with load_service("illumenate_lighting.patches.rfq_reply_by_email") as (module, frappe):
			frappe.db.exists.return_value = template is not None
			frappe.db.get_value.return_value = template
			frappe.get_all.return_value = [Record(name=name, mfs_html=html) for name, html in drafts]
			result = module.execute()
			return module, frappe, result

	def test_shipped_body_becomes_the_reply_by_email_body(self):
		new = library.BY_SLUG["rfq_request"].body()
		self.assertIn("portal_link", self.OLD)
		module, frappe, result = self.run_patch(self.OLD, [("PUR-RFQ-1", self.OLD), ("PUR-RFQ-2", "Custom")])
		self.assertEqual(module.reply_by_email(self.OLD), new)
		self.assertEqual(module.reply_by_email(new), new)
		self.assertEqual(result, {"template": True, "drafts": ["PUR-RFQ-1"]})
		frappe.db.set_value.assert_any_call("Email Template", module.TEMPLATE, "response_html", new)
		frappe.db.set_value.assert_any_call(
			"Request for Quotation", "PUR-RFQ-1", "mfs_html", new, update_modified=False
		)
		self.assertEqual(frappe.db.set_value.call_count, 2)
		self.assertEqual(
			frappe.get_all.call_args.kwargs["filters"], {"docstatus": 0, "email_template": module.TEMPLATE}
		)

	def test_already_updated_or_missing_template_is_left_alone(self):
		new = library.BY_SLUG["rfq_request"].body()
		for template in (new, None):
			_module, frappe, result = self.run_patch(template, [])
			self.assertEqual(result, {"template": False, "drafts": []})
			frappe.db.set_value.assert_not_called()


if __name__ == "__main__":
	unittest.main()
