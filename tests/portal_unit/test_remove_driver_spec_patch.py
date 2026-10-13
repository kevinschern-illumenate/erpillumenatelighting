"""The one-time removal of PS-UNIV-24V-100W-IP66 never edits a pinned build beyond its driver pointer."""

import unittest
from unittest.mock import MagicMock, call

from test_services import Record, load_service

PATCH = "illumenate_lighting.patches.remove_driver_spec_ps_univ_24v_100w_ip66"
DRIVER = "PS-UNIV-24V-100W-IP66"


class LinkExistsError(Exception):
	pass


def site(frappe, rows):
	"""Wire get_all to a schema of Link fields and the rows that point at the driver."""
	fields = {
		"DocField": [Record(parent=doctype, fieldname=field) for doctype, field in rows],
		"Custom Field": [],
	}
	frappe.LinkExistsError = LinkExistsError
	frappe.get_traceback = MagicMock(return_value="traceback")
	frappe.log_error = MagicMock()
	frappe.delete_doc = MagicMock()
	frappe.db.exists.return_value = True
	frappe.db.table_exists.return_value = True
	frappe.get_all.side_effect = lambda doctype, **kw: (
		fields[doctype] if doctype in fields else rows[(doctype, next(iter(kw["filters"])))]
	)


class RemoveDriverSpec(unittest.TestCase):
	def test_clears_build_pointer_and_removes_catalog_references(self):
		with load_service(PATCH) as (module, frappe):
			site(
				frappe,
				{
					("ilL-Spec-Driver", "item"): [],
					("ilL-Child-LED-Sheet-Group", "driver_spec"): ["row-1"],
					("ilL-Rel-Driver-Eligibility", "driver_spec"): ["elig-1"],
					("ilL-Child-Driver-Template-Variant", "driver_spec"): ["variant-1"],
				},
			)
			module.execute()
			frappe.db.set_value.assert_called_once_with(
				"ilL-Child-LED-Sheet-Group", "row-1", "driver_spec", None, update_modified=False
			)
			frappe.db.delete.assert_called_once_with(
				"ilL-Child-Driver-Template-Variant", {"name": "variant-1"}
			)
			self.assertEqual(
				frappe.delete_doc.call_args_list,
				[
					call("ilL-Rel-Driver-Eligibility", "elig-1", ignore_permissions=True, force=True),
					call("ilL-Spec-Driver", DRIVER, ignore_permissions=True),
				],
			)
			frappe.db.commit.assert_called_once()

	def test_unrecognised_reference_leaves_everything_in_place(self):
		with load_service(PATCH) as (module, frappe):
			site(
				frappe,
				{
					("ilL-Child-LED-Sheet-Group", "driver_spec"): ["row-1"],
					("Some Other Doctype", "driver"): ["other-1"],
				},
			)
			module.execute()
			frappe.db.set_value.assert_not_called()
			frappe.delete_doc.assert_not_called()
			frappe.log_error.assert_called_once()

	def test_remaining_link_rolls_back_without_failing_the_deploy(self):
		with load_service(PATCH) as (module, frappe):
			site(frappe, {("ilL-Child-LED-Sheet-Group", "driver_spec"): ["row-1"]})
			frappe.delete_doc.side_effect = LinkExistsError("still linked")
			module.execute()
			frappe.db.rollback.assert_called_once()
			frappe.db.commit.assert_not_called()
			frappe.log_error.assert_called_once()

	def test_already_removed_is_a_no_op(self):
		with load_service(PATCH) as (module, frappe):
			frappe.db.exists.return_value = False
			module.execute()
			frappe.get_all.assert_not_called()


if __name__ == "__main__":
	unittest.main()
