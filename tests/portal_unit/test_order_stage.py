"""Stage on Sales Orders and Quotations (api/order_stage.py)."""

import ast
import pathlib
import re
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service

MODULE = ROOT + ".api.order_stage"
REPO = pathlib.Path(__file__).resolve().parents[2]
TODAY = date(2026, 11, 20)


def board(status, work_orders=1, eta=None):
	return {"status": status, "work_orders": work_orders, "eta": eta, "no_po": []}


def submitted(**values):
	return Record({"docstatus": 1, "status": "To Deliver and Bill", "per_delivered": 0, **values})


class SalesOrderStage(unittest.TestCase):
	def stage(self, order, view=None, paid=False):
		with load_service(MODULE) as (stage, _):
			result = stage.sales_order_stage(order, view, paid)
			return result and (result["ill_stage"], result["ill_waiting_on"], result["ill_stage_note"])

	def test_drafts_and_terminal_states(self):
		self.assertEqual(self.stage(Record(docstatus=0)), ("Pending Approval", "Us", ""))
		self.assertEqual(self.stage(Record(docstatus=2, ill_stage_override="Held")), ("Cancelled", "", ""))
		self.assertEqual(self.stage(submitted(status="Closed", ill_stage_override="Held"))[0], "Completed")
		self.assertEqual(self.stage(submitted(status="Completed", per_delivered=100))[0], "Completed")
		self.assertEqual(
			self.stage(submitted(status="To Bill", per_delivered=100))[0], "Shipped / In Transit"
		)

	def test_override_wins_until_cleared(self):
		with load_service(MODULE) as (stage, _):
			pb = stage.pb
			order = submitted(ill_stage_override="Delivered", per_delivered=60)
			result = stage.sales_order_stage(order, board(pb.IN_PROD))
			self.assertEqual(result["ill_stage"], "Delivered")
			self.assertEqual(result["ill_stage_note"], "Override · Partially Shipped (60%)")
			self.assertEqual(
				stage.sales_order_stage(Record(docstatus=0, ill_stage_override="Hold for Release"))[
					"ill_stage"
				],
				"Hold for Release",
			)

	def test_hold_reasons_are_their_own_stages(self):
		for hold, waiting in (
			("Hold for Release", "Customer"),
			("Hold for Confirmation", "Customer"),
			("Hold for Ship", "Customer"),
		):
			self.assertEqual(self.stage(submitted(ill_hold_reason=hold))[:2], (hold, waiting))

	def test_production_stages_follow_the_board(self):
		with load_service(MODULE) as (stage, _):
			pb = stage.pb
			cases = {
				pb.PEND_PROD: ("Pend-Prod", "Warehouse"),
				pb.IN_PROD: ("In-Prod", "Warehouse"),
				pb.PAINT: ("Paint", "Vendor"),
				pb.HELD: ("Held", "Us"),
				pb.PEND_SHIP: ("Pend-Ship", "Warehouse"),
			}
			for code, expected in cases.items():
				result = stage.sales_order_stage(submitted(), board(code))
				self.assertEqual((result["ill_stage"], result["ill_waiting_on"]), expected)
			result = stage.sales_order_stage(submitted(), board(pb.PEND_PROD, work_orders=0))
			self.assertEqual((result["ill_stage"], result["ill_waiting_on"]), ("Needs Work Orders", "Us"))
			result = stage.sales_order_stage(submitted(), board(pb.WFP, eta=date(2026, 12, 1)))
			self.assertEqual(
				(result["ill_stage"], result["ill_stage_note"]), ("Waiting for parts", "Parts ETA 2026-12-01")
			)
			self.assertEqual(
				stage.sales_order_stage(submitted(), board(pb.WFP))["ill_stage_note"], "No PO for short parts"
			)
			# Open but not on the board yet: leave it for the sweep.
			self.assertIsNone(stage.sales_order_stage(submitted()))

	def test_ready_and_shipping(self):
		with load_service(MODULE) as (stage, _):
			ready = board(stage.pb.PEND_SHIP)
			name = lambda order, paid=False: stage.sales_order_stage(order, ready, paid)["ill_stage"]  # noqa: E731
			self.assertEqual(name(submitted(ill_proforma_will_call="Will Call")), "Will Call - Ready")
			self.assertEqual(
				name(submitted(ill_proforma_will_call="Proforma")), "Proforma - Awaiting Payment"
			)
			self.assertEqual(name(submitted(ill_proforma_will_call="Proforma"), paid=True), "Pend-Ship")
			partial = stage.sales_order_stage(
				submitted(per_delivered=40, ill_proforma_will_call="Will Call"), ready
			)
			self.assertEqual(
				(partial["ill_stage"], partial["ill_stage_note"]),
				("Partially Shipped", "Partially Shipped (40%)"),
			)
			# Furthest-behind part wins: the rest is still being built.
			building = stage.sales_order_stage(submitted(per_delivered=40), board(stage.pb.IN_PROD))
			self.assertEqual(
				(building["ill_stage"], building["ill_stage_note"]), ("In-Prod", "Partially Shipped (40%)")
			)

	def test_board_honours_the_new_override(self):
		with load_service(ROOT + ".api.production_board") as (pb, _):
			self.assertEqual(pb.order_status(Record(ill_stage_override="Hold for Ship"), [], False), pb.HELD)
			self.assertEqual(pb.order_status(Record(ill_stage_override="In-Prod"), [], False), pb.IN_PROD)
			self.assertEqual(
				pb.order_status(Record(ill_stage_override="Delivered", ill_build_points=0), [], False),
				pb.PEND_SHIP,
			)


