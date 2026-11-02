"""Patch: the Webflow Product's site Custom Fields move to fields that ship with the app."""

import unittest
from unittest.mock import MagicMock

from test_services import Record, load_service

PATCH = "illumenate_lighting.patches.rename_webflow_product_custom_fields"


class RenamePatch(unittest.TestCase):
	def run_patch(self, products, template_images):
		with load_service(PATCH) as (module, frappe):
			frappe.db.has_column = lambda doctype, column: True
			frappe.get_all = MagicMock(return_value=products)
			order = []
			frappe.db.sql.side_effect = lambda *args, **kwargs: order.append("copy")
			frappe.delete_doc = MagicMock(side_effect=lambda *args, **kwargs: order.append("delete"))
			frappe.clear_cache = MagicMock()
			frappe.log_error = MagicMock()
			frappe.db.set_value = MagicMock()

			def get_value(doctype, name, field, *args, **kwargs):
				if doctype == "Custom Field":
					return f"{name['dt']}-{name['fieldname']}"
				return template_images.get((doctype, name))

			frappe.db.get_value = get_value
			module.execute()
			frappe.order = order
			return frappe

	def test_values_and_rows_move_before_the_custom_fields_go(self):
		frappe = self.run_patch([], {})
		sql = [call.args[0] for call in frappe.db.sql.call_args_list]
		self.assertTrue(any("set `webflow_status` = `custom_webflow_status`" in q for q in sql))
		self.assertTrue(any("set `web_product_category` = `custom_web_product_category`" in q for q in sql))
		self.assertTrue(any("set `webflow_template_status` = `custom_template_status`" in q for q in sql))
		self.assertTrue(any("set `webflow_description` = `custom_webflow_description`" in q for q in sql))
		self.assertTrue(any("webflow_badge = '' where webflow_badge = 'None'" in q for q in sql))
		moved = [call.args[1] for call in frappe.db.sql.call_args_list if len(call.args) > 1]
		self.assertIn(("webflow_specifications", "ilL-Webflow-Product", "custom_spec_custom"), moved)
		deleted = {call.args[1] for call in frappe.delete_doc.call_args_list}
		for fieldname in ("custom_webflow_status", "custom_dimensions_image_2", "custom_column_break_lgzvl"):
			self.assertIn(f"ilL-Webflow-Product-{fieldname}", deleted)
		self.assertIn("ilL-Child-Webflow-Kit-Component-custom_webflow_title", deleted)
		# Every copy happens before the first delete.
		self.assertEqual(frappe.order, sorted(frappe.order, key=lambda step: step == "delete"))
		self.assertIn("delete", frappe.order)

	def test_dark_dimension_images_move_to_an_empty_template_and_the_rest_are_listed(self):
		products = [
			Record(name="kit-a", custom_dimensions_image_2="/files/a.png", kit_template="KIT-A"),
			Record(name="kit-b", custom_dimensions_image_2="/files/b.png", kit_template="KIT-B"),
			Record(name="loose", custom_dimensions_image_2="/files/c.png"),
		]
		frappe = self.run_patch(products, {("ilL-Extrusion-Kit-Template", "KIT-B"): "/files/other.png"})
		frappe.db.set_value.assert_called_once_with(
			"ilL-Extrusion-Kit-Template", "KIT-A", "dimensions_image", "/files/a.png", update_modified=False
		)
		message = frappe.log_error.call_args.kwargs["message"]
		self.assertIn("kit-b: ilL-Extrusion-Kit-Template KIT-B already has /files/other.png", message)
		self.assertIn("loose: no template", message)


if __name__ == "__main__":
	unittest.main()
