"""Draft Quotations / Sales Orders and their Fixture Schedule keep the same scope."""

import types
import unittest
from unittest.mock import MagicMock, patch

from test_services import ROOT, Record, load_service


class Row(Record):
	__setattr__ = dict.__setitem__

	def set(self, key, value):
		self[key] = value


class Doc(Row):
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.setdefault("flags", Record())
		self.save = MagicMock()
		self.add_comment = MagicMock()

	def append(self, field, values):
		row = Row(values)
		row.setdefault("name", None)
		self[field].append(row)
		return row


def schedule_line(name, **values):
	return Row({"name": name, "qty": 1, "line_id": name, "location": None, "notes": "", **values})


def quote_row(name, line=None, **values):
	return Row({"name": name, "item_code": "ITEM", "qty": 1, "conversion_factor": 1, "ill_schedule_line_id": line, **values})


NEXT_ID = types.SimpleNamespace(_next_fixture_type=lambda schedule, used: "A9")


def service():
	return load_service(ROOT + ".api.schedule_sync", {ROOT + ".api.desk_configurator": NEXT_ID})


class PlanTransactionChanges(unittest.TestCase):
	def test_a_row_added_by_hand_becomes_a_line(self):
		with service() as (sync, _):
			before = [quote_row("R1", "L1")]
			rows = [quote_row("R1", "L1"), quote_row("R2", item_code="CLIP")]
			plan = sync.plan_transaction_changes(["L1"], before, rows, newly_linked=False)
		self.assertEqual([row.name for row in plan["add"]], ["R2"])
		self.assertEqual(plan["remove"], [])

	def test_supplies_alternatives_and_old_unlinked_rows_are_not_added(self):
		with service() as (sync, _):
			legacy = quote_row("R0", item_code="PS-OLD")
			rows = [
				legacy,
				quote_row("R1", item_code="PS", ill_is_power_supply_line=1),
				quote_row("R2", item_code="ALT", is_alternative=1),
			]
			plan = sync.plan_transaction_changes(["L1"], [legacy], rows, newly_linked=False)
			self.assertEqual(plan["add"], [])
			# Linking the schedule for the first time brings the existing rows along.
			linked = sync.plan_transaction_changes(["L1"], [legacy], [legacy], newly_linked=True)
			self.assertEqual(linked["add"], [legacy])

	def test_a_line_goes_only_with_its_last_row(self):
		with service() as (sync, _):
			before = [quote_row("R1", "KIT"), quote_row("R2", "KIT"), quote_row("R3", "L2")]
			plan = sync.plan_transaction_changes(["KIT", "L2"], before, [before[0]], newly_linked=False)
		self.assertEqual(plan["remove"], ["L2"])

	def test_edits_flow_back_only_for_one_row_lines(self):
		with service() as (sync, _):
			before = [quote_row("R1", "L1"), quote_row("R2", "KIT"), quote_row("R3", "KIT")]
			rows = [quote_row("R1", "L1", qty=4), quote_row("R2", "KIT", qty=9), quote_row("R3", "KIT")]
			plan = sync.plan_transaction_changes(["L1", "KIT"], before, rows, newly_linked=False)
		self.assertEqual([(row.name, was.name) for row, was in plan["update"]], [("R1", "R1")])