class QuotationStage(unittest.TestCase):
	def stage(self, quote, last_sent=None, days=7):
		with load_service(MODULE) as (stage, _):
			result = stage.quotation_stage(quote, TODAY, days, last_sent)
			return result["ill_stage"], result["ill_waiting_on"], result["ill_stage_note"]

	def test_rules(self):
		sent = {"docstatus": 1, "status": "Open", "transaction_date": "2026-11-01"}
		self.assertEqual(self.stage(Record(docstatus=0))[:2], ("Drafting", "Us"))
		self.assertEqual(
			self.stage(Record(docstatus=0, ill_stage_override="Waiting on Vendor"))[:2],
			("Waiting on Vendor", "Vendor"),
		)
		self.assertEqual(self.stage(Record(docstatus=2))[0], "Cancelled")
		self.assertEqual(self.stage(Record(sent, status="Ordered", ill_stage_override="Revising"))[0], "Won")
		self.assertEqual(self.stage(Record(sent, status="Partially Ordered"))[0], "Won")
		self.assertEqual(self.stage(Record(sent, status="Lost"))[0], "Lost")
		self.assertEqual(self.stage(Record(sent, valid_till="2026-11-19"))[0], "Expired")
		self.assertEqual(self.stage(Record(sent, status="Replied")), ("Follow Up", "Us", "Customer replied"))
		self.assertEqual(self.stage(Record(sent), last_sent="2026-11-18 10:00:00")[:2], ("Sent", "Customer"))
		self.assertEqual(self.stage(Record(sent, ill_quote_sent_on="2026-11-15"))[0], "Sent")
		self.assertEqual(self.stage(Record(sent)), ("Follow Up", "Us", "Sent 19 days ago, no reply"))
		self.assertEqual(self.stage(Record(sent, ill_stage_override="Revising"))[0], "Revising")


class Refresh(unittest.TestCase):
	def test_only_changed_orders_are_written_without_touching_modified(self):
		with load_service(MODULE) as (stage, frappe):
			frappe.get_meta.return_value.has_field.return_value = True
			same = submitted(name="SO-1", ill_stage="In-Prod", ill_waiting_on="Warehouse", ill_stage_note="")
			moved = submitted(name="SO-2", ill_stage="Pend-Prod", ill_waiting_on="Warehouse")
			frappe.get_all.side_effect = lambda doctype, **kw: (
				[same, moved]
				if "ill_stage" in kw["filters"] and kw["filters"]["ill_stage"][0] == "not in"
				else []
			)
			view = {"SO-1": board(stage.pb.IN_PROD), "SO-2": board(stage.pb.PEND_SHIP)}
			with patch.object(stage, "board_view", return_value=view):
				self.assertEqual(stage.refresh_sales_orders(), 1)
			frappe.db.set_value.assert_called_once_with(
				"Sales Order",
				"SO-2",
				{"ill_stage": "Pend-Ship", "ill_waiting_on": "Warehouse", "ill_stage_note": ""},
				update_modified=False,
			)

	def test_proforma_paid_by_advance_or_settled_invoices(self):
		with load_service(MODULE) as (stage, frappe):
			orders = [
				Record(name="A", grand_total=100, rounded_total=100, advance_paid=100),
				Record(name="B", grand_total=100, advance_paid=0, per_billed=100),
				Record(name="C", grand_total=100, advance_paid=0, per_billed=100),
				Record(name="D", grand_total=100, advance_paid=10, per_billed=50),
			]

			def get_all(doctype, **kw):
				if doctype == "Sales Invoice Item":
					return [Record(parent="INV-B", sales_order="B"), Record(parent="INV-C", sales_order="C")]
				return [
					Record(name="INV-B", outstanding_amount=0),
					Record(name="INV-C", outstanding_amount=25),
				]

			frappe.get_all.side_effect = get_all
			self.assertEqual(stage.paid_orders(orders), {"A", "B"})

	def test_drafts_queue_nothing_except_work_orders(self):
		with load_service(MODULE) as (stage, frappe):
			frappe.enqueue = MagicMock()
			stage.queue_refresh(Record(doctype="Purchase Order", docstatus=0))
			frappe.enqueue.assert_not_called()
			stage.queue_refresh(Record(doctype="Work Order", docstatus=0))
			kwargs = frappe.enqueue.call_args.kwargs
			self.assertEqual(
				(kwargs["job_id"], kwargs["deduplicate"], kwargs["enqueue_after_commit"]),
				(stage.JOB_ID, True, True),
			)
			frappe.flags["in_migrate"] = True
			frappe.enqueue.reset_mock()
			stage.queue_refresh(Record(doctype="Delivery Note", docstatus=1))
			frappe.enqueue.assert_not_called()

	def test_clearing_the_override_keeps_the_stored_stage(self):
		with load_service(MODULE) as (stage, _):
			doc = MagicMock()
			fields = submitted(ill_stage="In-Prod", ill_stage_override="")
			doc.get.side_effect = fields.get
			doc.get_doc_before_save.return_value = Record(
				ill_stage="Held", ill_waiting_on="Us", ill_stage_note="Override"
			)
			stage.sales_order_before_update_after_submit(doc)
			doc.set.assert_any_call("ill_stage", "Held")
			fields["ill_stage_override"] = "Paint"
			doc.set.reset_mock()
			stage.sales_order_before_update_after_submit(doc)
			doc.set.assert_any_call("ill_stage", "Paint")


