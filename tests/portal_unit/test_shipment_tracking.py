"""DESK-8 and shipping plan phase 3: carrier, tracking numbers and links for a Delivery Note."""

import unittest

from test_services import ROOT, Record, load_service

NONE = {"carrier": None, "number": None, "url": None}


def fake_get_all(links=(), shipments=(), parcels=()):
	"""frappe.get_all stand-in that answers the three lookups packages_by_delivery_note makes."""

	def get_all(doctype, filters=None, fields=None, order_by=None, **kwargs):
		if doctype == "Shipment Delivery Note":
			wanted = set(filters["delivery_note"][1])
			return [Record(row) for row in links if row["delivery_note"] in wanted]
		if doctype == "Shipment":
			wanted = set(filters["name"][1])
			rows = [
				Record(row) for row in shipments if row["name"] in wanted and row.get("docstatus", 1) == 1
			]
			rows = [row for row in rows if row.get("awb_number")]
			return sorted(rows, key=lambda row: row.get("creation") or "")
		if doctype == "Shipment Parcel":
			wanted = set(filters["parent"][1])
			rows = [Record(row) for row in parcels if row["parent"] in wanted]
			return sorted(rows, key=lambda row: row.get("idx") or 0)
		raise AssertionError(doctype)

	return get_all


class ShipmentTracking(unittest.TestCase):
	def tracking(self, **values):
		with load_service(ROOT + ".portal.shipment_tracking") as (module, _frappe):
			return module.tracking(Record(values))

	def test_parcel_carriers_get_an_encoded_tracking_link(self):
		self.assertEqual(
			self.tracking(ill_carrier="UPS", ill_tracking_number=" 1Z 999&x "),
			{
				"carrier": "UPS",
				"number": "1Z 999&x",
				"url": "https://www.ups.com/track?tracknum=1Z%20999%26x",
				"packages": [
					{
						"carrier": "UPS",
						"number": "1Z 999&x",
						"url": "https://www.ups.com/track?tracknum=1Z%20999%26x",
					}
				],
			},
		)
		self.assertTrue(
			self.tracking(ill_carrier="FedEx", ill_tracking_number="77")["url"].startswith(
				"https://www.fedex.com/"
			)
		)
		self.assertIn("tLabels=94", self.tracking(ill_carrier="USPS", ill_tracking_number="94")["url"])

	def test_freight_and_other_show_the_number_without_a_link(self):
		for carrier in ("Freight", "Other"):
			with self.subTest(carrier=carrier):
				result = self.tracking(ill_carrier=carrier, ill_tracking_number="PRO-1")
				self.assertEqual(
					{key: result[key] for key in ("carrier", "number", "url")},
					{"carrier": carrier, "number": "PRO-1", "url": None},
				)

	def test_older_notes_fall_back_to_vehicle_and_lr_numbers(self):
		result = self.tracking(transporter_name="Acme Freight", vehicle_no="V-1")
		self.assertEqual(result["number"], "V-1")
		self.assertEqual(result["carrier"], "Acme Freight")
		self.assertIsNone(result["url"])
		self.assertEqual(self.tracking(lr_no="LR-9")["number"], "LR-9")
		self.assertEqual(self.tracking(), {**NONE, "packages": []})

	def test_free_text_transporter_never_gets_a_link(self):
		self.assertIsNone(self.tracking(transporter_name="fedex", vehicle_no="77")["url"])

	def test_tracking_url_accepts_easypost_spelling(self):
		with load_service(ROOT + ".portal.shipment_tracking") as (module, _frappe):
			self.assertTrue(module.tracking_url("FEDEX", "1").startswith("https://www.fedex.com/"))
			self.assertIsNone(module.tracking_url("DHL", "1"))
			self.assertIsNone(module.tracking_url("FedEx", ""))


