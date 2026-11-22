"""Shipping plan phases 1 to 3: parcel checks, box splitting and tracker status rules."""

import unittest

from test_services import ROOT, load_service


def rules():
	with load_service(ROOT + ".api.shipping_rules") as (module, _frappe):
		return module


R = rules()
LIMITS = R.thresholds()


def box(length=24, width=12, height=8, weight=10, count=1):
	return {"length": length, "width": width, "height": height, "weight": weight, "count": count}


class Thresholds(unittest.TestCase):
	def test_settings_override_defaults_but_blank_or_zero_keep_them(self):
		limits = R.thresholds({"ah_length_in": 60, "max_weight_lb": 0, "ah_weight_lb": None})
		self.assertEqual(limits["ah_length_in"], 60)
		self.assertEqual(limits["max_weight_lb"], 150)
		self.assertEqual(limits["ah_weight_lb"], 50)
		self.assertEqual(set(limits), set(R.DEFAULT_THRESHOLDS))

	def test_length_plus_girth_uses_the_longest_side_as_length(self):
		self.assertEqual(R.length_plus_girth(box(6, 48, 6)), 48 + 2 * (6 + 6))


class ParcelChecks(unittest.TestCase):
	def test_a_normal_box_passes_without_flags(self):
		self.assertEqual(R.check_parcels([box()], LIMITS), {"errors": [], "flags": [], "special": [False]})

	def test_no_parcels_and_missing_measurements_block(self):
		self.assertEqual(R.check_parcels([], LIMITS)["errors"], ["Add at least one parcel."])
		errors = R.check_parcels([box(height=0, weight=0)], LIMITS)["errors"]
		self.assertEqual(len(errors), 2)
		self.assertTrue(errors[0].startswith("Box 1 needs a length, width and height"))
		self.assertIn("weight above 0 (pounds)", errors[1])

	def test_over_the_hard_limits_blocks(self):
		for parcel, word in (
			(box(length=110), "long"),
			(box(weight=151), "weighs"),
			(box(100, 20, 20), "girth"),
		):
			with self.subTest(word=word):
				found = R.check_parcels([parcel], LIMITS)
				self.assertEqual(len(found["errors"]), 1)
				self.assertIn(word, found["errors"][0])
				self.assertEqual(found["flags"], [])

	def test_long_fixture_box_flags_additional_handling(self):
		found = R.check_parcels([box(), box(52, 6, 6, 12)], LIMITS)
		self.assertEqual(found["errors"], [])
		self.assertEqual(found["special"], [False, True])
		self.assertEqual(found["flags"], ["Box 2: additional handling: longest side 52 in."])

	def test_oversize_replaces_the_additional_handling_size_flags(self):
		found = R.check_parcels([box(98, 6, 6, 20)], LIMITS)
		self.assertEqual(len(found["flags"]), 1)
		self.assertTrue(found["flags"][0].startswith("Box 1: oversize (98 in long"))

	def test_heavy_and_wide_boxes_each_flag(self):
		flags = R.check_parcels([box(40, 32, 10, 55)], LIMITS)["flags"]
		self.assertIn("Box 1: additional handling: second side 32 in.", flags)
		self.assertIn("Box 1: additional handling: 55 lb.", flags)


class Boxes(unittest.TestCase):
	def test_rows_with_count_one_are_left_alone(self):
		self.assertIsNone(R.expand_counts([box(), box(count=None)]))

	def test_a_count_becomes_one_row_per_box(self):
		boxes = R.expand_counts([box(48, 6, 6, 9, count=3), box(count=1)])
		self.assertEqual(len(boxes), 4)
		self.assertTrue(all(b["count"] == 1 for b in boxes))
		self.assertEqual([b["length"] for b in boxes], [48, 48, 48, 24])
		boxes[0]["length"] = 1
		self.assertEqual(boxes[1]["length"], 48)


class Weights(unittest.TestCase):
	def test_suggested_weight_converts_and_rounds_up(self):
		pounds, unknown = R.suggested_weight(
			[
				{"total_weight": 1, "weight_uom": "Kg"},
				{"weight_per_unit": 4, "stock_qty": 2, "weight_uom": "LB"},
				{"weight_per_unit": 8, "qty": 2, "weight_uom": "Ounce"},
				{"total_weight": 0, "weight_uom": "Kg"},
				{"total_weight": 3, "weight_uom": "Stone"},
			]
		)
		self.assertEqual(pounds, 11.3)  # 1 kg (2.20462) + 8 lb + 16 oz (1 lb), rounded up
		self.assertEqual(unknown, ["Stone"])

	def test_lines_without_a_uom_count_as_pounds(self):
		self.assertEqual(R.suggested_weight([{"total_weight": 2.01}]), (2.1, []))
		self.assertEqual(R.suggested_weight([]), (0.0, []))


class TrackerStatus(unittest.TestCase):
	def test_easypost_statuses_map_to_box_statuses(self):
		self.assertEqual(R.box_status("delivered"), "Delivered")
		self.assertEqual(R.box_status("RETURN_TO_SENDER"), "Returned")
		self.assertEqual(R.box_status("failure"), "Exception")
		self.assertEqual(R.box_status("something_new"), "Something New")
		self.assertEqual(R.box_status(None), "Unknown")

	def test_shipment_is_delivered_only_when_every_box_is(self):
		self.assertEqual(R.shipment_status(["Delivered", "In Transit"], "In Progress"), "In Progress")
		self.assertEqual(R.shipment_status(["Delivered", None], "In Progress"), "In Progress")
		self.assertEqual(R.shipment_status(["Delivered", "Delivered"], "In Progress"), "Delivered")

	def test_returned_wins_and_unknowns_keep_the_current_value(self):
		self.assertEqual(R.shipment_status(["Delivered", "Returned"], "In Progress"), "Returned")
		self.assertEqual(R.shipment_status(["Exception"], "In Progress"), "In Progress")
		self.assertIsNone(R.shipment_status([None, "Unknown"], None))


if __name__ == "__main__":
	unittest.main()
