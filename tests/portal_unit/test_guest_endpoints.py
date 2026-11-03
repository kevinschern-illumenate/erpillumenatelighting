"""Guest (allow_guest) endpoint hardening — plan item 1.4."""

import ast
import json
import pathlib
import types
import unittest

from test_services import ROOT, load_service

APP = pathlib.Path(__file__).resolve().parents[2] / "illumenate_lighting"


def _guest_endpoints():
	for path in sorted(APP.rglob("*.py")):
		if path.name.startswith("test_"):
			continue
		tree = ast.parse(path.read_text(encoding="utf-8"))
		for node in ast.walk(tree):
			if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
				continue
			for index, decorator in enumerate(node.decorator_list):
				if (
					isinstance(decorator, ast.Call)
					and ast.unparse(decorator.func) in {"frappe.whitelist", "whitelist"}
					and any(
						kw.arg == "allow_guest" and getattr(kw.value, "value", None) is True
						for kw in decorator.keywords
					)
				):
					yield path.relative_to(APP.parent), node, index


class GuestEndpointInventory(unittest.TestCase):
	def test_inventory_is_not_empty(self):
		self.assertGreater(len(list(_guest_endpoints())), 25)

	def test_every_guest_endpoint_is_rate_limited_directly_under_whitelist(self):
		problems = []
		for path, node, index in _guest_endpoints():
			decorators = node.decorator_list
			following = decorators[index + 1] if index + 1 < len(decorators) else None
			if index != 0:
				problems.append(f"{path}:{node.lineno} {node.name}: whitelist is not the outermost decorator")
			if not (
				isinstance(following, ast.Call)
				and ast.unparse(following.func) in {"rate_limit", "frappe.rate_limiter.rate_limit"}
			):
				problems.append(f"{path}:{node.lineno} {node.name}: missing @rate_limit under @frappe.whitelist")
				continue
			kwargs = {kw.arg: kw.value for kw in following.keywords}
			if not {"limit", "seconds"} <= kwargs.keys():
				problems.append(f"{path}:{node.lineno} {node.name}: rate_limit needs limit= and seconds=")
		self.assertEqual(problems, [])


class GuestPayload(unittest.TestCase):
	def setUp(self):
		with load_service(ROOT + ".api.guest_payload") as (module, _):
			self.module = module

	def test_strings_are_decoded_and_dicts_pass_through(self):
		self.assertEqual(self.module.load_guest_json('{"a": 1}'), {"a": 1})
		payload = {"a": 1}
		self.assertIs(self.module.load_guest_json(payload), payload)
		self.assertIsNone(self.module.load_guest_json(None))

	def test_oversized_strings_are_refused_before_parsing(self):
		big = json.dumps({"x": "y" * self.module.MAX_GUEST_JSON_BYTES})
		with self.assertRaises(self.module.PayloadTooLarge) as caught:
			self.module.load_guest_json(big)
		# Existing handlers catch json.JSONDecodeError / ValueError.
		self.assertIsInstance(caught.exception, json.JSONDecodeError)
		self.assertIsInstance(caught.exception, ValueError)

	def test_limit_counts_utf8_bytes(self):
		value = json.dumps("é" * 40, ensure_ascii=False)
		self.assertEqual(self.module.load_guest_json(value, limit=len(value.encode())), "é" * 40)
		with self.assertRaises(self.module.PayloadTooLarge):
			self.module.load_guest_json(value, limit=len(value))

	def test_object_only_rejects_non_objects_as_decode_errors(self):
		load = self.module.load_guest_json
		self.assertEqual(load('{"a": 1}', object_only=True), {"a": 1})
		for value in ("[]", "null", "3", '"x"', [], None):
			with self.assertRaises(json.JSONDecodeError):
				load(value, object_only=True)
		self.assertEqual(load("[]"), [])

	def test_bounded_int_accepts_form_strings_and_clamps(self):
		bounded = self.module.bounded_int
		self.assertEqual(bounded("10", default=6, minimum=1, maximum=24), 10)
		self.assertEqual(bounded(" 3 ", default=6, minimum=1, maximum=24), 3)
		self.assertEqual(bounded("0", default=6, minimum=1, maximum=24), 1)
		self.assertEqual(bounded(10_000, default=6, minimum=1, maximum=24), 24)
		self.assertEqual(bounded("abc", default=6, minimum=1, maximum=24), 6)
		self.assertEqual(bounded(None, default=6, minimum=1, maximum=24), 6)
		self.assertEqual(bounded("", default=6, minimum=1, maximum=24), 6)


class DriverControllerSelections(unittest.TestCase):
	def test_oversized_selections_are_rejected_as_invalid_json(self):
		deps = {
			ROOT + ".doctype.ill_controller_template.ill_controller_template": types.SimpleNamespace(
				CONTROLLER_VARIANT_AXES={}
			),
			ROOT + ".doctype.ill_driver_template.ill_driver_template": types.SimpleNamespace(
				DRIVER_VARIANT_AXES={}, _normalise_axis_value=str
			),
		}
		with load_service(ROOT + ".api.driver_controller_configurator", deps) as (service, _):
			self.assertEqual(service._coerce_selections('{"wattage": "96"}'), {"wattage": "96"})
			with self.assertRaisesRegex(ValueError, "Invalid selections JSON"):
				service._coerce_selections(json.dumps({"x": "y" * 70_000}))


class WebflowConfiguratorSelections(unittest.TestCase):
	def test_every_selections_parse_uses_the_guarded_loader(self):
		source = (APP / "illumenate_lighting" / "api" / "webflow_configurator.py").read_text(encoding="utf-8")
		self.assertNotIn("json.loads(selections)", source)
		self.assertGreaterEqual(source.count("load_guest_json(selections, object_only=True)"), 6)


if __name__ == "__main__":
	unittest.main()
