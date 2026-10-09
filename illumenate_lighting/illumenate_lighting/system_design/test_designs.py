# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Installed-site checks for saved designs and revisions (WP-2.4)."""

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from illumenate_lighting.illumenate_lighting.system_design import (
	access,
	api,
	catalog,
	deliverables,
	gate,
	writeback,
)

FIXTURE = (
	Path(__file__).resolve().parents[3]
	/ "tools/system_designer/packages/core-schemas/fixtures/designs/valid/runs-and-site.json"
)


def website_user(email):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "ZZ",
				"user_type": "Website User",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
	return email


def _tree_leaf(doctype, field, root, leaf):
	"""A non-group record in an ERPNext tree, creating the root on a site without setup data."""
	existing = frappe.db.get_value(doctype, {"is_group": 0}, "name")
	if existing:
		return existing
	if not frappe.db.exists(doctype, root):
		frappe.get_doc({"doctype": doctype, field: root, "is_group": 1}).insert(ignore_permissions=True)
	if not frappe.db.exists(doctype, leaf):
		parent_field = "parent_" + frappe.scrub(doctype)
		frappe.get_doc({"doctype": doctype, field: leaf, "is_group": 0, parent_field: root}).insert(
			ignore_permissions=True
		)
	return leaf


def stock_uom():
	"""A UOM for test Items; the CI site has no setup data."""
	if not frappe.db.exists("UOM", "Nos"):
		frappe.get_doc({"doctype": "UOM", "uom_name": "Nos"}).insert(ignore_permissions=True)
	return "Nos"


def last_error():
	"""The newest Error Log, so an INTERNAL endpoint answer shows its cause in the test output."""
	rows = frappe.get_all("Error Log", fields=["method", "error"], order_by="creation desc", limit=1)
	return rows[0] if rows else None


def designer_customer():
	"""The customer every ilL-Project needs, created once for these tests."""
	name = "ZZ Designer Customer"
	if not frappe.db.exists("Customer", name):
		frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_group": _tree_leaf(
					"Customer Group", "customer_group_name", "All Customer Groups", "ZZ Designer Group"
				),
				"territory": _tree_leaf(
					"Territory", "territory_name", "All Territories", "ZZ Designer Territory"
				),
			}
		).insert(ignore_permissions=True)
	return name


def applications_engineer():
	"""A reviewer (D3) and the System Design Review request type, which test sites skip patches for."""
	from illumenate_lighting.patches import add_system_design_review_request_type

	add_system_design_review_request_type.execute()
	engineer = "zz-apps-engineer@example.com"
	if not frappe.db.exists("User", engineer):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": engineer,
				"first_name": "ZZ Engineer",
				"user_type": "System User",
				"send_welcome_email": 0,
				"roles": [{"role": "ilL Applications Engineer"}],
			}
		).insert(ignore_permissions=True)
	return engineer


def blank_pdf():
	import io

	from pypdf import PdfWriter

	writer = PdfWriter()
	writer.add_blank_page(width=792, height=612)
	buffer = io.BytesIO()
	writer.write(buffer)
	return buffer.getvalue()


