"""Label queue (api/labels.py): planning, reconcile, ordering, formatting and the hooks.

Pure functions run as they are; the hooks run against the Frappe doubles in test_services.
"""

import unittest
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

TEMPLATES = [
	{
		"name": "Work order",
		"layout": "work_order",
		"label_stock": "1.5 x 2.5",
		"applies_to": "All",
		"quantity_rule": "Per document",
		"copies": 1,
		"packet_order": 10,
	},
	{
		"name": "Product",
		"layout": "product",
		"label_stock": "1.5 x 2.5",
		"applies_to": "Not light engine",
		"quantity_rule": "Per unit",
		"copies": 1,
		"packet_order": 20,
	},
	{
		"name": "Light engine",
		"layout": "light_engine",
		"label_stock": "1.5 x 2.5",
		"applies_to": "Light engine",
		"quantity_rule": "Per unit",
		"copies": 1,
		"packet_order": 20,
	},
	{
		"name": "Kit piece",
		"layout": "kit_piece",
		"label_stock": "1.5 x 2.5",
		"applies_to": "Ship-in-pieces line",
		"quantity_rule": "Per kit piece",
		"copies": 1,
		"packet_order": 30,
	},
	{
		"name": "Packet checklist",
		"layout": "packet_4x6",
		"label_stock": "4 x 6",
		"applies_to": "All",
		"quantity_rule": "Per document",
		"copies": 1,
		"packet_order": 90,
	},
]


def info(kind="assembled", qty=12, sales_order="SO-1", name="WO-1"):
	return {
		"doctype": "Work Order",
		"name": name,
		"kind": kind,
		"qty": qty,
		"sales_order": sales_order,
		"context": {"wo": name, "so": sales_order or "", "fixture_type": "L1"},
	}


