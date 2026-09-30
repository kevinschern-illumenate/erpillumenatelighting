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
# Whitelisted parameters that still reject a blank form value. No portal or Desk
# caller sends them blank today, and their bodies do not normalize one, so each
# needs a body change as well as a wider annotation (recovery plan §7.5).
KNOWN_STRICT = {
	"api.configurator_engine.validate_and_quote": {
		"start_leader_len_mm",
		"end_leader_len_mm",
		"relax_length_validation",
	},
	"api.configurator_engine.validate_and_quote_with_output": {"start_leader_len_mm", "end_leader_len_mm"},
	"api.document_requests.add_deliverable": {"publish"},
	"api.exports.generate_schedule_csv": {"priced"},
	"api.exports.generate_schedule_pdf": {"priced"},
	"api.manufacturing_generator.generate_manufacturing_artifacts": {"qty", "skip_if_exists"},
	"api.portal.create_website_user": {"send_invite"},
	"api.portal.get_items_by_product_type": {"exclude_variants"},
	"api.portal.get_product_types": {"include_subgroups"},
	"api.portal.invite_project_collaborator": {"send_invite"},
	"api.reconciliation.regenerate_artifacts": {"regenerate_bom", "regenerate_work_order"},
	"api.spec_submittal.generate_spec_submittal_packet": {"include_cover", "allow_partial"},
	"api.webflow_attributes.get_product_attribute_references": {"limit", "offset"},
	"api.webflow_attributes.get_webflow_attributes": {"limit", "offset"},
	"api.webflow_attributes.trigger_attribute_sync": {"sync_all"},
	"api.webflow_export.get_webflow_categories": {"include_inactive"},
	"api.webflow_export.get_webflow_products": {"limit", "offset"},
	"api.webflow_integration.get_related_products": {"limit"},
	"api.webflow_schedule.add_to_schedule": {"quantity"},
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
		"""Catch another strict optional scalar before a browser reaches it.

		Every defaulted int/float/bool parameter must accept a blank form value, and
		every list/dict parameter a JSON string (frappe.call encodes arrays and
		objects that way). Parameters in KNOWN_STRICT are the exceptions.
		"""
		import ast
		from pathlib import Path

		from frappe.exceptions import FrappeTypeError
		from frappe.utils.typing_validations import transform_parameter_types

		app = Path(frappe.get_app_path("illumenate_lighting"))
		checked = 0
		failures = set()
		for path in app.rglob("*.py"):
			if path.name.startswith("test_"):
				continue
			for definition in ast.parse(path.read_text(encoding="utf-8")).body:
				if not isinstance(definition, ast.FunctionDef) or not any(
					"frappe.whitelist" in ast.unparse(d) for d in definition.decorator_list
				):
					continue
				args = definition.args.args
				defaults = definition.args.defaults
				optional = list(zip(args[len(args) - len(defaults) :], defaults, strict=True))
				optional += [
					(arg, default)
					for arg, default in zip(
						definition.args.kwonlyargs, definition.args.kw_defaults, strict=True
					)
					if default is not None
				]
				for arg, _default in optional:
					annotation = ast.unparse(arg.annotation) if arg.annotation else ""
					probes = []
					if any(t in annotation for t in ("float", "int", "bool")):
						probes.append("")
					if "list" in annotation.lower():
						probes.append('["value"]')
					if "dict" in annotation.lower():
						probes.append('{"key": "value"}')
					if not probes:
						continue
					module = ".".join(path.relative_to(app.parent).with_suffix("").parts)
					function = inspect.unwrap(frappe.get_attr(module + "." + definition.name))
					method = (
						module.removeprefix("illumenate_lighting.illumenate_lighting.")
						+ "."
						+ definition.name
					)
					for probe in probes:
						try:
							transform_parameter_types(function, (), {arg.arg: probe})
						except FrappeTypeError:
							failures.add((method, arg.arg))
						checked += 1
		known = {(method, arg) for method, names in KNOWN_STRICT.items() for arg in names}
		self.assertEqual(sorted(failures - known), [], "Widen these annotations and normalize inside")
		self.assertEqual(
			sorted(known - failures), [], "These now accept form values; remove from KNOWN_STRICT"
		)
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