class LineUpdates(unittest.TestCase):
	def test_accessory_line_takes_quantity_item_and_labels(self):
		with service() as (sync, _):
			line = schedule_line("L1", manufacturer_type="ACCESSORY", accessory_item="CLIP")
			before = quote_row("R1", "L1", item_code="CLIP")
			row = quote_row("R1", "L1", item_code="CLIP-2", qty=3, ill_section_label="Lobby", ill_fixture_type="X1")
			changes = sync.line_updates(line, row, before)
		self.assertEqual(changes, {"qty": 3, "accessory_item": "CLIP-2", "location": "Lobby", "line_id": "X1"})

	def test_supply_lines_follow_their_fixture(self):
		with service() as (sync, _):
			line = schedule_line("P1", manufacturer_type="ACCESSORY", power_supply_for_line="K1")
			changes = sync.line_updates(line, quote_row("R1", "P1", qty=5), quote_row("R1", "P1"))
		self.assertEqual(changes, {})

	def test_fractional_or_multi_row_quantities_never_reach_the_schedule(self):
		with service() as (sync, _):
			kit = schedule_line("K", manufacturer_type="ILLUMENATE", product_type="Extrusion Kit", variant_selections="{}")
			self.assertEqual(sync.line_updates(kit, quote_row("R", "K", qty=6), quote_row("R", "K")), {})
			fixture = schedule_line("F", manufacturer_type="ILLUMENATE", configured_fixture="CF-1")
			self.assertEqual(sync.line_updates(fixture, quote_row("R", "F", qty=2.5), quote_row("R", "F")), {})


class PlanScheduleChanges(unittest.TestCase):
	def test_classifies_line_changes(self):
		with service() as (sync, _):
			before = [
				schedule_line("SAME"),
				schedule_line("GONE"),
				schedule_line("RECONF", configured_fixture="CF-1"),
				schedule_line("MORE", qty=2),
				schedule_line("MOVED", location="Lobby"),
			]
			after = [
				schedule_line("SAME"),
				schedule_line("RECONF", configured_fixture="CF-2"),
				schedule_line("MORE", qty=6),
				schedule_line("MOVED", location="Hall"),
				schedule_line("NEW"),
			]
			plan = sync.plan_schedule_changes(before, after)
		self.assertEqual(plan["added"], ["NEW"])
		self.assertEqual(plan["removed"], ["GONE"])
		self.assertEqual(plan["rebuilt"], ["RECONF"])
		self.assertEqual(plan["scaled"], {"MORE": 3.0})
		self.assertEqual(plan["relabelled"], ["MOVED"])

	def test_new_rows_sit_with_their_schedule_neighbours(self):
		with service() as (sync, _):
			items = [quote_row("R1", "L1"), quote_row("R3", "L3"), quote_row("FREIGHT"), quote_row("N2", "L2"), quote_row("N0", "L0")]
			placed = sync.place_new_rows(["L0", "L1", "L2", "L3"], items, 3)
		self.assertEqual([row.name for row in placed], ["N0", "R1", "N2", "R3", "FREIGHT"])
		self.assertEqual([row.idx for row in placed], [1, 2, 3, 4, 5])


def quotation(items, before_items, **values):
	doc = Doc({"doctype": "Quotation", "name": "QTN-1", "docstatus": 0, "ill_fixture_schedule": "SCH-1", "items": items, **values})
	before = Doc({"ill_fixture_schedule": "SCH-1", "items": before_items}) if before_items is not None else None
	doc.get_doc_before_save = lambda: before
	return doc


def schedule(lines):
	doc = Doc({"doctype": "ilL-Project-Fixture-Schedule", "name": "SCH-1", "status": "DRAFT", "lines": lines})

	def save():
		for index, line in enumerate(doc.lines, 1):
			line.name = line.name or f"NEW-{index}"

	doc.save = MagicMock(side_effect=save)
	return doc


