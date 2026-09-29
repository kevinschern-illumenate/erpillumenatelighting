"""Public Sheet disclosure and approved standard Item save boundaries."""

import json
import types
import unittest
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service


class PublicSheet(unittest.TestCase):
	def deps(self):
		return {
			"frappe.rate_limiter": types.SimpleNamespace(rate_limit=lambda **kwargs: lambda fn: fn),
			ROOT + ".api.led_sheet_configurator": types.SimpleNamespace(
				_norm_option_key=lambda value: value,
				_calculate_sheet=MagicMock(return_value={"config_hash": "hash"}),
			),
		}

	def template(self):
		return Record(
			name="Snowfield",
			allowed_specs=[Record(spec="SW", is_active=1)],
			allowed_options=[
				Record(option_type="CCT", attribute_link="3000K", option_code="30", is_active=1)
			],
		)

	def test_public_intent_is_allowlisted_and_resolves_choice_codes(self):
		with load_service(ROOT + ".api.public_sheet", self.deps()) as (service, _):
			with patch.object(service, "product_and_template", return_value=(None, self.template())):
				intent = service.request("snow", {"options": {"CCT": "30"}, "include_power_supply": False})
				self.assertEqual(
					intent["selections"],
					{"spec": "SW", "options": {"CCT": "3000K"}, "include_power_supply": False},
				)
				for selections in (
					{"schedule_name": "foreign"},
					{"commercial": True},
					{"spec": "foreign"},
					{"options": {"CCT": "bad"}},
				):
					with self.subTest(selections=selections), self.assertRaises(ValueError):
						service.request("snow", selections)

	def test_preview_cannot_disclose_pricing_materials_or_private_context(self):
		deps = self.deps()
		calculator = deps[ROOT + ".api.led_sheet_configurator"]._calculate_sheet
		calculator.return_value = {
			"config_hash": "hash",
			"msrp": 500,
			"cost": 100,
			"components": ["secret"],
			"panels_needed": 6,
			"include_power_supply": False,
		}
		with load_service(ROOT + ".api.public_sheet", deps) as (service, _):
			with patch.object(service, "product_and_template", return_value=(None, self.template())):
				result = service.preview(
					"snow", {"coverage_width_ft": 3, "coverage_height_ft": 4, "include_power_supply": False}
				)
			self.assertEqual(result["panels_needed"], 6)
			self.assertFalse(result["include_power_supply"])
			self.assertTrue({"msrp", "cost", "components", "build_snapshot_json"}.isdisjoint(result))
			self.assertIs(calculator.call_args.kwargs["commercial"], False)

	def test_pdf_requires_isolated_download_context(self):
		deps = self.deps()
		deps[ROOT + ".api.led_sheet_configurator"].OPTION_FIELD_BY_TYPE = {}
		deps[ROOT + ".api.spec_submittal"] = types.SimpleNamespace(
			generate_filled_sheet_submittal=MagicMock()
		)
		with load_service(ROOT + ".api.public_sheet", deps) as (service, _):
			with self.assertRaisesRegex(ValueError, "isolated"):
				service.generate("snow", {})
			deps[ROOT + ".api.spec_submittal"].generate_filled_sheet_submittal.assert_not_called()


