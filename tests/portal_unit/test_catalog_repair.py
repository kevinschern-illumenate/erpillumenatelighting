"""Catalog Configurability report and the template back-link repair."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service

BACKLINKS = {
	"ilL-Fixture-Template": [
		Record(name="F1", webflow_product="linear-missing", is_active=1),
		Record(name="F2", webflow_product="linear-other", is_active=1),
		Record(name="F3", webflow_product="linear-retired", is_active=0),
	],
	"ilL-Tape-Neon-Template": [
		Record(name="T1", webflow_product="neon-wrong-category", is_active=1, product_category="LED Tape"),
	],
	"ilL-LED-Sheet-Template": [],
}
PRODUCTS = [
	Record(
		name="linear-missing", product_name="Linear A", product_type="Fixture Template", is_configurable=0
	),
	Record(
		name="linear-other",
		product_name="Linear B",
		product_type="Fixture Template",
		is_configurable=1,
		fixture_template="F9",
	),
	Record(name="neon-wrong-category", product_name="Neon", product_type="LED Neon", is_configurable=1),
]


def fake_get_all(doctype, filters=None, **kwargs):
	if doctype == "ilL-Webflow-Product":
		return [row for row in PRODUCTS if row.name in filters["name"][1]]
	return BACKLINKS[doctype]


class CatalogRepair(unittest.TestCase):
	def test_dry_run_plans_links_and_reports_conflicts_without_saving(self):
		with load_service(ROOT + ".portal.catalog_repair") as (service, frappe):
			frappe.get_all.side_effect = fake_get_all
			result = service.link_configurable_products(dry_run=1)
			frappe.get_doc.assert_not_called()
		self.assertTrue(result["dry_run"])
		self.assertEqual(
			result["changes"],
			[
				{
					"product": "linear-missing",
					"product_name": "Linear A",
					"changes": {"fixture_template": "F1", "is_configurable": 1},
				}
			],
		)
		messages = {row["product"]: row["message"] for row in result["conflicts"]}
		self.assertIn("links F9", messages["linear-other"])
		self.assertIn("does not belong to this product type", messages["neon-wrong-category"])
		self.assertNotIn("linear-retired", messages)

	def test_apply_saves_each_change_and_rolls_back_a_failed_product(self):
		with load_service(ROOT + ".portal.catalog_repair") as (service, frappe):
			frappe.get_all.side_effect = fake_get_all
			doc = MagicMock()
			frappe.get_doc.return_value = doc
			result = service.link_configurable_products(dry_run=0)
			doc.update.assert_called_once_with({"fixture_template": "F1", "is_configurable": 1})
			doc.save.assert_called_once_with(ignore_permissions=True)
			self.assertEqual(len(result["changes"]), 1)

			doc.save.side_effect = ValueError("Template F1 has no tape offerings")
			result = service.link_configurable_products(dry_run=0)
			frappe.db.rollback.assert_called_once_with(save_point="ill_catalog_repair")
			self.assertEqual(result["changes"], [])
			self.assertEqual(result["errors"][0]["message"], "Template F1 has no tape offerings")

	def test_several_templates_pointing_at_one_product_need_a_person(self):
		with load_service(ROOT + ".portal.catalog_repair") as (service, _frappe):
			backlinks = {
				"p": [("ilL-Fixture-Template", "F1", True, None), ("ilL-Fixture-Template", "F2", True, None)]
			}
			product = Record(name="p", product_type="Fixture Template", is_configurable=1)
			changes, conflicts = service._plan(product, backlinks)
		self.assertEqual(changes, {})
		self.assertIn("F1, F2", conflicts[0])


class ConfigurabilityReport(unittest.TestCase):
	def test_rows_explain_each_reason_and_skip_configurable_products(self):
		products = [
			Record(
				name="ok",
				product_name="Works",
				product_type="Fixture Template",
				is_active=1,
				is_configurable=1,
				fixture_template="F1",
			),
			Record(
				name="missing",
				product_name="No link",
				product_type="Fixture Template",
				is_active=1,
				is_configurable=1,
			),
			Record(
				name="broken",
				product_name="Bad options",
				product_type="LED Tape",
				is_active=1,
				is_configurable=1,
				tape_neon_template="T1",
			),
		]
		options = [
			Record(parent="ok", option_step=4, allowed_values_json='{"lensMap": {}}'),
			Record(parent="broken", option_step=3, allowed_values_json="[1, 2]"),
		]
		catalog = types.SimpleNamespace(
			_template_activity=lambda rows: {},
			_is_template_active=lambda product, activity: True,
		)
		repair = types.SimpleNamespace(
			template_backlinks=lambda: {"missing": [("ilL-Fixture-Template", "F7", True, None)]}
		)
		deps = {
			ROOT + ".api.product_catalog": catalog,
			ROOT + ".portal.catalog_repair": repair,
			ROOT + ".portal.rollout": types.SimpleNamespace(reason=lambda family, public=False: "ok"),
		}
		with load_service(ROOT + ".report.catalog_configurability.catalog_configurability", deps) as (
			report,
			frappe,
		):
			frappe._dict = Record
			frappe.get_all.side_effect = lambda doctype, **kwargs: (
				products if doctype == "ilL-Webflow-Product" else options
			)
			_columns, rows = report.execute({})
		by_product = {row["product"]: row for row in rows}
		self.assertEqual(set(by_product), {"missing", "broken"})
		self.assertEqual(by_product["missing"]["reason"], "missing_template")
		self.assertIn("Apply repair to link F7", by_product["missing"]["fix"])
		self.assertEqual(by_product["broken"]["reason"], "invalid_options:3")
		self.assertIn("step 3", by_product["broken"]["fix"])


if __name__ == "__main__":
	unittest.main()