class Wiring(unittest.TestCase):
	def python_colours(self):
		with load_service(MODULE) as (stage, _):
			return {dt: {s: c for s, _w, c in rows} for dt, rows in stage.STAGES.items()}

	def test_js_colours_match_python(self):
		expected = self.python_colours()
		for path in ("order_stage.js", "order_stage_list.js"):
			source = (REPO / "illumenate_lighting" / "public" / "js" / path).read_text(encoding="utf-8")
			block = source[source.index("const ILL_STAGE_COLORS") : source.index("};") + 2]
			found, current = {}, None
			for line in block.splitlines():
				head = re.match(r'\s*"([^"]+)": \{$', line)
				pair = re.match(r'\s*"([^"]+)": "([^"]+)",$', line)
				if head:
					current = found.setdefault(head.group(1), {})
				elif pair and current is not None:
					current[pair.group(1)] = pair.group(2)
			self.assertEqual(found, expected, path)

	def test_patch_offers_every_stage_and_no_terminal_override(self):
		with load_service(
			ROOT.rsplit(".", 1)[0] + ".patches.add_order_stage_fields",
			extras={"frappe.custom.doctype.custom_field.custom_field": MagicMock()},
		) as (patch_module, _):
			for doctype, rows in patch_module.order_stage.STAGES.items():
				fields = {f["fieldname"]: f for f in patch_module._fields(doctype, "x")}
				self.assertEqual(fields["ill_stage"]["options"].split("\n")[1:], [s for s, _w, _c in rows])
				override = fields["ill_stage_override"]["options"].split("\n")
				self.assertFalse({"Completed", "Cancelled", "Won"} & set(override))
				self.assertTrue(fields["ill_stage_override"]["allow_on_submit"])

	def test_hooks_wire_events_scripts_and_sweep(self):
		tree = ast.parse((REPO / "illumenate_lighting" / "hooks.py").read_text(encoding="utf-8"))
		values = {
			t.id: node.value
			for node in tree.body
			if isinstance(node, ast.Assign)
			for t in node.targets
			if isinstance(t, ast.Name)
		}
		events = ast.literal_eval(values["doc_events"])
		queue = "illumenate_lighting.illumenate_lighting.api.order_stage.queue_refresh"
		for doctype in (
			"Sales Order",
			"Work Order",
			"Delivery Note",
			"Purchase Order",
			"Purchase Receipt",
			"Stock Entry",
			"Payment Entry",
			"Sales Invoice",
		):
			self.assertEqual(events[doctype]["on_change"], queue, doctype)
		self.assertIn(
			queue.replace("queue_refresh", "quotation_before_submit"), events["Quotation"]["before_submit"]
		)
		cron = ast.literal_eval(values["scheduler_events"])["cron"]
		self.assertIn(
			"illumenate_lighting.illumenate_lighting.api.order_stage.refresh_all", cron["*/15 * * * *"]
		)
		self.assertIn(
			"illumenate_lighting.patches.add_order_stage_fields",
			(REPO / "illumenate_lighting" / "patches.txt").read_text(),
		)


if __name__ == "__main__":
	unittest.main()
