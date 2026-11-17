# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Helpdesk ticket links behave on sites with and without Helpdesk installed."""

import frappe
from frappe.tests import IntegrationTestCase

from illumenate_lighting.illumenate_lighting import helpdesk_links


class TestHelpdeskLinks(IntegrationTestCase):
	def test_dashboard_lists_tickets_only_with_helpdesk(self):
		data = helpdesk_links.quotation_dashboard({"fieldname": "prevdoc_docname", "transactions": []})
		groups = [t for t in data["transactions"] if "HD Ticket" in t.get("items", [])]
		if helpdesk_links.helpdesk_installed():
			self.assertEqual(len(groups), 1)
			self.assertEqual(data["non_standard_fieldnames"]["HD Ticket"], "ill_quotation")
		else:
			self.assertEqual(groups, [])

	def test_pdf_url_is_blank_for_unsupported_or_missing_documents(self):
		self.assertEqual(helpdesk_links.ill_print_pdf_url("Quotation", None), "")
		self.assertEqual(helpdesk_links.ill_print_pdf_url("User", "Administrator"), "")
		self.assertEqual(helpdesk_links.ill_print_pdf_url("Quotation", "no-such-quotation"), "")

	def test_pdf_url_carries_a_share_key(self):
		name = frappe.db.get_value("Quotation", {"docstatus": ["<", 2]}, "name")
		if not name:
			self.skipTest("no Quotation on this site")
		url = helpdesk_links.ill_print_pdf_url("Quotation", name, print_format="Standard")
		self.assertIn("frappe.utils.print_format.download_pdf", url)
		self.assertIn("key=", url)
		self.assertIn("format=Standard", url)

	def test_ensure_fields_is_a_no_op_without_helpdesk(self):
		if helpdesk_links.helpdesk_installed():
			self.skipTest("Helpdesk is installed")
		helpdesk_links.ensure_fields()
		self.assertFalse(frappe.db.exists("Custom Field", {"dt": "HD Ticket"}))

	def test_project_and_schedule_dashboards_use_ticket_fields(self):
		for override, doctype, fieldname in (
			(helpdesk_links.project_dashboard, "ilL-Project", "ill_project"),
			(
				helpdesk_links.fixture_schedule_dashboard,
				"ilL-Project-Fixture-Schedule",
				"ill_fixture_schedule",
			),
		):
			data = override({})
			if helpdesk_links.helpdesk_installed():
				self.assertEqual(data["non_standard_fieldnames"]["HD Ticket"], fieldname, doctype)
			else:
				self.assertEqual(data, {})

	def test_pdf_url_is_blank_for_project_documents(self):
		self.assertEqual(helpdesk_links.ill_print_pdf_url("ilL-Project", "anything"), "")

	def test_fill_upstream_takes_project_from_schedule(self):
		schedule = frappe.db.get_value(
			"ilL-Project-Fixture-Schedule",
			{"ill_project": ["is", "set"]},
			["name", "ill_project"],
			as_dict=True,
		)
		if not schedule:
			self.skipTest("no fixture schedule with a project on this site")
		doc = frappe._dict(ill_fixture_schedule=schedule.name)
		helpdesk_links.fill_upstream(doc)
		self.assertEqual(doc.ill_project, schedule.ill_project)

		doc = frappe._dict(ill_fixture_schedule=schedule.name, ill_project="kept")
		helpdesk_links.fill_upstream(doc)
		self.assertEqual(doc.ill_project, "kept")

	def test_legacy_sidebar_flag_means_sales_fields_only(self):
		frappe.db.set_default("ill_helpdesk_sidebar_seeded", "1")
		self.assertEqual(helpdesk_links._seeded_fields(), set(helpdesk_links.SALES_FIELDS.values()))
		frappe.db.set_default("ill_helpdesk_sidebar_seeded", "ill_project,ill_quotation")
		self.assertEqual(helpdesk_links._seeded_fields(), {"ill_project", "ill_quotation"})
