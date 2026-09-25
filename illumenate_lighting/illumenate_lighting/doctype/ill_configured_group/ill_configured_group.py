import json

import frappe
from frappe.model.document import Document


class ilLConfiguredGroup(Document):
	def validate(self):
		from illumenate_lighting.illumenate_lighting.api.fixture_group_bom import snapshot
		from illumenate_lighting.illumenate_lighting.api.group_contract import TEMPLATE_TYPES

		build = snapshot(self)
		if not self.flags.group_engine_write:
			frappe.throw("Save group builds through the configurator")
		request = build["request"]
		if (self.family, self.template_type, self.template) != (
			request["family"],
			TEMPLATE_TYPES[request["family"]],
			request["template"],
		):
			frappe.throw("Group template and family must match the engineering snapshot")
		members = [
			{"member_key": row.member_key, "snapshot": json.loads(row.snapshot_json)} for row in self.members
		]
		if members != [{"member_key": row["member_key"], "snapshot": row} for row in build["members"]]:
			frappe.throw("Group member instructions must match the pinned snapshot")
		allocations = [
			{
				"member_key": row.member_key,
				"run_key": row.run_key,
				"supply_number": row.supply_number,
				"output_number": row.output_number,
				"item_code": row.item_code,
				"watts": row.watts,
			}
			for row in self.allocations
		]
		expected = [
			{
				"member_key": a["run_key"].split(":")[0],
				"run_key": a["run_key"],
				"supply_number": a["supply"],
				"output_number": a["output"],
				"item_code": a["item_code"],
				"watts": a["watts"],
			}
			for a in build["power_plan"]["allocations"]
		]
		if allocations != expected:
			frappe.throw("Group output allocations must match the pinned snapshot")
		old = self.get_doc_before_save()
		if old:
			for field in self.meta.fields:
				if field.fieldname in {"configured_item", "bom"}:
					continue
				if frappe.as_json(self.get(field.fieldname)) != frappe.as_json(old.get(field.fieldname)):
					frappe.throw("Group engineering builds are immutable; save a new configuration")


def has_permission(doc, user=None, permission_type=None, ptype=None):
	from illumenate_lighting.illumenate_lighting.portal.access import READ_PTYPES, can_read_configured_record

	return (permission_type or ptype or "read") in READ_PTYPES and can_read_configured_record(
		doc.doctype, doc.name, user
	)


def get_permission_query_conditions(user=None):
	# Global builds contain no customer metadata. Dealer lists still require an authorized schedule/handoff.
	user = user or frappe.session.user
	if user == "Administrator" or "System Manager" in frappe.get_roles(user):
		return ""
	return "1=0"