class StandardProducts(unittest.TestCase):
	def deps(self):
		return {
			ROOT + ".portal.access": types.SimpleNamespace(
				require_catalog_access=MagicMock(), can_edit_schedule=lambda doc: doc.name == "S1"
			),
			ROOT + ".portal.configuration": types.SimpleNamespace(
				RECEIPT="Receipt", schedule_context=MagicMock()
			),
		}

	def test_only_enabled_sales_skus_in_stock_units_are_orderable(self):
		with load_service(ROOT + ".portal.standard_products", self.deps()) as (service, frappe):
			product = Record(is_active=1, product_type="Accessory", product_name="Clip", portal_item="CLIP")
			frappe.db.get_value.return_value = Record(
				disabled=0, has_variants=0, is_sales_item=1, item_name="Clip", stock_uom="Nos"
			)
			self.assertEqual(service.choices(product)[0]["stock_uom"], "Nos")
			for field in ("disabled", "has_variants", "is_sales_item"):
				frappe.db.get_value.return_value[field] = 0 if field == "is_sales_item" else 1
				self.assertEqual(service.choices(product), [])
				frappe.db.get_value.return_value[field] = 1 if field == "is_sales_item" else 0

	def test_component_specs_become_accessory_choices_but_kits_need_a_portal_item(self):
		with load_service(ROOT + ".portal.standard_products", self.deps()) as (service, frappe):
			frappe.db.get_value.side_effect = lambda doctype, code, fields, as_dict: Record(
				disabled=0, has_variants=0, is_sales_item=1, item_name=code, stock_uom="Nos"
			)
			frappe.get_doc.side_effect = lambda doctype, name: Record(
				name=name, item=name + "-ITEM", is_active=1, meta=Record(has_field=lambda field: True)
			)
			component = Record(
				is_active=1,
				product_type="Component",
				product_name="Channel",
				profile_spec="PRO",
				lens_spec="LEN",
			)
			self.assertEqual(
				[row["item_code"] for row in service.choices(component)], ["PRO-ITEM", "LEN-ITEM"]
			)
			kit = Record(is_active=1, product_type="Extrusion Kit", product_name="Kit", profile_spec="PRO")
			self.assertEqual(service.choices(kit), [])
			kit["portal_item"] = "KIT"
			self.assertEqual([row["item_code"] for row in service.choices(kit)], ["KIT"])

	def test_fixture_type_is_required_after_trimming(self):
		with load_service(ROOT + ".portal.standard_products", self.deps()) as (service, frappe):
			with self.assertRaisesRegex(ValueError, "fixture type"):
				service.add("clip", "CLIP", "S1", 1, "   ", "old", "retry-key")
			frappe.get_doc.assert_not_called()

	def test_retry_precedes_revision_check_but_changed_content_cannot_reuse_key(self):
		deps = self.deps()
		deps[ROOT + ".portal.configuration"].schedule_context.return_value = Record(modified="new")
		with load_service(ROOT + ".portal.standard_products", deps) as (service, frappe):
			body = {
				"product": "clip",
				"item": "CLIP",
				"quantity": 2,
				"line_id": "L1",
				"location": None,
				"notes": None,
				"modified": "old",
			}
			frappe.db.get_value.return_value = Record(
				request_hash=service.fingerprint(body),
				response_json=json.dumps({"schedule_name": "S1", "line_key": "line"}),
			)
			self.assertTrue(service.add("clip", "CLIP", "S1", 2, "L1", "old", "retry-key")["already_existed"])
			with self.assertRaisesRegex(ValueError, "different content"):
				service.add("clip", "CLIP", "S1", 3, "L1", "old", "retry-key")
			frappe.get_doc.assert_not_called()

	def test_prepare_keeps_native_read_scope_and_only_returns_editable_schedules(self):
		with load_service(ROOT + ".portal.standard_products", self.deps()) as (service, frappe):
			frappe.get_list = MagicMock(return_value=[Record(name="S1"), Record(name="READONLY")])
			frappe.get_doc.side_effect = lambda doctype, name: Record(name=name)
			with patch.object(service, "_product"), patch.object(service, "choices", return_value=[]):
				result = service.prepare("clip", "office")
			self.assertEqual([row.name for row in result["schedules"]], ["S1"])
			self.assertEqual(frappe.get_list.call_args.kwargs["limit_page_length"], 100)
			frappe.get_all.assert_not_called()


class CatalogPricing(unittest.TestCase):
	def test_per_foot_msrp_comes_from_the_family_template(self):
		deps = {ROOT + ".portal.access": types.SimpleNamespace(require_catalog_access=MagicMock())}
		with load_service(ROOT + ".api.product_catalog", deps) as (service, frappe):
			frappe.get_all.side_effect = lambda doctype, **kwargs: {
				"ilL-Fixture-Template": [Record(name="F1", price_per_ft_msrp=30)],
				"ilL-Tape-Neon-Template": [
					Record(name="T1", price_per_ft_msrp=8.5),
					Record(name="N1", price_per_ft_msrp=None),
				],
			}[doctype]
			products = [
				Record(name="linear", product_type="Fixture Template", fixture_template="F1"),
				Record(name="tape", product_type="LED Tape", tape_neon_template="T1"),
				Record(name="neon", product_type="LED Neon", tape_neon_template="N1"),
				Record(name="sheet", product_type="LED Sheet", led_sheet_template="S1"),
				Record(name="clip", product_type="Accessory"),
			]
			self.assertEqual(service._per_foot_prices(products), {"linear": 30, "tape": 8.5})
			self.assertEqual(
				sorted(call.args[0] for call in frappe.get_all.call_args_list),
				["ilL-Fixture-Template", "ilL-Tape-Neon-Template"],
			)