class Labels(unittest.TestCase):
	def setUp(self):
		self.ctx = load_service(ROOT + ".api.labels")
		self.labels, self.frappe = self.ctx.__enter__()
		self.addCleanup(self.ctx.__exit__, None, None, None)

	# ------------------------------------------------------------ kinds

	def test_work_order_kinds_first_rule_wins(self):
		kind = self.labels.work_order_kind
		self.assertEqual(kind({}, {"ill_configured_fixture": "CF"}, engine={"key": "LE1"}), "light_engine")
		self.assertEqual(kind({}, {"ill_configured_group": "G", "ill_configured_fixture": "CF"}), "group_run")
		self.assertEqual(kind({"ill_configured_fixture": "CF"}, {}), "assembled")
		self.assertEqual(kind({}, {"ill_configured_fixture": "CF"}), "assembled")
		self.assertEqual(kind({}, {"ill_configured_tape_neon": "TN"}), "tape_neon")
		self.assertEqual(kind({}, {"ill_configured_led_sheet": "LS"}), "led_sheet")
		self.assertEqual(kind({}, None), "not_configured")

	def test_applies_to(self):
		applies = self.labels.template_applies
		self.assertFalse(applies({"applies_to": "Not light engine"}, "light_engine"))
		self.assertFalse(applies({"applies_to": "Not light engine"}, "group_run"))
		self.assertTrue(applies({"applies_to": "Not light engine"}, "tape_neon"))
		self.assertTrue(applies({"applies_to": "Light engine"}, "group_run"))
		self.assertTrue(applies({"applies_to": None}, "led_sheet"))

	# ------------------------------------------------------------ planning

	def test_twelve_units_make_one_wo_twelve_product_one_packet(self):
		wanted = self.labels.plan_labels(TEMPLATES, info())
		names = [w["template"] for w in wanted]
		self.assertEqual(names.count("Work order"), 1)
		self.assertEqual(names.count("Product"), 12)
		self.assertEqual(names.count("Packet checklist"), 1)
		self.assertNotIn("Light engine", names)
		product = [w for w in wanted if w["template"] == "Product"]
		self.assertEqual(product[2]["context"]["unit_text"], "Unit 3 of 12")
		self.assertEqual(product[0]["context"]["doc_label"], "SALES ORDER")
		packet = wanted[-1]
		self.assertEqual(packet["label_stock"], "4 x 6")
		self.assertEqual(packet["context"]["checklist"], ["Work order label", "Product labels x 12"])

	def test_small_packets_list_each_unit(self):
		packet = self.labels.plan_labels(TEMPLATES, info(qty=2))[-1]
		self.assertEqual(
			packet["context"]["checklist"],
			["Work order label", "Product label, unit 1 of 2", "Product label, unit 2 of 2"],
		)

	def test_light_engine_gets_engine_labels_not_product_labels(self):
		names = [w["template"] for w in self.labels.plan_labels(TEMPLATES, info(kind="light_engine", qty=3))]
		self.assertEqual(names.count("Light engine"), 3)
		self.assertEqual(names.count("Product"), 0)

	def test_stock_build_without_sales_order_gets_wo_and_packet_only(self):
		wanted = self.labels.plan_labels(TEMPLATES, info(kind="not_configured", sales_order=None))
		self.assertEqual([w["template"] for w in wanted], ["Work order", "Packet checklist"])

	def test_kit_pieces_wait_for_phase_two(self):
		names = [w["template"] for w in self.labels.plan_labels(TEMPLATES, info(kind="light_engine"))]
		self.assertNotIn("Kit piece", names)

	def test_dedupe_keys_are_stable_and_unique(self):
		first = [w["dedupe_key"] for w in self.labels.plan_labels(TEMPLATES, info())]
		second = [w["dedupe_key"] for w in self.labels.plan_labels(TEMPLATES, info())]
		self.assertEqual(first, second)
		self.assertEqual(len(first), len(set(first)))
		self.assertIn("Product:Work Order:WO-1:-:3:1", first)

	def test_copies_make_extra_keys(self):
		templates = [{**TEMPLATES[0], "copies": 2}]
		keys = [w["dedupe_key"] for w in self.labels.plan_labels(templates, info())]
		self.assertEqual(keys, ["Work order:Work Order:WO-1:-:1:1", "Work order:Work Order:WO-1:-:1:1:c2"])

	# ------------------------------------------------------------ reconcile

	def _jobs(self, wanted, status="Queued"):
		return [
			{
				"name": f"J{i}",
				"dedupe_key": w["dedupe_key"],
				"status": status,
				"context_hash": self.labels.context_hash(w["context"]),
				"is_stale": 0,
			}
			for i, w in enumerate(wanted)
		]

	def test_new_work_order_inserts_everything(self):
		wanted = self.labels.plan_labels(TEMPLATES, info())
		plan = self.labels.reconcile([], wanted)
		self.assertEqual(len(plan["insert"]), 14)
		self.assertFalse(plan["cancel"] or plan["void"] or plan["refresh"])

	def test_reconcile_is_idempotent(self):
		wanted = self.labels.plan_labels(TEMPLATES, info())
		plan = self.labels.reconcile(self._jobs(wanted), wanted)
		self.assertEqual(sum(len(v) for v in plan.values()), 0)

	def test_qty_down_cancels_unprinted_extras_and_refreshes_the_rest(self):
		before = self.labels.plan_labels(TEMPLATES, info(qty=12))
		after = self.labels.plan_labels(TEMPLATES, info(qty=10))
		plan = self.labels.reconcile(self._jobs(before), after)
		self.assertEqual(len(plan["cancel"]), 2)
		# unit_count changed from 12 to 10 on every product label, so their content refreshed
		self.assertEqual(len(plan["refresh"]), 11)
		self.assertFalse(plan["insert"] or plan["void"])

	def test_printed_labels_no_longer_wanted_are_voided_with_reason(self):
		before = self.labels.plan_labels(TEMPLATES, info(qty=12))
		after = self.labels.plan_labels(TEMPLATES, info(qty=10))
		plan = self.labels.reconcile(
			self._jobs(before, "Printed"), after, "Work order WO-1 changed (now qty 10)"
		)
		self.assertEqual(len(plan["void"]), 2)
		self.assertEqual(plan["void"][0][1], "Work order WO-1 changed (now qty 10)")
		self.assertEqual(len(plan["stale"]), 11)

	def test_stale_is_marked_once(self):
		before = self.labels.plan_labels(TEMPLATES[:1], info())
		changed = self.labels.plan_labels(TEMPLATES[:1], {**info(), "context": {"wo": "WO-1", "so": "SO-2"}})
		jobs = self._jobs(before, "Printed")
		jobs[0]["is_stale"] = 1
		self.assertEqual(self.labels.reconcile(jobs, changed)["stale"], [])

	def test_cancelled_or_void_jobs_come_back_when_wanted_again(self):
		wanted = self.labels.plan_labels(TEMPLATES[:1], info())
		plan = self.labels.reconcile(self._jobs(wanted, "Cancelled"), wanted)
		self.assertEqual([name for name, _row in plan["requeue"]], ["J0"])
		self.assertFalse(plan["insert"])

	def test_release_cancels_queued_and_voids_printed(self):
		jobs = [
			{"name": "A", "dedupe_key": "a", "status": "Queued"},
			{"name": "B", "dedupe_key": "b", "status": "Printed"},
			{"name": "C", "dedupe_key": "c", "status": "Sent"},
			{"name": "D", "dedupe_key": "d", "status": "Void"},
		]
		plan = self.labels.reconcile(jobs, [], "Work order cancelled")
		self.assertEqual(plan["cancel"], ["A"])
		self.assertEqual([n for n, _ in plan["void"]], ["B", "C"])

	# ------------------------------------------------------------ ordering

	def test_groups_follow_print_order_and_jobs_packet_order(self):
		groups = [
			{
				"stock": "4 x 6",
				"print_order": 2,
				"jobs": [{"name": "P", "work_order": "WO-1", "packet_order": 90}],
			},
			{
				"stock": "1.5 x 2.5",
				"print_order": 1,
				"jobs": [
					{
						"name": "X3",
						"work_order": "WO-2",
						"ship_by": "2026-12-01",
						"packet_order": 20,
						"unit_no": 1,
					},
					{
						"name": "X2",
						"work_order": "WO-1",
						"ship_by": "2026-12-05",
						"packet_order": 20,
						"unit_no": 2,
					},
					{
						"name": "X1",
						"work_order": "WO-1",
						"ship_by": "2026-12-05",
						"packet_order": 10,
						"unit_no": 1,
					},
					{
						"name": "X4",
						"work_order": "WO-1",
						"ship_by": "2026-12-05",
						"packet_order": 20,
						"unit_no": 1,
					},
					{"name": "R", "reference_name": "R-00001", "packet_order": 50},
				],
			},
		]
		ordered = self.labels.order_groups(groups)
		self.assertEqual([g["stock"] for g in ordered], ["1.5 x 2.5", "4 x 6"])
		self.assertEqual([j["name"] for j in ordered[0]["jobs"]], ["X3", "X1", "X4", "X2", "R"])

	def test_order_groups_works_with_one_empty_group(self):
		self.assertEqual(
			self.labels.order_groups([{"stock": "4 x 6", "print_order": 2, "jobs": []}])[0]["jobs"], []
		)

	# ------------------------------------------------------------ formatting

	def test_fit_pt_bounds(self):
		fit = self.labels.fit_pt
		self.assertEqual(fit("L1", 4, 24, 11), 24)
		self.assertEqual(fit("", 4, 24, 11), 24)
		self.assertEqual(fit("ABCDEFGH", 4, 24, 11), 12)
		self.assertEqual(fit("X" * 100, 4, 24, 11), 11)
		self.assertEqual(fit("ABCDEFG", 4, 24, 11), 13.5)

	def test_truncate(self):
		self.assertEqual(self.labels.truncate("ABCDEFGHIJ", 5), "ABCD…")
		self.assertEqual(self.labels.truncate("ABC", 5), "ABC")
		self.assertEqual(self.labels.truncate(None, 5), "")

	def test_feet_inches_matches_the_build_format(self):
		fi = self.labels.feet_inches
		self.assertEqual(fi(304.8 * 10 + 25.4 * 3), "10' 3\"")
		self.assertEqual(fi(304.8 * 100), "100'")
		self.assertEqual(fi(25.4 * 7.5), '7.5"')
		self.assertEqual(fi(304.8 * 12 - 0.5), "12'")

	def test_fmt_date(self):
		self.assertEqual(self.labels.fmt_date("2026-12-04"), "12/04/26")
		self.assertEqual(self.labels.fmt_date(None), "")

	def test_build_context_formats_and_leaves_blanks_blank(self):
		wo = {
			"name": "WO-1",
			"qty": 12,
			"sales_order": "SO-1",
			"production_item": "ITEM",
			"expected_delivery_date": None,
			"required_items": [
				{"item_code": f"P{i}", "required_qty": 2, "stock_uom": "Nos"} for i in range(12)
			],
		}
		row = {
			"item_code": "ILL-PN",
			"ill_fixture_type": "L1",
			"ill_section_label": None,
			"ill_requested_length_mm": 304.8 * 4,
		}
		c = self.labels.build_context(
			"assembled", wo, {"customer_name": "Acme", "delivery_date": "2026-12-08"}, row
		)
		self.assertEqual(c["part_number"], "ILL-PN")
		self.assertEqual(c["length"], "4'")
		self.assertEqual(c["section"], "")
		self.assertEqual(c["po"], "")
		self.assertEqual(c["ship_by"], "12/08/26")
		self.assertEqual(c["build_qty"], "12")
		self.assertEqual(len(c["pull"]), 10)
		self.assertEqual(c["pull_more"], 2)
		self.assertNotIn("N/A", str(c))
		fallback = self.labels.build_context("not_configured", wo, {}, {}, fixture_part="DISPLAY-PN")
		self.assertEqual(fallback["part_number"], "DISPLAY-PN")

	def test_code128_and_qr_are_svg(self):
		modules = self.labels.code128_modules("R-00041")
		self.assertTrue(modules.startswith("11010010000"))  # Start Code B
		self.assertTrue(modules.endswith("1100011101011"))  # Stop
		self.assertTrue(self.labels.code128_svg("R-00041").startswith("data:image/svg+xml;base64,"))
		self.assertEqual(self.labels.code128_svg(""), "")
		self.assertTrue(
			self.labels.qr_svg("https://erp.test/app/work-order/WO-1").startswith("data:image/svg+xml")
		)

	# ------------------------------------------------------------ hooks

	def _flags(self, enabled=True, auto=1):
		values = {"labels_enabled": 1 if enabled else 0, "labels_auto_work_order": auto}
		self.frappe.db.get_single_value.side_effect = lambda _doctype, field: values.get(field)
		self.frappe.enqueue = MagicMock()
		self.frappe.log_error = MagicMock()
		self.frappe.get_traceback = lambda: "trace"

	def test_hooks_do_nothing_when_labels_are_off(self):
		self._flags(enabled=False)
		doc = MagicMock(name="WO-1")
		self.labels.on_work_order_insert(doc)
		self.labels.on_work_order_update(doc)
		self.labels.on_work_order_cancel(doc)
		self.labels.on_work_order_trash(doc)
		self.frappe.enqueue.assert_not_called()
		self.frappe.get_all.assert_not_called()

	def test_insert_enqueues_after_commit_with_a_job_id(self):
		self._flags()
		self.labels.on_work_order_insert(Record(name="WO-9"))
		kwargs = self.frappe.enqueue.call_args.kwargs
		self.assertEqual(kwargs["work_order"], "WO-9")
		self.assertTrue(kwargs["enqueue_after_commit"])
		self.assertEqual(kwargs["job_id"], "ill-labels-WO-9")

	def test_insert_respects_the_auto_switch(self):
		self._flags(auto=0)
		self.labels.on_work_order_insert(Record(name="WO-9"))
		self.frappe.enqueue.assert_not_called()

	def test_update_only_replans_on_watched_changes(self):
		self._flags()
		doc = MagicMock()
		doc.name = "WO-9"
		doc.get_doc_before_save.return_value = None
		self.labels.on_work_order_update(doc)  # brand new: after_insert handles it
		self.frappe.enqueue.assert_not_called()
		doc.get_doc_before_save.return_value = object()
		doc.has_value_changed.side_effect = lambda field: field == "status"
		self.labels.on_work_order_update(doc)
		self.frappe.enqueue.assert_not_called()
		doc.has_value_changed.side_effect = lambda field: field == "qty"
		self.labels.on_work_order_update(doc)
		self.frappe.enqueue.assert_called_once()

	def test_hooks_never_raise(self):
		self._flags()
		self.frappe.enqueue.side_effect = RuntimeError("redis down")
		self.labels.on_work_order_insert(Record(name="WO-9"))
		with patch.object(self.labels, "release_document", side_effect=RuntimeError("db")):
			self.labels.on_work_order_cancel(Record(name="WO-9"))
			self.labels.on_work_order_trash(Record(name="WO-9"))
		self.assertEqual(self.frappe.log_error.call_count, 3)

	def test_old_frappe_without_deduplicate_still_enqueues(self):
		self._flags()
		calls = []

		def enqueue(method, **kwargs):
			if "deduplicate" in kwargs:
				raise TypeError("unexpected keyword")
			calls.append(kwargs)

		self.frappe.enqueue = enqueue
		self.labels.on_work_order_insert(Record(name="WO-9"))
		self.assertEqual(calls[0]["job_id"], "ill-labels-WO-9")

	def test_document_labels_are_quiet_without_a_role(self):
		self._flags()
		self.frappe.get_roles.return_value = ["Dealer"]
		self.assertEqual(self.labels.get_document_labels("Work Order", "WO-1")["enabled"], False)


class HooksRegistered(unittest.TestCase):
	def test_hooks_file_wires_the_label_queue(self):
		from pathlib import Path

		source = (Path(__file__).resolve().parents[2] / "illumenate_lighting" / "hooks.py").read_text(
			encoding="utf-8"
		)
		for event in (
			"on_work_order_insert",
			"on_work_order_update",
			"on_work_order_cancel",
			"on_work_order_trash",
		):
			self.assertIn(f"api.labels.{event}", source)
		self.assertIn('"ilL-Label-Print-Job"]', source)
		self.assertIn("public/js/work_order_labels.js", source)
		self.assertIn("public/js/sales_order_labels.js", source)


if __name__ == "__main__":
	unittest.main()
