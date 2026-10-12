"""Custom fields listed only in the module-level fixtures never reach a site.

Frappe's fixture sync reads ``<app>/fixtures`` (illumenate_lighting/fixtures), not the
module's ``illumenate_lighting/illumenate_lighting/fixtures``. Every Custom Field in the
module-level custom_field.json therefore needs a patch that creates it.
"""

import json
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from test_services import ROOT, load_service

MODULE_FIELDS = Path("illumenate_lighting/illumenate_lighting/fixtures/custom_field.json")
PATCHES = Path("illumenate_lighting/patches")
NEW_PATCHES = {
	"add_item_build_id_field": {("Item", "ill_build_id")},
	"add_webflow_contact_form_fields": {
		("CRM Lead", name)
		for name in (
			"webflow_form_details_section",
			"webflow_submitted_at",
			"webflow_contact_form_subject",
			"webflow_contact_form_message",
			"webflow_contact_form_file_url",
			"webflow_project_name",
			"webflow_products_interested",
		)
	},
	"add_work_order_qc_fields": {
		("Work Order", name)
		for name in (
			"ill_section_break",
			"ill_functional_test_result",
			"ill_serial_no",
			"ill_column_break",
			"ill_configured_fixture",
			"ill_test_notes",
		)
	},
}


def run_patch(patch_name, doctype_exists=True):
	"""Return the create_custom_fields call a patch makes, or None."""
	recorder = MagicMock()
	custom_field = type("module", (), {"create_custom_fields": recorder})
	extras = {"frappe.custom.doctype.custom_field.custom_field": custom_field}
	with load_service(f"illumenate_lighting.patches.{patch_name}", extras) as (patch, frappe):
		frappe.db.exists.return_value = doctype_exists
		patch.execute()
	return recorder.call_args


class ModuleLevelCustomFields(unittest.TestCase):
	def test_every_module_level_custom_field_has_a_creating_patch(self):
		sources = [path.read_text() for path in PATCHES.glob("*.py")]
		missing = [
			(row["dt"], row["fieldname"])
			for row in json.loads(MODULE_FIELDS.read_text())
			if not any(f'"{row["fieldname"]}"' in s and f'"{row["dt"]}"' in s for s in sources)
		]
		self.assertEqual(missing, [])

	def test_new_patches_create_their_fields_without_overwriting_site_edits(self):
		for patch_name, expected in NEW_PATCHES.items():
			with self.subTest(patch_name):
				call = run_patch(patch_name)
				fields = {(dt, f["fieldname"]) for dt, rows in call.args[0].items() for f in rows}
				self.assertEqual(fields, expected)
				if patch_name != "add_item_build_id_field":
					self.assertFalse(call.kwargs["update"])

	def test_existing_and_fresh_sites_both_run_the_new_patches(self):
		post_sync = Path("illumenate_lighting/patches.txt").read_text().split("[post_model_sync]", 1)[1]
		install = Path("illumenate_lighting/illumenate_lighting/install.py").read_text()
		for patch_name in NEW_PATCHES:
			self.assertIn(f"illumenate_lighting.patches.{patch_name}", post_sync.splitlines())
			self.assertIn(f"illumenate_lighting.patches.{patch_name} import", install)

	def test_free_text_lead_fields_have_no_140_character_limit(self):
		rows = run_patch("add_webflow_contact_form_fields").args[0]["CRM Lead"]
		types = {f["fieldname"]: f["fieldtype"] for f in rows}
		for name in ("webflow_contact_form_subject", "webflow_contact_form_file_url", "webflow_project_name"):
			self.assertNotEqual(types[name], "Data")

	def test_contact_form_patch_skips_sites_without_frappe_crm(self):
		self.assertIsNone(run_patch("add_webflow_contact_form_fields", doctype_exists=False))


class WebflowSubmittedAt(unittest.TestCase):
	def convert(self, value):
		with load_service(ROOT + ".api.webflow_leads") as (module, frappe):
			frappe.utils.convert_utc_to_system_timezone = lambda utc: utc.astimezone(
				ZoneInfo("America/Los_Angeles")
			)
			return module._submitted_datetime(value)

	def test_webflow_utc_timestamp_becomes_naive_system_time(self):
		self.assertEqual(self.convert("2026-10-08T16:34:56.789Z"), datetime(2026, 10, 8, 9, 34, 56, 789000))

	def test_naive_timestamp_is_kept(self):
		self.assertEqual(self.convert("2026-10-08 16:34:56"), datetime(2026, 10, 8, 16, 34, 56))

	def test_unparseable_timestamp_is_dropped_instead_of_failing_the_lead(self):
		self.assertIsNone(self.convert("last Tuesday"))


if __name__ == "__main__":
	unittest.main()