class TestDesigns(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		project = frappe.get_doc(
			{
				"doctype": "ilL-Project",
				"project_name": "ZZ Designer Save Test",
				"customer": designer_customer(),
			}
		)
		project.insert(ignore_permissions=True)
		self.schedule = frappe.get_doc(
			{
				"doctype": "ilL-Project-Fixture-Schedule",
				"schedule_name": "ZZ Designer Save Schedule",
				"ill_project": project.name,
				"lines": [
					{
						"line_id": "TP1",
						"qty": 1,
						"location": "Hall",
						"manufacturer_type": "OTHER",
						"watts_each": 12,
						"input_voltage_v": 120,
						"voltage_class": "Line Voltage",
					}
				],
			}
		).insert(ignore_permissions=True)
		self.design = json.loads(FIXTURE.read_text(encoding="utf-8"))
		self.design["schedule"] = {"name": self.schedule.name, "version": self.schedule.get("version") or 0}
		self.design["catalogSnapshotHash"] = catalog.current_snapshot_hash()

	def save(self, **kwargs):
		kwargs.setdefault("terms_accepted", 1)
		return api.save_design(schedule=self.schedule.name, design_json=json.dumps(self.design), **kwargs)

	def test_save_update_conflict_and_revision(self):
		first = self.save()
		self.assertTrue(first["success"], first)
		data = first["data"]
		self.assertEqual(data["revision"], "A")
		self.assertEqual(len(data["build_hash"]), 64)
		record = frappe.get_doc("ilL-System-Design", data["name"])
		self.assertEqual(
			(record.status, record.is_current, record.ill_project), ("Draft", 1, self.schedule.ill_project)
		)
		self.assertEqual(record.terms_accepted_by, "Administrator")

		self.assertEqual(self.save()["code"], "CONFLICT")
		updated = self.save(design_name=data["name"], expected_modified=data["modified"])
		self.assertTrue(updated["success"], updated)
		stale = self.save(design_name=data["name"], expected_modified=data["modified"])
		self.assertEqual(stale["code"], "CONFLICT")

		opened = api.open_design(schedule=self.schedule.name)["data"]
		self.assertEqual(opened["design_meta"]["name"], data["name"])
		self.assertEqual(opened["design"]["schedule"]["name"], self.schedule.name)
		found = api.find_schedules(query="ZZ Designer Save")["data"]
		self.assertTrue(next(row for row in found if row["name"] == self.schedule.name)["has_design"])

		revision = api.create_revision(design=data["name"], note="Second pass")
		self.assertTrue(revision["success"], revision)
		self.assertEqual(revision["data"]["revision"], "B")
		self.assertEqual(frappe.db.get_value("ilL-System-Design", data["name"], "is_current"), 0)
		self.assertEqual(api.create_revision(design=data["name"])["code"], "CONFLICT")
		meta = api.open_design(schedule=self.schedule.name)["data"]["design_meta"]
		self.assertEqual((meta["revision"], meta["terms_accepted"]), ("B", False))
		unaccepted = self.save(
			design_name=revision["data"]["name"],
			expected_modified=meta["modified"],
			terms_accepted=0,
		)
		self.assertEqual(unaccepted["code"], "INVALID")
		self.assertEqual(api.open_design(schedule="NOPE-404", design=data["name"])["code"], "NOT_FOUND")

	def test_review_status_and_locked_schedule(self):
		data = self.save()["data"]
		frappe.db.set_value("ilL-System-Design", data["name"], "status", "In Review")
		modified = str(frappe.db.get_value("ilL-System-Design", data["name"], "modified"))
		self.assertEqual(self.save(design_name=data["name"], expected_modified=modified)["code"], "LOCKED")
		self.schedule.db_set("is_locked", 1)
		self.assertEqual(self.save()["code"], "LOCKED")

	def test_size_limit(self):
		self.design["views"] = {"riser": "x" * (5 * 1024 * 1024)}
		self.assertEqual(self.save()["code"], "INVALID")

	def test_permission_follows_the_schedule(self):
		data = self.save()["data"]
		record = frappe.get_doc("ilL-System-Design", data["name"])
		owner = website_user("zz-designer-owner@example.com")
		stranger = website_user("zz-designer-stranger@example.com")
		self.schedule.db_set("owner", owner)
		self.assertTrue(access.design_permission(record, "read", owner))
		self.assertFalse(access.design_permission(record, "read", stranger))
		self.assertFalse(access.design_permission(record, "read", "Guest"))
		self.assertTrue(access.design_permission(record, "write", "Administrator"))
		visible = frappe.db.sql(
			f"select name from `tabilL-System-Design` where {access.design_query_conditions(stranger)}",
			pluck="name",
		)
		self.assertNotIn(record.name, visible)
		frappe.set_user(stranger)
		try:
			self.assertEqual(
				api.open_design(schedule=self.schedule.name, design=record.name)["code"], "NOT_FOUND"
			)
		finally:
			frappe.set_user("Administrator")

	def test_reconcile_after_a_schedule_change(self):
		data = self.save()["data"]
		self.assertTrue(api.open_design(schedule=self.schedule.name)["data"]["reconcile"]["in_sync"])
		self.schedule.reload()
		self.schedule.append(
			"lines",
			{
				"line_id": "TP2",
				"qty": 1,
				"location": "Hall",
				"manufacturer_type": "OTHER",
				"watts_each": 8,
				"input_voltage_v": 120,
				"voltage_class": "Line Voltage",
			},
		)
		self.schedule.save(ignore_permissions=True)
		diff = api.reconcile_design(design=data["name"])["data"]
		self.assertEqual([item["lineId"] for item in diff["added"]], ["TP2"])
		self.assertEqual(api.open_design(schedule=self.schedule.name)["data"]["reconcile"], diff)
		blocked = self.save(design_name=data["name"], expected_modified=data["modified"])
		self.assertEqual(blocked["code"], "CONFLICT")
		saved = self.save(design_name=data["name"], expected_modified=data["modified"], reconciled=1)
		self.assertTrue(saved["success"], saved)
		self.assertTrue(api.reconcile_design(design=data["name"])["data"]["in_sync"])

	def test_verify_design_on_the_server(self):
		data = self.save()["data"]
		alone = api.verify_design(design=data["name"])
		self.assertTrue(alone["success"], alone)
		self.assertEqual((alone["data"]["ok"], alone["data"]["mismatches"]), (True, []))
		summary = alone["data"]["summary"]
		self.assertEqual(set(summary), {"loading", "runs", "messages", "review"})
		agreed = api.verify_design(design=data["name"], client=json.dumps(summary))["data"]
		self.assertTrue(agreed["ok"])
		disputed = api.verify_design(
			design=data["name"], client=json.dumps({**summary, "messages": ["PSU_OVERLOAD|PS-9"]})
		)["data"]
		self.assertFalse(disputed["ok"])
		self.assertIn(
			{"code": "PSU_OVERLOAD", "entityRef": "PS-9", "client": True, "server": False},
			disputed["mismatches"],
		)
		stored = json.loads(frappe.db.get_value("ilL-System-Design", data["name"], "verification_json"))
		self.assertEqual((stored["ok"], stored["compared"]), (False, True))
		self.assertEqual(api.verify_design(design="nope")["code"], "NOT_FOUND")
		self.assertEqual(api.verify_design(design=data["name"], client="[1")["code"], "INVALID")

	def test_upload_a_riser_deliverable(self):
		data = self.save()["data"]
		svg = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 17 11"><line x1="0" y1="0" x2="1" y2="1"/></svg>'
		digest = hashlib.sha256(svg).hexdigest()
		before = frappe.db.get_value("ilL-System-Design", data["name"], "modified")
		stored = deliverables.upload_deliverable(
			data["name"], "Riser SVG", "E-1", digest, data["build_hash"], content=svg, filename="riser.svg"
		)
		row = stored["row"]
		self.assertEqual((row["kind"], row["variant"], row["revision"]), ("Riser SVG", "E-1", "A"))
		self.assertEqual((row["file_sha256"], row["build_hash"]), (digest, data["build_hash"]))
		self.assertTrue(stored["file_url"].startswith("/private/files/ilLumenate-System-Designer_"))
		self.assertEqual(frappe.db.get_value("ilL-System-Design", data["name"], "modified"), before)
		again = deliverables.upload_deliverable(
			data["name"], "Riser SVG", "E-1", digest, content=svg, filename="riser.svg"
		)
		self.assertEqual(again["row"]["name"], row["name"])
		opened = api.open_design(schedule=self.schedule.name)["data"]
		self.assertEqual([item["name"] for item in opened["deliverables"]], [row["name"]])
		self.assertEqual(opened["title_block"]["customer"], designer_customer())
		self.assertEqual(opened["title_block"]["project_name"], "ZZ Designer Save Test")

		def code(**changes):
			args = {"kind": "Riser SVG", "sha256": digest, "content": svg, "filename": "riser.svg", **changes}
			try:
				deliverables.upload_deliverable(data["name"], **args)
			except Exception as e:
				return getattr(e, "code", type(e).__name__)

		self.assertEqual(code(sha256="0" * 64), "INVALID")
		self.assertEqual(code(build_hash="f" * 64), "CONFLICT")
		self.assertEqual(code(kind="Riser PDF", filename="riser.pdf"), "INVALID")
		script = b"<svg><script>alert(1)</script></svg>"
		self.assertEqual(code(content=script, sha256=hashlib.sha256(script).hexdigest()), "INVALID")

	def test_pilot_telemetry_rows(self):
		data = self.save()["data"]
		api.open_design(schedule=self.schedule.name)
		logged = api.log_event(
			schedule=self.schedule.name,
			event="feedback",
			design=data["name"],
			details=json.dumps({"rating": 4, "comment": "Clear"}),
		)
		self.assertTrue(logged["success"], logged)
		rows = frappe.get_all(
			"ilL-Portal-Event",
			filters={"reference_name": data["name"], "event_key": ["like", "system_design:%"]},
			fields=["event_key", "message"],
		)
		events = sorted(row.event_key.split(":")[1] for row in rows)
		self.assertEqual(events, ["feedback", "opened", "saved"])
		feedback = next(json.loads(row.message) for row in rows if ":feedback:" in row.event_key)
		self.assertEqual((feedback["rating"], feedback["comment"]), (4, "Clear"))
		self.assertEqual(api.log_event(schedule=self.schedule.name, event="opened")["code"], "INVALID")

	def test_copy_forward_to_the_next_version(self):
		data = self.save()["data"]
		next_name = self.schedule.create_new_version(version_notes="ZZ designer copy test")
		copied = api.copy_design_to_version(design=data["name"], target_schedule=next_name)
		self.assertTrue(copied["success"], copied)
		record = frappe.get_doc("ilL-System-Design", copied["data"]["name"])
		self.assertEqual((record.fixture_schedule, record.revision_parent), (next_name, data["name"]))
		self.assertEqual(json.loads(record.design_json)["schedule"]["name"], next_name)
		opened = api.open_design(schedule=next_name)["data"]
		self.assertEqual(opened["design_meta"]["name"], record.name)
		self.assertIsNone(opened["newer_version"])
		locked = api.open_design(schedule=self.schedule.name)["data"]
		self.assertTrue(locked["schedule"]["is_locked"])
		self.assertEqual(locked["newer_version"]["name"], next_name)
		self.assertTrue(opened["reconcile"]["in_sync"])
		self.assertEqual(
			api.copy_design_to_version(design=data["name"], target_schedule=next_name)["code"], "CONFLICT"
		)
		other = frappe.get_doc(
			{
				"doctype": "ilL-Project-Fixture-Schedule",
				"schedule_name": "ZZ Other",
				"ill_project": self.schedule.ill_project,
			}
		).insert(ignore_permissions=True)
		self.assertEqual(
			api.copy_design_to_version(design=data["name"], target_schedule=other.name)["code"], "INVALID"
		)

	def test_write_back_supplies_and_wire(self):
		data = self.save()["data"]
		for code in ("ZZ-WB-PSU", "ZZ-WB-WIRE"):
			if not frappe.db.exists("Item", code):
				frappe.get_doc(
					{
						"doctype": "Item",
						"item_code": code,
						"item_name": code,
						"item_group": _tree_leaf(
							"Item Group", "item_group_name", "All Item Groups", "ZZ Designer Items"
						),
						"stock_uom": stock_uom(),
					}
				).insert(ignore_permissions=True)
		stored = json.loads(frappe.db.get_value("ilL-System-Design", data["name"], "design_json"))
		stored["project"]["equipment"] = [
			{"id": "PS-1", "tag": "PS-1", "catalogId": "drv:ZZ-WB-PSU", "qty": 2, "enclosure": "cab-1"}
		]
		frappe.db.set_value("ilL-System-Design", data["name"], "design_json", json.dumps(stored))
		snapshot = {
			"items": [
				{
					"id": "drv:ZZ-WB-PSU",
					"erpItemCode": "ZZ-WB-PSU",
					"isExample": False,
					"specs": {"kind": "psu"},
				}
			],
			"wires": [
				{
					"id": "wire:ZZ-WB-WIRE",
					"erpItemCode": "ZZ-WB-WIRE",
					"isExample": False,
					"salesUom": "spool",
					"spoolLengthFt": 250,
				}
			],
		}
		feet = json.dumps({"wire:ZZ-WB-WIRE": 260})
		with patch.object(catalog, "get_snapshot", return_value=snapshot):
			preview = api.writeback_preview(design=data["name"], wire_feet=feet)
			self.assertTrue(preview["success"], preview)
			added = {row["key"]: row["qty"] for row in preview["data"]["add"]}
			self.assertEqual(added, {"Supply:ZZ-WB-PSU": 2, "Wire:ZZ-WB-WIRE": 2})
			self.assertIn("price_delta", preview["data"])
			stale = api.writeback_apply(design=data["name"], accepted_keys='["Supply:OTHER"]', wire_feet=feet)
			self.assertEqual(stale["code"], "CONFLICT")
			applied = api.writeback_apply(
				design=data["name"], accepted_keys=json.dumps(list(added)), wire_feet=feet
			)
			self.assertTrue(applied["success"], applied)
			self.assertEqual(applied["data"]["added"], 2)
			self.schedule.reload()
			rows = {
				line.design_line_key: (line.line_id, line.qty, line.location, line.system_design)
				for line in self.schedule.lines
				if line.design_line_role
			}
			self.assertEqual(
				rows,
				{
					"Supply:ZZ-WB-PSU": ("PS1", 2, "Pantry", data["name"]),
					"Wire:ZZ-WB-WIRE": ("WIRE1", 2, "Field wire", data["name"]),
				},
			)
			again = api.writeback_preview(design=data["name"], wire_feet=feet)["data"]
			self.assertEqual(writeback.change_keys(again), set())
			self.assertTrue(api.reconcile_design(design=data["name"])["data"]["in_sync"])
			fewer = api.writeback_preview(design=data["name"])["data"]
			self.assertEqual([row["key"] for row in fewer["remove"]], ["Wire:ZZ-WB-WIRE"])
			stored["project"]["equipment"][0]["qty"] = 3
			frappe.db.set_value("ilL-System-Design", data["name"], "design_json", json.dumps(stored))
			moved = api.writeback_preview(design=data["name"], wire_feet=feet)["data"]
			self.assertEqual(
				[(row["key"], row["from_qty"], row["qty"]) for row in moved["update"]],
				[("Supply:ZZ-WB-PSU", 2, 3)],
			)
			self.schedule.reload()
			self.schedule.lines = [
				line for line in self.schedule.lines if line.design_line_key != "Wire:ZZ-WB-WIRE"
			]
			self.schedule.save(ignore_permissions=True)
			with (
				patch.object(writeback, "_add_line", side_effect=RuntimeError("boom")),
				patch.object(frappe.db, "rollback") as rollback,
			):
				failed = api.writeback_apply(
					design=data["name"], accepted_keys='["Wire:ZZ-WB-WIRE"]', wire_feet=feet
				)
			self.assertEqual(failed["code"], "INTERNAL")
			rollback.assert_called_once()

	def test_request_review(self):
		engineer = applications_engineer()
		frappe.db.set_single_value("ilL-System-Designer-Settings", "reviewer_assignment", "Round Robin")
		data = self.save()["data"]
		self.assertEqual(api.request_review(design=data["name"], error_count=2)["code"], "INVALID")
		requested = api.request_review(
			design=data["name"], priority="High", note="Pantry first", error_count=0
		)
		self.assertTrue(requested["success"], requested)
		request = frappe.get_doc("ilL-Document-Request", requested["data"]["request"])
		self.assertEqual(
			(request.request_type, request.status, request.reference_name, request.fixture_schedule),
			("System Design Review", "Submitted", data["name"], self.schedule.name),
		)
		self.assertIn("ilL Applications Engineer", frappe.get_roles(request.technical_reviewer))
		self.assertEqual(request.assigned_to, request.technical_reviewer)
		self.assertTrue(request.sla_deadline)
		record = frappe.get_doc("ilL-System-Design", data["name"])
		self.assertEqual((record.status, record.review_request), ("In Review", request.name))
		self.assertEqual(requested["data"]["design_meta"]["status"], "In Review")
		self.assertEqual(api.request_review(design=data["name"])["code"], "CONFLICT")
		frappe.set_user(engineer)
		self.assertTrue(api.open_design(schedule=self.schedule.name)["success"])
		self.assertTrue(frappe.has_permission("ilL-Document-Request", "read", doc=request))

	def test_review_comments_override_and_decision(self):
		engineer = applications_engineer()
		data = self.save()["data"]
		requested = api.request_review(design=data["name"], error_count=0)
		self.assertTrue(requested["success"], requested)
		request_name = requested["data"]["request"]
		frappe.db.set_value(
			"ilL-Document-Request", request_name, {"technical_reviewer": engineer, "assigned_to": engineer}
		)
		pdf = blank_pdf()

		def keep_riser():
			stored = deliverables.upload_deliverable(
				data["name"],
				"Riser PDF",
				"Tabloid",
				hashlib.sha256(pdf).hexdigest(),
				content=pdf,
				filename="r.pdf",
			)
			return stored["row"]

		keep_riser()
		self.assertEqual(api.review_decide(design=data["name"], decision="Approved")["code"], "FORBIDDEN")
		frappe.set_user(engineer)
		pin = json.dumps({"sheet": "E-1", "x": 0.5, "y": 0.25})
		comment = api.add_comment(design=data["name"], body="Check PS-1", view="Riser", anchor=pin)
		self.assertTrue(comment["success"], comment)
		listed = api.list_comments(design=data["name"])["data"]
		self.assertEqual([(row["body"], row["anchor"]["sheet"]) for row in listed], [("Check PS-1", "E-1")])
		resolved = api.resolve_comment(design=data["name"], comment_id=listed[0]["comment_id"])["data"]
		self.assertTrue(resolved["resolved"])
		self.assertEqual(
			api.review_decide(design=data["name"], decision="Changes Requested")["code"], "INVALID"
		)
		overridden = api.override_check(
			design=data["name"], code="PSU_OVERLOAD", entity_ref="PS-1", reason="Field verified"
		)
		self.assertTrue(overridden["success"], overridden)
		self.assertNotEqual(overridden["data"]["build_hash"], data["build_hash"])
		# The kept PDF was drawn before the override, so the reviewer keeps a new one.
		self.assertEqual(api.review_decide(design=data["name"], decision="Approved")["code"], "INVALID")
		keep_riser()
		decided = api.review_decide(design=data["name"], decision="Approved", note="Looks good")
		self.assertTrue(decided["success"], (decided, last_error()))
		record = frappe.get_doc("ilL-System-Design", data["name"])
		self.assertEqual((record.status, record.approved_by), ("Approved", engineer))
		review = frappe.get_doc("ilL-Drawing-Review", record.approved_review)
		self.assertEqual((review.decision, review.build_hash), ("APPROVED", record.build_hash))
		self.assertEqual(frappe.db.get_value("ilL-Document-Request", request_name, "status"), "Completed")
		self.assertEqual(decided["data"]["design_meta"]["status"], "Approved")
		self.assertEqual(api.review_decide(design=data["name"], decision="Approved")["code"], "CONFLICT")

	def test_review_gate_before_ordering(self):
		from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
			can_request_schedule_order,
		)

		settings = "ilL-System-Designer-Settings"
		frappe.db.set_single_value(settings, "review_gate_enabled", 1)
		frappe.db.set_single_value(settings, "review_gate_watts", 10)
		data = self.save()["data"]

		def order():
			self.schedule.reload()
			return can_request_schedule_order(self.schedule)

		# With the site flag off the gate never changes ordering.
		with patch.dict(frappe.conf, {gate.SITE_FLAG: 0}):
			self.assertEqual(order(), (True, ""))
		with patch.dict(frappe.conf, {gate.SITE_FLAG: 1}):
			allowed, reason = order()
			self.assertFalse(allowed)
			self.assertIn("12 W", reason)
			requirement = api.review_requirement(schedule=self.schedule.name)["data"]
			self.assertEqual((requirement["required"], requirement["satisfied"]), (True, False))
			frappe.db.set_value("ilL-System-Design", data["name"], "status", "Approved")
			self.assertEqual(order(), (True, ""))
			self.assertEqual(
				api.review_requirement(schedule=self.schedule.name)["data"]["approved_design"], data["name"]
			)
			# A schedule change after approval needs a new review or an override.
			self.schedule.lines[0].qty = 2
			self.schedule.save(ignore_permissions=True)
			self.assertFalse(order()[0])
			self.assertEqual(
				api.override_review_gate(schedule=self.schedule.name, reason="x")["code"], "INVALID"
			)
			first = api.override_review_gate(schedule=self.schedule.name, reason="Customer signed off")
			self.assertTrue(first["success"], first)
			again = api.override_review_gate(schedule=self.schedule.name, reason="Customer signed off")
			self.assertEqual(again["data"]["override_id"], first["data"]["override_id"])
			self.assertEqual(order(), (True, ""))
			self.assertEqual(
				api.review_requirement(schedule=self.schedule.name)["data"]["override"]["reason"],
				"Customer signed off",
			)
			frappe.set_user(website_user("zz-designer-dealer-gate@example.com"))
			self.assertEqual(
				api.override_review_gate(schedule=self.schedule.name, reason="Please")["code"], "FORBIDDEN"
			)

	def test_schedule_and_project_pages(self):
		from illumenate_lighting.illumenate_lighting.system_design import portal_pages

		card = portal_pages.schedule_card(self.schedule)
		self.assertEqual(
			(card["url"], card["design"]), (f"/portal/schedules/{self.schedule.name}/design", None)
		)
		data = self.save()["data"]
		card = portal_pages.schedule_card(self.schedule)
		self.assertEqual((card["design"]["name"], card["design"]["status"]), (data["name"], "Draft"))
		schedules = [
			frappe._dict(name=self.schedule.name, schedule_name="ZZ", version=self.schedule.version or 0)
		]
		self.assertEqual([row["name"] for row in portal_pages.project_designs(schedules)], [data["name"]])

	def test_reviewed_design_lets_the_schedule_be_ordered(self):
		"""WP-4.6 on the server: save, request review, approve, then the D4 gate allows ordering."""
		from illumenate_lighting.illumenate_lighting.doctype.ill_project_fixture_schedule.ill_project_fixture_schedule import (
			can_request_schedule_order,
		)

		settings = "ilL-System-Designer-Settings"
		frappe.db.set_single_value(settings, "review_gate_enabled", 1)
		frappe.db.set_single_value(settings, "review_gate_watts", 10)
		engineer = applications_engineer()
		data = self.save()["data"]
		with patch.dict(frappe.conf, {gate.SITE_FLAG: 1}):
			self.assertFalse(can_request_schedule_order(self.schedule)[0])
			requested = api.request_review(design=data["name"], error_count=0)["data"]
			frappe.db.set_value(
				"ilL-Document-Request",
				requested["request"],
				{"technical_reviewer": engineer, "assigned_to": engineer},
			)
			pdf = blank_pdf()
			deliverables.upload_deliverable(
				data["name"],
				"Riser PDF",
				"Tabloid",
				hashlib.sha256(pdf).hexdigest(),
				content=pdf,
				filename="r.pdf",
			)
			frappe.set_user(engineer)
			decided = api.review_decide(design=data["name"], decision="Approved")
			self.assertTrue(decided["success"], (decided, last_error()))
			frappe.set_user("Administrator")
			self.schedule.reload()
			self.assertEqual(can_request_schedule_order(self.schedule), (True, ""))
