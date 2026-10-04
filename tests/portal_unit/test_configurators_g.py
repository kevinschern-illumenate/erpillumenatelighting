"""New family projections and authoritative, replay-safe portal writes."""

import json
import types
import unittest
from unittest.mock import MagicMock

from test_kit_save import SELECTIONS, SERVER_RESULT
from test_product_finder_content import FakeDocument
from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.api.product_projection import project_product


class Configurators(unittest.TestCase):
	def test_new_family_projection_requires_active_template(self):
		for family, field in [
			("Driver", "driver_template"),
			("Controller", "controller_template"),
			("Extrusion Kit", "kit_template"),
		]:
			product = {"name": "P", "product_type": family, "is_active": 1, "is_configurable": 1, field: "T"}
			self.assertEqual(project_product(product)["capability"], "configure")
			self.assertNotEqual(project_product(product, template_active=False)["capability"], "configure")

	def test_driver_save_strips_forgery_and_revalidates_variant(self):
		validator = MagicMock(
			return_value={
				"success": True,
				"template_code": "T",
				"variant": {"item": "SAFE", "variant_code": "V"},
			}
		)
		deps = {
			ROOT + ".portal.access": types.SimpleNamespace(
				require_catalog_access=MagicMock(), can_edit_schedule=MagicMock()
			),
			ROOT + ".portal.configuration": types.SimpleNamespace(
				RECEIPT="Receipt",
				schedule_context=MagicMock(),
				object_value=lambda v, label: json.loads(v) if isinstance(v, str) else v,
			),
			ROOT + ".portal.rollout": types.SimpleNamespace(require_family=MagicMock()),
			ROOT + ".api.driver_controller_configurator": types.SimpleNamespace(
				_KINDS={"Driver": {"steps": [{"name": "wattage"}]}}, _validate_configuration=validator
			),
		}
		with load_service(ROOT + ".portal.standard_products", deps) as (service, _):
			service._product = MagicMock(return_value=Record(product_type="Driver"))
			service._add = MagicMock(return_value={"success": True})
			args = ("p", {"wattage": 96, "item_code": "FORGED", "price": 0}, "S", 1, "L", "old", "retry-key")
			service.add_configured(*args)
			self.assertEqual(json.loads(validator.call_args.args[2]), {"wattage": 96})
			self.assertEqual(service._add.call_args.args[1], "SAFE")
			self.assertEqual(service._add.call_args.args[-1]["item_code"], "SAFE")
			validator.return_value = {"success": False, "error": "Invalid option"}
			with self.assertRaisesRegex(ValueError, "Invalid"):
				service.add_configured(*args)

	def test_portal_kit_checks_lock_validates_and_replays_receipt(self):
		line = FakeDocument(line_key="L", qty=1, set=lambda k, v: line.update({k: v}))
		schedule = FakeDocument(
			name="S", modified="old", status="DRAFT", is_locked=0, lines=[line], save=MagicMock()
		)
		context = MagicMock(return_value=schedule)
		validate = MagicMock(return_value=SERVER_RESULT)
		writer = MagicMock()
		deps = {
			ROOT + ".portal.access": types.SimpleNamespace(require_catalog_access=MagicMock()),
			ROOT + ".portal.configuration": types.SimpleNamespace(
				RECEIPT="Receipt",
				object_value=lambda v, label: v or {},
				resolve_line=lambda *a: line,
				schedule_context=context,
			),
			ROOT + ".portal.rollout": types.SimpleNamespace(require_family=MagicMock()),
			ROOT + ".api.extrusion_kit_configurator": types.SimpleNamespace(
				KIT_SELECTION_KEYS=tuple(SELECTIONS),
				validate_kit_configuration=validate,
				_write_kit_line=writer,
			),
			ROOT + ".portal.product_finder.sessions": types.SimpleNamespace(decoded=json.loads),
			ROOT + ".portal.product_finder.verification": types.SimpleNamespace(),
		}
		with load_service(ROOT + ".portal.kit_configuration", deps) as (service, frappe):
			frappe.db.get_value.return_value = None
			args = dict(
				schedule_name="S",
				selections={**SELECTIONS, "pricing": 0, "verification_status": "Verified"},
				idempotency_key="retry-key",
				expected_modified="old",
				line_key="L",
				metadata={"qty": 2},
			)
			result = service.save(**args)
			validate.assert_called_once_with(SELECTIONS)
			writer.assert_called_once_with(schedule, line, SERVER_RESULT)
			self.assertTrue(result["success"])
			self.assertEqual(line.qty, 2)
			context.assert_called_with("S", write=True, lock=True)
			receipt = frappe.get_doc.call_args.args[0]
			frappe.db.get_value.return_value = Record(
				request_hash=receipt["request_hash"], response_json=receipt["response_json"]
			)
			self.assertTrue(service.save(**args)["already_existed"])
			validate.assert_called_once()
			with self.assertRaisesRegex(ValueError, "different content"):
				service.save(**{**args, "metadata": {"qty": 3}})
			frappe.db.get_value.return_value = None
			schedule.is_locked = 1
			with self.assertRaisesRegex(ValueError, "changed"):
				service.save(**args)

	def test_shared_writer_clears_old_family_artifacts(self):
		with load_service(ROOT + ".api.extrusion_kit_configurator") as (service, frappe):
			frappe.db.get_value.return_value = 10
			line = FakeDocument(
				configured_fixture="OLD",
				ill_configurator_request="OLD",
				ill_bom="OLD",
				verification_status="Pending",
			)
			service._write_kit_line(None, line, SERVER_RESULT)
			for field in ("configured_fixture", "ill_configurator_request", "ill_bom", "verification_status"):
				self.assertIsNone(line[field])
			self.assertEqual(line.kit_template, "KIT-1")

	def test_kit_backfill_preserves_conflicts(self):
		with load_service("illumenate_lighting.patches.backfill_kit_template_links") as (patch, frappe):
			frappe.get_all.return_value = [
				Record(name="K1", webflow_product="P1"),
				Record(name="K2", webflow_product="P2"),
			]
			frappe.db.get_value.side_effect = [None, "OTHER"]
			frappe.log_error = MagicMock()
			patch.execute()
			frappe.db.set_value.assert_called_once_with("ilL-Webflow-Product", "P1", "kit_template", "K1")
			frappe.log_error.assert_called_once()