class TransactionToSchedule(unittest.TestCase):
	def run_sync(self, doc, sched, item=None, is_open=True):
		with service() as (sync, frappe):
			frappe.db.exists.return_value = True
			frappe.get_doc.return_value = sched
			frappe.db.get_value.return_value = item
			frappe.log_error = MagicMock()
			frappe.get_traceback = MagicMock(return_value="")
			with patch.object(sync, "schedule_is_open", return_value=is_open):
				sync.on_transaction_validate(doc)
			return frappe

	def test_accessory_added_in_the_quote_reaches_the_schedule(self):
		fixture = schedule_line("L1", manufacturer_type="ILLUMENATE", configured_fixture="CF-1")
		sched = schedule([fixture])
		configured = quote_row("R1", "L1", item_code="FIX")
		clip = quote_row("R2", item_code="CLIP", qty=4, ill_section_label="Lobby")
		doc = quotation([configured, clip], [configured])
		item = Record(item_name="Mounting clip", is_stock_item=1, is_sales_item=1, disabled=0, has_variants=0)
		frappe = self.run_sync(doc, sched, item)

		added = sched.lines[-1]
		self.assertEqual(
			(added.manufacturer_type, added.accessory_item, added.qty, added.location, added.line_id),
			("ACCESSORY", "CLIP", 4, "Lobby", "A9"),
		)
		sched.save.assert_called_once()
		self.assertEqual(sched.flags["ill_schedule_sync_source"], ("Quotation", "QTN-1"))
		self.assertTrue(sched.flags.ignore_permissions)
		self.assertEqual((clip.ill_schedule_line_id, clip.ill_fixture_type), (added.name, "A9"))
		self.assertIn("1 line(s) added", frappe.msgprint.call_args.args[0])

	def test_freight_and_services_stay_on_the_quote(self):
		sched = schedule([])
		freight = quote_row("R1", item_code="FREIGHT")
		doc = quotation([freight], [])
		self.run_sync(doc, sched, Record(item_name="Freight", is_stock_item=0, is_sales_item=1))
		self.assertEqual(sched.lines, [])
		sched.save.assert_not_called()
		self.assertIsNone(freight.ill_schedule_line_id)

	def test_removing_a_fixture_drops_its_line_and_its_supply_rows(self):
		fixture = schedule_line("L1", manufacturer_type="ILLUMENATE", configured_fixture="CF-1", line_key="K1")
		supply = schedule_line("P1", manufacturer_type="ACCESSORY", accessory_item="PS", power_supply_for_line="K1")
		sched = schedule([fixture, supply])
		# The schedule's own validate drops supplies whose fixture line is gone.
		sched.save.side_effect = lambda: sched.set("lines", [line for line in sched.lines if not line.get("power_supply_for_line")])
		fixture_row, supply_row, other = quote_row("R1", "L1"), quote_row("R2", "P1", ill_is_power_supply_line=1), quote_row("R3")
		doc = quotation([supply_row, other], [fixture_row, supply_row, other])
		self.run_sync(doc, sched)
		self.assertEqual(sched.lines, [])
		self.assertEqual([row.name for row in doc["items"]], ["R3"])

	def test_fixture_quantity_drives_its_supply_rows(self):
		fixture = schedule_line("L1", manufacturer_type="ILLUMENATE", configured_fixture="CF-1", line_key="K1", qty=1)
		supply = schedule_line("P1", manufacturer_type="ACCESSORY", accessory_item="PS", power_supply_for_line="K1", qty=2)

		def reconcile():
			supply.qty = 2 * fixture.qty

		sched = schedule([fixture, supply])
		sched.save.side_effect = reconcile
		before = [quote_row("R1", "L1", rate=500), quote_row("R2", "P1", qty=2, rate=40, ill_is_power_supply_line=1)]
		rows = [quote_row("R1", "L1", qty=3, rate=500), quote_row("R2", "P1", qty=2, rate=40, ill_is_power_supply_line=1)]
		self.run_sync(quotation(rows, before), sched)
		self.assertEqual((fixture.qty, supply.qty), (3, 6))
		self.assertEqual([(row.qty, row.rate) for row in rows], [(3, 500), (6.0, 40)])

	def test_closed_states_are_left_alone(self):
		for doc, is_open in (
			(quotation([quote_row("R2", item_code="CLIP")], [], docstatus=1), True),
			(quotation([quote_row("R2", item_code="CLIP")], []), False),
			(quotation([quote_row("R2", item_code="CLIP")], None, amended_from="QTN-0"), True),
			(quotation([quote_row("R2", item_code="CLIP")], [], ill_fixture_schedule=None), True),
		):
			sched = schedule([])
			self.run_sync(doc, sched, Record(item_name="Clip", is_stock_item=1, is_sales_item=1), is_open=is_open)
			sched.save.assert_not_called()

	def test_switching_schedule_versions_does_not_rewrite_either(self):
		sched = schedule([schedule_line("L1")])
		doc = quotation([quote_row("R2", item_code="CLIP")], [])
		doc.get_doc_before_save = lambda: Doc({"ill_fixture_schedule": "SCH-0", "items": []})
		self.run_sync(doc, sched, Record(item_name="Clip", is_stock_item=1, is_sales_item=1))
		sched.save.assert_not_called()

	def test_a_failed_schedule_write_never_blocks_the_quote(self):
		sched = schedule([])
		sched.save.side_effect = RuntimeError("schedule rejected the line")
		clip = quote_row("R2", item_code="CLIP")
		frappe = self.run_sync(quotation([clip], []), sched, Record(item_name="Clip", is_stock_item=1, is_sales_item=1))
		frappe.db.rollback.assert_called_once_with(save_point="ill_schedule_sync")
		self.assertIsNone(clip.ill_schedule_line_id)
		self.assertEqual(frappe.msgprint.call_args.kwargs["indicator"], "orange")


