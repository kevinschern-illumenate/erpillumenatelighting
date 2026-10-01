"""Catalog facet counts follow the dealer's other filters and search (disjunctive facets)."""

import types
import unittest
from unittest.mock import MagicMock

from test_services import ROOT, Record, load_service


def deps():
	return {ROOT + ".portal.access": types.SimpleNamespace(require_catalog_access=MagicMock())}


class CatalogScope(unittest.TestCase):
	def test_scope_matches_every_filter_except_the_excluded_one(self):
		with load_service(ROOT + ".api.product_catalog", deps()) as (service, _frappe):
			filters, error = service._clean_filters(
				'{"product_type": "LED Tape", "CCT": ["3000K", "90"], "series": []}'
			)
			self.assertIsNone(error)
			self.assertEqual(filters, {"product_type": ["LED Tape"], "CCT": ["3000K", "90"]})
			joins, where, params = service._scope(filters, " cove ")
			self.assertIn("`tabilL-Webflow-Product`.`product_type` IN (%(f0_0)s)", where)
			self.assertIn("display_label IN (%(f1_0)s, %(f1_1)s)", joins)
			self.assertEqual(params["f1_type"], "CCT")
			self.assertEqual(params["search"], "%cove%")
			joins, where, params = service._scope(filters, "", exclude="CCT")
			self.assertEqual(joins, "")
			self.assertNotIn("f1_type", params)

	def test_rejects_unusable_filter_payloads(self):
		with load_service(ROOT + ".api.product_catalog", deps()) as (service, _frappe):
			self.assertEqual(service._clean_filters("[1]")[1], "Filters must be an object")
			self.assertIn("at most 50", service._clean_filters({"CCT": [3000]})[1])
			result = service.get_catalog_filter_options(filters='{"CCT": [3000]}')
			self.assertFalse(result["success"])


class FacetCounts(unittest.TestCase):
	def run_options(self, filters=None, search=""):
		calls = []

		def sql(query, params=None, as_dict=False):
			calls.append((query, params or {}))
			if "p.product_type" in query:
				return [
					Record(product_type="LED Tape", cnt=4),
					Record(product_type="Fixture Template", cnt=2),
				]
			if "attribute_type = %(facet_type)s" in query:
				return [Record(attribute_type="CCT", display_label="2700K", cnt=1)]
			if "al.attribute_type" in query:
				return [
					Record(attribute_type="Finish", display_label="white", cnt=3),
					Record(attribute_type="Finish", display_label="Black", cnt=2),
					Record(attribute_type="Finish", display_label=None, cnt=9),
				]
			if "p.`series`" in query:
				return [Record(value="Eldorado", cnt=2)]
			return []

		with load_service(ROOT + ".api.product_catalog", deps()) as (service, frappe):
			frappe.db.sql = MagicMock(side_effect=sql)
			result = service.get_catalog_filter_options(filters=filters, search=search)
		return result, calls

	def test_without_filters_counts_every_active_product_in_the_existing_shape(self):
		result, calls = self.run_options()
		self.assertEqual(len(calls), 4)
		self.assertEqual(
			result["product_types"],
			[{"value": "Fixture Template", "count": 2}, {"value": "LED Tape", "count": 4}],
		)
		self.assertEqual(
			[group["attribute_type"] for group in result["filters"]],
			["series", "Finish"],
		)
		self.assertEqual(result["filters"][0]["label"], "Series")
		self.assertEqual(
			result["filters"][1]["options"], [{"value": "Black", "count": 2}, {"value": "white", "count": 3}]
		)

	def test_each_group_ignores_only_its_own_selection_and_keeps_selected_zero_values(self):
		result, calls = self.run_options(
			filters={"CCT": ["3000K"], "product_type": ["LED Neon"]}, search="cove"
		)
		_type_query, type_params = calls[0]
		self.assertNotIn("LED Neon", type_params.values())
		self.assertIn("3000K", type_params.values())
		_cct_query, cct_params = calls[1]
		self.assertEqual(cct_params["facet_type"], "CCT")
		self.assertNotIn("3000K", cct_params.values())
		self.assertIn("LED Neon", cct_params.values())
		rest_query, rest_params = calls[2]
		self.assertIn("NOT IN (%(facet_type_0)s)", rest_query)
		self.assertEqual(rest_params["facet_type_0"], "CCT")
		self.assertTrue(all(params.get("search") == "%cove%" for _query, params in calls))
		self.assertIn({"value": "LED Neon", "count": 0}, result["product_types"])
		cct = next(group for group in result["filters"] if group["attribute_type"] == "CCT")
		self.assertEqual(cct["options"], [{"value": "2700K", "count": 1}, {"value": "3000K", "count": 0}])


if __name__ == "__main__":
	unittest.main()


class FinderScope(unittest.TestCase):
	def test_restrict_names_never_interpolates_user_values(self):
		with load_service(ROOT + '.api.product_catalog', deps()) as (service, _):
			_, where, params = service._scope({}, '', restrict_names=["P' OR 1=1", 'P2'])
			self.assertIn('.name IN %(finder_names)s', where)
			self.assertNotIn("P' OR 1=1", where)
			self.assertIn("P' OR 1=1", params["finder_names"])
			self.assertIn('1=0', service._scope({}, '', restrict_names=[])[1])

	def test_companion_facet_queries_keep_session_scope(self):
		with load_service(ROOT + '.api.product_catalog', deps()) as (service, frappe):
			service._finder_scope = MagicMock(return_value=(['DRIVER'], {}, {}))
			frappe.db.sql.return_value = []
			service.get_catalog_filter_options(finder='TOKEN', view='companions')
			service._finder_scope.assert_called_with('TOKEN', 'companions')
			for call in frappe.db.sql.call_args_list:
				self.assertIn('DRIVER', call.args[1]['finder_names'])
