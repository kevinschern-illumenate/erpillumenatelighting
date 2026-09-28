"""Exercise form-encoded configurator inputs through Frappe's real dispatcher.

These are transport/validation tests, not approvals of site engineering data.
No whitelist decorator, argument validator or request dispatcher is mocked.
"""

import inspect
from unittest.mock import patch
from urllib.parse import urlencode

import frappe
from frappe.handler import execute_cmd
from werkzeug.wrappers import Request

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # Frappe v15
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase


API = "illumenate_lighting.illumenate_lighting.api."
MISSING = "ILL-TRANSPORT-NOT-CONFIGURED"
LINEAR = {
	"fixture_template_code": MISSING,
	"finish_code": "",
	"lens_appearance_code": "",
	"mounting_method_code": "",
	"endcap_color_code": "",
	"environment_rating_code": "",
	"tape_offering_id": MISSING,
	"segments_json": '[{"requested_length_mm":1000,"end_type":"Endcap"}]',
	"include_power_supply": "false",
	"_skip_record_creation": "true",
}


class TestConfiguratorTransport(IntegrationTestCase):
	def call_form(self, method, args):
		# Match jQuery form encoding: null becomes an empty string. The real
		# request parser produces strings, not the numbers in our JS objects.
		body = urlencode({key: "" if value is None else value for key, value in args.items()})
		request = Request.from_values(
			path="/api/method/" + API + method,
			method="POST",
			data=body,
			content_type="application/x-www-form-urlencoded",
		)
		with (
			patch.object(frappe.local, "request", request, create=True),
			patch.object(frappe.local, "form_dict", frappe._dict(request.form)),
		):
			return execute_cmd(API + method)

	def test_linear_form_payloads_reach_domain_validation(self):
		for override in ("omitted", None, "", "12.5"):
			for method in (
				"validate_and_quote_multisegment",
				"validate_and_quote_multisegment_with_output",
				"validate_and_quote",
			):
				with self.subTest(method=method, override=override):
					args = dict(LINEAR)
					if override != "omitted":
						args["override_max_run_ft"] = override
					if method.endswith("with_output"):
						args.update(led_package_code="", delivered_output_value="100")
					elif method == "validate_and_quote":
						args.update(
							requested_overall_length_mm="1000",
							endcap_style_start_code="",
							endcap_style_end_code="",
							power_feed_type_code="",
						)
					result = self.call_form("configurator_engine." + method, args)
					self.assertFalse(result["is_valid"])
					self.assertIn("not found", str(result["messages"]))

	def test_empty_output_selection_returns_a_validation_result(self):
		for method in ("validate_and_quote_multisegment_with_output", "auto_select_tape_for_configuration"):
			with self.subTest(method=method):
				result = self.call_form(
					"configurator_engine." + method,
					{**LINEAR, "led_package_code": "", "delivered_output_value": ""},
				)
				self.assertIn("Invalid", str(result))
				self.assertFalse(result.get("success", result.get("is_valid")))

	def test_tape_neon_and_webflow_optional_overrides(self):
		for override in ("omitted", None, "", "12.5"):
			for method in (
				"tape_neon_configurator.validate_tape_configuration",
				"tape_neon_configurator.validate_neon_configuration",
				"webflow_configurator.validate_configuration",
			):
				with self.subTest(method=method, override=override):
					args = {
						"selections": "{}",
						"segments_json": "[]",
						"product_slug": MISSING,
						"include_power_supply": "false",
						"_skip_record_creation": "true",
					}
					if override != "omitted":
						args["override_max_run_ft"] = override
					result = self.call_form(method, args)
					self.assertFalse(result.get("success", result.get("is_valid")))
					self.assertTrue("Missing required" in result["error"] or "not found" in result["error"])

	def test_optional_schedule_indices_and_session_quantity(self):
		methods = (
			"portal.save_configured_fixture_to_schedule",
			"extrusion_kit_configurator.save_kit_to_schedule",
			"tape_neon_configurator.save_tape_to_schedule",
			"tape_neon_configurator.save_tape_neon_template_to_schedule",
			"webflow_schedule.add_from_session",
		)
		for method in methods:
			field = "quantity" if method.endswith("add_from_session") else "line_idx"
			for value in (None, "", "2", "1.5", "-1", "Infinity", "invalid"):
				with self.subTest(method=method, value=value):
					result = self.call_form(
						method,
						{
							field: value,
							"schedule_name": MISSING,
							"schedule_id": MISSING,
							"session_id": MISSING,
							"configured_fixture_id": MISSING,
							"manufacturable_length_mm": "1000",
							"configuration_result": "{}",
						},
					)
					self.assertFalse(result["success"])
					if value in (None, "", "2"):
						self.assertIn("not found", result["error"])
					else:
						self.assertIn("quantity" if field == "quantity" else "line index", result["error"])

	def test_invalid_run_overrides_are_not_silently_ignored(self):
		from illumenate_lighting.illumenate_lighting.api.configuration_contract import optional_positive

		for value in ("0", "-1", "NaN", "Infinity", "12feet"):
			with self.subTest(value=value):
				with self.assertRaises(ValueError):
					optional_positive(value)
				result = self.call_form(
					"webflow_configurator.validate_configuration",
					{"product_slug": MISSING, "selections": "{}", "override_max_run_ft": value},
				)
				self.assertFalse(result["is_valid"])
				self.assertEqual(result["field"], "override_max_run_ft")

	def test_all_optional_numeric_whitelist_parameters_accept_form_blanks(self):
		"""Catch another strict optional scalar before a browser reaches it."""
		import ast
		from pathlib import Path

		from frappe.utils.typing_validations import transform_parameter_types

		checked = 0
		for path in Path(frappe.get_app_path("illumenate_lighting")).rglob("*.py"):
			if path.name.startswith("test_"):
				continue
			for definition in ast.parse(path.read_text(encoding="utf-8")).body:
				if not isinstance(definition, ast.FunctionDef) or not any(
					"frappe.whitelist" in ast.unparse(d) for d in definition.decorator_list
				):
					continue
				args = definition.args.args
				defaults = definition.args.defaults
				for arg, default in zip(args[len(args) - len(defaults) :], defaults, strict=True):
					annotation = ast.unparse(arg.annotation) if arg.annotation else ""
					if (
						not isinstance(default, ast.Constant)
						or default.value is not None
						or not any(t in annotation for t in ("float", "int", "bool"))
					):
						continue
					module = ".".join(
						path.relative_to(Path(frappe.get_app_path("illumenate_lighting")).parent)
						.with_suffix("")
						.parts
					)
					function = inspect.unwrap(frappe.get_attr(module + "." + definition.name))
					with self.subTest(method=definition.name, arg=arg.arg):
						transform_parameter_types(function, (), {arg.arg: ""})
						checked += 1
		self.assertGreaterEqual(checked, 13)

	def test_finish_options_and_saved_fixture_details_use_installed_schema(self):
		prefix = "ILL-TRANSPORT-" + frappe.generate_hash(length=10)
		definitions = [
			{
				"doctype": "ilL-Attribute-Finish",
				"name": prefix,
				"finish_name": "Transport Test Finish",
				"code": "TTF",
				"status": "Active",
			},
			{
				"doctype": "ilL-Fixture-Template",
				"name": prefix,
				"template_name": "Transport Test Template",
				"is_active": 1,
			},
			{
				"doctype": "ilL-Configured-Fixture",
				"name": prefix,
				"config_hash": prefix,
				"finish": prefix,
				"fixture_template": prefix,
				"manufacturable_overall_length_mm": 1000,
				"include_power_supply": 0,
			},
		]
		inserted = []
		try:
			for definition in definitions:
				doc = frappe.get_doc(definition)
				doc.db_insert()
				inserted.append(doc)
			result = self.call_form(
				"configurator_engine.get_cascading_options_for_template", {"fixture_template_code": prefix}
			)
			self.assertTrue(result["success"])
			self.assertIn({"value": prefix, "label": "Transport Test Finish"}, result["options"]["finishes"])
			result = self.call_form(
				"portal.get_configured_fixture_details", {"configured_fixture_id": prefix}
			)
			self.assertTrue(result["success"])
			self.assertEqual(result["details"]["finish"], "Transport Test Finish")
		finally:
			for doc in reversed(inserted):
				frappe.db.delete(doc.doctype, {"name": doc.name})
			frappe.clear_document_cache("ilL-Fixture-Template", prefix)