class ScheduleToTransactions(unittest.TestCase):
	def test_portal_edits_reach_every_other_draft_without_touching_price(self):
		with service() as (sync, frappe):
			lines = [schedule_line("L1", qty=4), schedule_line("L3")]
			sched = schedule(lines)
			sched.get_doc_before_save = lambda: Doc({"lines": [schedule_line("L1", qty=2), schedule_line("L2")]})
			sched.flags["ill_schedule_sync_source"] = ("Quotation", "QTN-SOURCE")
			sched._schedule_line_group_fields = lambda line: (line.location, line.notes or None)

			def append_quote_lines(target, **kwargs):
				self.assertEqual(kwargs["only_lines"], {"L3"})
				target["items"].append(quote_row("N3", "L3"))
				return {"rows_added": 1}

			sched.append_quote_lines = MagicMock(side_effect=append_quote_lines)
			draft = quotation([quote_row("R1", "L1", qty=2, rate=99), quote_row("R2", "L2"), quote_row("FREIGHT")], [])
			frappe.get_all.side_effect = lambda doctype, **kwargs: ["QTN-SOURCE", "QTN-1"] if doctype == "Quotation" else []
			frappe.get_doc.return_value = draft
			with patch.object(sync, "schedule_is_open", return_value=True):
				sync.on_schedule_update(sched)

		frappe.get_doc.assert_called_once_with("Quotation", "QTN-1")
		self.assertEqual([(row.name, row.qty) for row in draft["items"]], [("R1", 4.0), ("N3", 1), ("FREIGHT", 1)])
		self.assertEqual(draft["items"][0].rate, 99)
		self.assertTrue(draft.flags["ill_skip_schedule_sync"])
		draft.save.assert_called_once()

	def test_sync_writes_do_not_echo(self):
		with service() as (sync, frappe):
			sched = schedule([schedule_line("L1")])
			sched.flags["ill_skip_schedule_sync"] = True
			sync.on_schedule_update(sched)
			doc = quotation([quote_row("R2", item_code="CLIP")], [])
			doc.flags["ill_skip_schedule_sync"] = True
			sync.on_transaction_validate(doc)
		frappe.get_all.assert_not_called()
		frappe.db.exists.assert_not_called()

	def test_a_locked_or_quoted_schedule_pushes_nothing(self):
		with service() as (sync, frappe):
			sched = schedule([schedule_line("L1")])
			with patch.object(sync, "schedule_is_open", return_value=False):
				sync.on_schedule_update(sched)
		frappe.get_all.assert_not_called()


if __name__ == "__main__":
	unittest.main()
