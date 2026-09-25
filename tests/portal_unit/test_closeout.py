"""Recovery closeout regressions; no installed Frappe or external service."""

import copy
import types
import unittest
from unittest.mock import MagicMock, patch

import test_reviews
from test_fixture_groups import request as group_request
from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint
from illumenate_lighting.illumenate_lighting.api.group_contract import member_presentation, normalize


class MutableRecord(Record):
	__setattr__ = dict.__setitem__


def row(**data):
	result = MutableRecord(**data)
	result["set"] = lambda key, value: result.update({key: value})
	return result


class Closeout(unittest.TestCase):
	def test_rollout_family_and_pilot_gates_are_independent_of_history(self):
		staff = types.SimpleNamespace(allowed=lambda _: False)
		with load_service(ROOT + ".portal.rollout", {ROOT + ".portal.staff": staff}) as (service, frappe):
			self.assertTrue(service.available("LED Sheet"))
			frappe.conf["ill_portal_enabled_families"] = ["LED Sheet"]
			frappe.conf["ill_portal_pilot_users"] = ["pilot@example.com"]
			self.assertFalse(service.available("LED Sheet"))
			self.assertTrue(service.available("LED Sheet", public=True))
			frappe.session.user = "pilot@example.com"
			self.assertTrue(service.available("LED Sheets"))
			with self.assertRaises(PermissionError):
				service.require_family("LED Neon")
			frappe.conf["ill_portal_enabled_families"] = "LED Sheet"
			with self.assertRaisesRegex(ValueError, "JSON list"):
				service.available("LED Sheet")
			frappe.db.set_value.assert_not_called()

	def test_tape_and_neon_previews_share_persisted_build_identity(self):
		from illumenate_lighting.illumenate_lighting.api.configuration_contract import canonical_json

		for neon in (False, True):
			with (
				self.subTest(neon=neon),
				load_service(ROOT + ".api.tape_neon_configurator") as (service, frappe),
			):
				template = Record(name="T", template_code="T")
				result = {
					"selections": {"cct": "3000K"},
					"computed": {"total_watts": 20, "total_price_msrp": 100},
					"resolved_items": {"tape_spec": "SPEC"},
					"components": [{"item_code": "TAPE", "qty": 5, "stock_uom": "Foot"}],
					"cables": [],
					"engineering_sources": {},
					"part_number": "PART",
				}
				frappe.get_doc.return_value = template
				frappe.db.get_value.return_value = {"input_voltage": "24V"}
				service._stamp_build_preview(result, "T", neon)
				doc = Record(
					build_schema_version=2,
					config_hash=result["candidate_config_hash"],
					build_snapshot_json=canonical_json(result["build_snapshot"]),
				)
				frappe.db.get_value.side_effect = lambda dt, *args, **kwargs: (
					{"input_voltage": "24V"} if dt == "ilL-Spec-LED Tape" else "EXISTING"
				)
				frappe.get_doc.return_value = doc
				result["computed"]["total_price_msrp"] = 300
				self.assertEqual(
					service._create_or_reuse_configured_tape_neon(template, result, neon), "EXISTING"
				)
				query = [
					c for c in frappe.db.get_value.call_args_list if c.args[0] == "ilL-Configured-Tape-Neon"
				][-1]
				self.assertEqual(query.args[1]["config_hash"], result["candidate_config_hash"])
				frappe.db.set_value.assert_not_called()

	def test_authoring_roles_exclude_commercial_and_customer_writes(self):
		with load_service("illumenate_lighting.portal_staff_permissions") as (service, _):
			matrix = service.authoring_permissions(
				[
					"Customer",
					"Sales Order",
					"ilL-Project",
					"ilL-Configured-Group",
					"ilL-Order-Intake",
					"ilL-Spec-LED Tape",
					"ilL-LED-Sheet-Template",
				]
			)
			self.assertEqual(set(matrix["Item"]), {"read", "select"})
			for name in (
				"Customer",
				"Sales Order",
				"ilL-Project",
				"ilL-Configured-Group",
				"ilL-Order-Intake",
			):
				self.assertNotIn(name, matrix)
			self.assertIn("write", matrix["ilL-LED-Sheet-Template"])
			self.assertIn("import", matrix["ilL-Spec-LED Tape"])

	def test_engineering_pdf_uses_sealed_sources_and_never_new_master_fallback(self):
		with load_service(ROOT + ".api.engineering_sources") as (service, frappe):
			frappe.db.get_value.return_value = {"watts_per_foot": 8, "input_voltage": "24V"}
			sources = service.capture(tape_spec="TAPE")
			doc = row(engine_version="tape-neon-2", engineering_sources=sources)
			frappe.db.get_value.return_value = {"watts_per_foot": 4}
			self.assertEqual(service.resolve(doc, "ilL-Spec-LED Tape", "watts_per_foot"), (True, 8))
			self.assertEqual(service.resolve(doc, "ilL-Spec-LED Tape", "unknown"), (True, None))
			self.assertEqual(
				service.resolve(row(engine_version="linear-2"), "ilL-Spec-LED Tape", "watts_per_foot"),
				(True, None),
			)
			self.assertEqual(
				service.resolve(row(engine_version="legacy"), "ilL-Spec-LED Tape", "watts_per_foot"),
				(False, None),
			)
			self.assertNotIn("cost", service.FIELDS["ilL-Spec-Driver"].split())

	def test_commercial_snapshots_notice_group_and_line_presentation_changes(self):
		from illumenate_lighting.illumenate_lighting.portal.offer_contract import commercial_snapshot

		with load_service(ROOT + ".portal.order_review", test_reviews.OrderApproval().dependencies()) as (
			service,
			_,
		):
			item = row(
				item_code="GROUP",
				ill_configured_group="G1",
				ill_fixture_type="L1",
				additional_notes="Install left",
			)
			order = types.SimpleNamespace(customer="A", items=[item])
			order.get = lambda key: getattr(order, key, None)
			before = fingerprint(service.snapshot(order))
			offer = fingerprint(commercial_snapshot(order, customer="A"))
			item.additional_notes = "Install right"
			self.assertNotEqual(before, fingerprint(service.snapshot(order)))
			self.assertNotEqual(offer, fingerprint(commercial_snapshot(order, customer="A")))
			offer = fingerprint(commercial_snapshot(order, customer="A"))
			item.ill_configured_group = "G2"
			self.assertNotEqual(offer, fingerprint(commercial_snapshot(order, customer="A")))

	def test_schedule_drawing_cannot_release_changed_order_scope(self):
		with load_service(ROOT + ".portal.drawing_impact") as (service, frappe):
			line = row(name="LINE", qty=2, configured_group="G", line_id="L1", location="Lobby")
			item = row(
				ill_schedule_line_id="LINE",
				qty=2,
				ill_configured_group="G",
				item_code="GI",
				ill_bom="GB",
				ill_fixture_type="L1",
				ill_section_label="Lobby",
				conversion_factor=1,
			)
			frappe.get_doc.return_value = Record(configured_item="GI", bom="GB")
			order, schedule = row(items=[item]), row(lines=[line])
			self.assertTrue(service.order_matches_schedule(order, schedule))
			item.rate = 999
			self.assertTrue(service.order_matches_schedule(order, schedule))
			item.qty = 3
			self.assertFalse(service.order_matches_schedule(order, schedule))
			item.qty, item.item_code = 2, "SWAPPED"
			self.assertFalse(service.order_matches_schedule(order, schedule))
			item.item_code = "GI"
			schedule["lines"].append(row(name="OMITTED", qty=1, configured_fixture="F"))
			self.assertFalse(service.order_matches_schedule(order, schedule))

	def test_labels_follow_canonical_geometry_and_duplicate_members_are_distinct(self):
		request = group_request()
		request["members"].append(copy.deepcopy(request["members"][0]))
		request["members"][-1]["label"] = "Duplicate"
		before = member_presentation(request)
		self.assertEqual(len({item["member_key"] for item in before}), 4)
		self.assertEqual([item["label"] for item in before], ["Long", "Short", "Longest", "Duplicate"])
		request["members"].reverse()
		self.assertEqual(
			normalize(request)["members"],
			normalize({**request, "members": list(reversed(request["members"]))})["members"],
		)

	def test_fulfillment_copies_build_evidence_from_exact_source_row(self):
		with load_service(ROOT + ".portal.commercial_lineage") as (service, frappe):
			original = row(
				name="ROW",
				item_code="GROUP",
				ill_configured_group="PINNED",
				ill_bom="BOM",
				ill_section_label="Lobby",
				ill_fixture_type="L1",
				ill_configuration_json='{"version":3}',
				additional_notes="Install left",
				ill_configurator_request='{"schema_version":3}',
			)
			frappe.get_doc.return_value = Record(customer="A", company="MFG", docstatus=1, items=[original])
			item = row(
				item_code="GROUP",
				against_sales_order="SO",
				so_detail="ROW",
				ill_bom="FORGED",
				meta=types.SimpleNamespace(has_field=lambda _: True),
			)
			doc = Record(doctype="Delivery Note", customer="A", company="MFG", docstatus=0, items=[item])
			service.validate(doc)
			self.assertEqual(item.additional_notes, "Install left")
			self.assertEqual(item.ill_configurator_request, '{"schema_version":3}')
			self.assertEqual(
				(item.ill_bom, item.ill_configured_group, item.ill_section_label), ("BOM", "PINNED", "Lobby")
			)
			item.item_code = "DIFFERENT"
			with self.assertRaisesRegex(ValueError, "source row"):
				service.validate(doc)

	def test_invoice_uses_delivery_row_and_denies_foreign_customer(self):
		with load_service(ROOT + ".portal.commercial_lineage") as (service, frappe):
			frappe.get_doc.return_value = Record(customer="B", company="MFG", docstatus=1)
			item = row(item_code="GROUP", delivery_note="DN", dn_detail="DNI")
			with self.assertRaisesRegex(ValueError, "same customer"):
				service.validate(
					Record(doctype="Sales Invoice", customer="A", company="MFG", docstatus=0, items=[item])
				)
			frappe.get_doc.assert_called_once_with("Delivery Note", "DN")

	def test_delivery_promise_updates_native_dates_and_amendment_clears_old_evidence(self):
		with load_service(ROOT + ".portal.order_review", test_reviews.OrderApproval().dependencies()) as (
			service,
			_,
		):
			old = row(ill_confirmed_delivery_date=None)
			item = row(delivery_date="2026-10-01")
			order = row(
				ill_fixture_schedule="S",
				docstatus=0,
				ill_confirmed_delivery_date="2026-11-01",
				items=[item],
				get_doc_before_save=lambda: old,
			)
			with patch.object(service, "_staff"):
				service.validate_order(order)
				self.assertEqual(order.delivery_date, "2026-11-01")
				self.assertEqual(item.delivery_date, "2026-11-01")
				order["get_doc_before_save"] = lambda: None
				order.amended_from, order.ill_quote_offer = "OLD", "OLD-OFFER"
				service.validate_order(order)
				self.assertIsNone(order.ill_quote_offer)
				self.assertIsNone(order.ill_delivery_confirmed_by)

	def test_disabled_buyer_cannot_supply_current_approval_evidence(self):
		deps = test_reviews.OrderApproval().dependencies()
		deps[ROOT + ".portal.access"].get_actor.return_value = Record(is_company_dealer_for=lambda _: False)
		with load_service(ROOT + ".portal.order_review", deps) as (service, _):
			order = types.SimpleNamespace(**test_reviews.OrderApproval().order())
			order.get = lambda key: getattr(order, key, None)
			intake = Record(
				state="UNDER_REVIEW",
				intake_json="{}",
				acknowledged_by="revoked",
				acknowledged_hash=fingerprint(service.snapshot(order)),
			)
			with (
				patch.object(service, "_staff"),
				patch.object(service, "_load", return_value=(order, intake)),
				self.assertRaisesRegex(ValueError, "no longer"),
			):
				service.before_submit(order)

	def test_order_lock_order_is_deterministic_and_detects_source_change(self):
		with load_service(ROOT + ".portal.order_review", test_reviews.OrderApproval().dependencies()) as (
			service,
			frappe,
		):
			frappe.db.get_value.side_effect = lambda dt, name, field: {"SO1": "S2", "SO2": "S1"}[name]
			service.lock_orders("SO2", "SO1", "SO2")
			self.assertEqual(
				[call.args[1] for call in frappe.db.sql.call_args_list], ["S1", "S2", "SO1", "SO2"]
			)
			frappe.db.get_value.side_effect = ["S1", "Changed"]
			with self.assertRaisesRegex(ValueError, "source schedule changed"):
				service.lock_orders("SO1")

	def test_migration_digest_detects_historical_bom_and_rate_mutation(self):
		with load_service(ROOT + ".portal.release_evidence") as (service, _):
			order = Record(
				doctype="Sales Order",
				customer="A",
				items=[Record(item_code="X", qty=2, rate=10, ill_bom="B1")],
			)
			before = {"records": {"Sales Order": {"SO": service.document_digest(order)}}}
			order["items"][0]["ill_bom"] = "B2"
			after = {"records": {"Sales Order": {"SO": service.document_digest(order), "NEW": "new"}}}
			result = service.compare(before, after)
			self.assertFalse(result["historical_records_unchanged"])
			self.assertEqual(result["changed"], [{"doctype": "Sales Order", "name": "SO"}])
			self.assertEqual(result["added"], [{"doctype": "Sales Order", "name": "NEW"}])

	def test_legacy_copy_rejects_changed_source_without_writing(self):
		with load_service(ROOT + ".portal.legacy_file_migration") as (service, frappe):
			frappe.only_for = MagicMock()
			with (
				patch.object(service, "inspect_file", return_value=(None, b"data", {"sha256": "new"})),
				self.assertRaisesRegex(ValueError, "bytes changed"),
			):
				service.copy_private("FILE", "old")
			frappe.get_doc.assert_not_called()
			frappe.db.rollback.assert_called()