class ShipmentPackages(unittest.TestCase):
	def run_lookup(self, names, **data):
		with load_service(ROOT + ".portal.shipment_tracking") as (module, frappe):
			frappe.get_all.side_effect = fake_get_all(**data)
			return module.packages_by_delivery_note(names)

	def test_no_shipment_means_no_packages_and_no_shipment_query(self):
		with load_service(ROOT + ".portal.shipment_tracking") as (module, frappe):
			frappe.get_all.side_effect = fake_get_all()
			self.assertEqual(module.packages_by_delivery_note(["DN-1"]), {})
			self.assertEqual(frappe.get_all.call_count, 1)
			self.assertEqual(module.packages_by_delivery_note([]), {})
			self.assertEqual(frappe.get_all.call_count, 1)

	def test_master_first_then_each_box_without_duplicates(self):
		result = self.run_lookup(
			["DN-1"],
			links=[{"parent": "SHIP-1", "delivery_note": "DN-1"}],
			shipments=[
				{"name": "SHIP-1", "carrier": "FedEx", "awb_number": "M1", "ill_label_status": "Bought"}
			],
			parcels=[
				{"parent": "SHIP-1", "ill_tracking_number": "M1", "idx": 1},
				{"parent": "SHIP-1", "ill_tracking_number": "B2", "idx": 2},
				{"parent": "SHIP-1", "ill_tracking_number": None, "idx": 3},
			],
		)
		self.assertEqual([p["number"] for p in result["DN-1"]], ["M1", "B2"])
		self.assertTrue(all(p["url"].startswith("https://www.fedex.com/") for p in result["DN-1"]))
		self.assertEqual({p["carrier"] for p in result["DN-1"]}, {"FedEx"})

	def test_two_shipments_on_one_note_list_both_oldest_first(self):
		result = self.run_lookup(
			["DN-1"],
			links=[
				{"parent": "SHIP-2", "delivery_note": "DN-1"},
				{"parent": "SHIP-1", "delivery_note": "DN-1"},
			],
			shipments=[
				{"name": "SHIP-2", "carrier": "FedEx", "awb_number": "B", "creation": "2026-11-02"},
				{"name": "SHIP-1", "carrier": "FedEx", "awb_number": "A", "creation": "2026-11-01"},
			],
		)
		self.assertEqual([p["number"] for p in result["DN-1"]], ["A", "B"])

	def test_voided_draft_and_cancelled_shipments_are_left_out(self):
		result = self.run_lookup(
			["DN-1"],
			links=[
				{"parent": "VOID", "delivery_note": "DN-1"},
				{"parent": "DRAFT", "delivery_note": "DN-1"},
				{"parent": "NOLABEL", "delivery_note": "DN-1"},
			],
			shipments=[
				{"name": "VOID", "carrier": "FedEx", "awb_number": "V", "ill_label_status": "Voided"},
				{"name": "DRAFT", "carrier": "FedEx", "awb_number": "D", "docstatus": 0},
				{"name": "NOLABEL", "carrier": "FedEx", "awb_number": None},
			],
		)
		self.assertEqual(result, {})

	def test_tracking_uses_shipments_before_the_manual_fields(self):
		data = {
			"links": [{"parent": "SHIP-1", "delivery_note": "DN-1"}],
			"shipments": [{"name": "SHIP-1", "carrier": "FedEx", "awb_number": "M1"}],
			"parcels": [
				{"parent": "SHIP-1", "ill_tracking_number": "M1", "idx": 1},
				{"parent": "SHIP-1", "ill_tracking_number": "B2", "idx": 2},
			],
		}
		with load_service(ROOT + ".portal.shipment_tracking") as (module, frappe):
			frappe.get_all.side_effect = fake_get_all(**data)
			result = module.tracking(Record(name="DN-1", ill_carrier="UPS", ill_tracking_number="OLD"))
			self.assertEqual((result["carrier"], result["number"]), ("FedEx", "M1"))
			self.assertEqual([p["number"] for p in result["packages"]], ["M1", "B2"])
			# A note with no live Shipment keeps the manual fields.
			legacy = module.tracking(Record(name="DN-2", ill_carrier="UPS", ill_tracking_number="1Z"))
			self.assertEqual([p["number"] for p in legacy["packages"]], ["1Z"])
			# Prefetched packages skip the lookup entirely.
			calls = frappe.get_all.call_count
			module.tracking(Record(name="DN-3"), [])
			self.assertEqual(frappe.get_all.call_count, calls)


if __name__ == "__main__":
	unittest.main()
