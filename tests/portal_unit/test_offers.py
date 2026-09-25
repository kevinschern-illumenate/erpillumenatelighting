import copy
import json
import types
import unittest
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

from illumenate_lighting.illumenate_lighting.api.configuration_contract import fingerprint
from illumenate_lighting.illumenate_lighting.portal.offer_contract import assert_conversion_matches


class OfferConversion(unittest.TestCase):
	def example(self):
		return {
			"customer": "DEALER-A",
			"currency": "USD",
			"terms": "Net 30",
			"grand_total": 120,
			"net_total": 120,
			"items": [
				{
					"item_code": "BUILD1",
					"qty": 2,
					"uom": "Nos",
					"conversion_factor": 1,
					"rate": 60,
					"amount": 120,
					"ill_bom": "BOM1",
				}
			],
		}

	def test_preserves_price_quantity_and_pinned_bom(self):
		original = self.example()
		assert_conversion_matches(original, copy.deepcopy(original))
		for field, value in (("qty", 1), ("rate", 65), ("ill_bom", "NEW-BOM"), ("item_code", "OTHER")):
			changed = copy.deepcopy(original)
			changed["items"][0][field] = value
			with self.subTest(field=field), self.assertRaises(ValueError):
				assert_conversion_matches(original, changed)

	def test_partial_erp_mapping_and_new_tax_are_rejected(self):
		original = self.example()
		for changed in (
			{**original, "items": []},
			{**original, "grand_total": 132},
			{**original, "terms": "Prepay"},
		):
			with self.assertRaises(ValueError):
				assert_conversion_matches(original, changed)


class IssuedOfferGuards(unittest.TestCase):
	def dependencies(self, buyer=True):
		access = types.ModuleType(ROOT + ".portal.access")
		access.can_read_schedule = MagicMock(return_value=True)
		access.get_actor = MagicMock(
			return_value=Record(
				user="buyer@example.com",
				is_guest=False,
				is_company_dealer_for=lambda customer: buyer and customer == "DEALER-A",
			)
		)
		staff = types.ModuleType(ROOT + ".portal.staff")
		staff.allowed = MagicMock(return_value=False)
		staff.require = MagicMock()
		return {module.__name__: module for module in (access, staff)}

	def example(self):
		return Record(
			name="OFFER1",
			customer="DEALER-A",
			quotation="Q1",
			schedule="S1",
			quote_request="QR1",
			state="ISSUED",
			snapshot_json=json.dumps({"customer": "DEALER-A"}),
			snapshot_hash="hash1",
			schedule_hash="scope1",
			valid_until="2026-10-01",
		)

	def test_technical_collaborator_cannot_read_commercial_offer(self):
		with load_service(ROOT + ".portal.offers", self.dependencies(buyer=False)) as (module, _frappe):
			self.assertFalse(module.can_read(self.example()))

	def test_foreign_customer_cannot_read_offer(self):
		with load_service(ROOT + ".portal.offers", self.dependencies()) as (module, _frappe):
			offer = self.example()
			offer["customer"] = "DEALER-B"
			self.assertFalse(module.can_read(offer))

	def test_dealer_service_access_does_not_expose_native_build_snapshot(self):
		with load_service(ROOT + ".portal.offers", self.dependencies()) as (module, _frappe):
			self.assertTrue(module.can_read(self.example()))
			self.assertFalse(module.has_permission(self.example()))

	def test_expired_cancelled_and_superseded_offers_are_unavailable(self):
		for case in ("expired", "cancelled", "superseded", "schedule", "quotation"):
			with (
				self.subTest(case=case),
				load_service(ROOT + ".portal.offers", self.dependencies()) as (module, frappe),
			):
				offer = self.example()
				quotation = Record(
					docstatus=2 if case == "cancelled" else 1, status="Open", party_name="DEALER-A"
				)
				request = Record(latest_issued_offer="OTHER" if case == "superseded" else "OFFER1")
				if case == "expired":
					offer["valid_until"] = "2026-09-01"
				frappe.get_doc.side_effect = [quotation, request, Record(is_locked=False)]
				with (
					patch.object(module, "_scope", return_value="other" if case == "schedule" else "scope1"),
					patch.object(module, "commercial_customer", return_value="DEALER-A"),
					patch.object(
						module,
						"_snapshot",
						return_value={"customer": "different" if case == "quotation" else "DEALER-A"},
					),
					self.assertRaises(ValueError),
				):
					module._current(offer)

	def test_authorized_accepted_retry_returns_existing_receipt_before_current_state(self):
		with load_service(ROOT + ".portal.offers", self.dependencies()) as (module, _frappe):
			offer = self.example()
			offer.update(
				state="ACCEPTED",
				sales_order="SO1",
				response_hash=fingerprint(
					{
						"action": "ACCEPT",
						"hash": "hash1",
						"note": "",
						"po_no": "PO1",
						"requested_date": "2026-10-02",
					}
				),
			)
			with (
				patch.object(module, "_load", return_value=offer),
				patch.object(module, "_current") as current,
			):
				result = module.respond("OFFER1", "ACCEPT", "hash1", po_no="PO1", requested_date="2026-10-02")
			self.assertEqual(result["sales_order"], "SO1")
			self.assertTrue(result["already_existed"])
			current.assert_not_called()

	def test_acceptance_with_changed_client_hash_is_rejected(self):
		with load_service(ROOT + ".portal.offers", self.dependencies()) as (module, _frappe):
			with (
				patch.object(module, "_load", return_value=self.example()),
				patch.object(module, "_current") as current,
				self.assertRaisesRegex(ValueError, "current offer"),
			):
				module.respond("OFFER1", "ACCEPT", "wrong-hash", requested_date="2026-10-02")
			current.assert_not_called()
