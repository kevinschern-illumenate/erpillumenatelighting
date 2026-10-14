"""DESK-8: carrier, tracking number and link for a Delivery Note."""

import unittest

from test_services import ROOT, Record, load_service


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
				self.assertEqual(
					self.tracking(ill_carrier=carrier, ill_tracking_number="PRO-1"),
					{"carrier": carrier, "number": "PRO-1", "url": None},
				)

	def test_older_notes_fall_back_to_vehicle_and_lr_numbers(self):
		self.assertEqual(
			self.tracking(transporter_name="Acme Freight", vehicle_no="V-1"),
			{"carrier": "Acme Freight", "number": "V-1", "url": None},
		)
		self.assertEqual(self.tracking(lr_no="LR-9")["number"], "LR-9")
		self.assertEqual(self.tracking(), {"carrier": None, "number": None, "url": None})


if __name__ == "__main__":
	unittest.main()
