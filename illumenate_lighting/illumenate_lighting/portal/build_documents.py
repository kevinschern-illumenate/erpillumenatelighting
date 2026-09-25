"""Filled member specifications and instructions from a pinned group build."""

import copy
import html
import json

import frappe


def member_document(group, member):
	"""Adapt sealed member values without creating or recalculating a family record."""
	build = member["build"]
	data = {
		**build,
		**build.get("inputs", {}),
		**build.get("selections", {}),
		**build.get("computed", {}),
		**build.get("resolved_items", {}),
		**member.get("pricing_inputs", {}),
	}
	family, template = group["request"]["family"], group["request"]["template"]
	data.update(name=member["member_key"], include_power_supply=False)
	if family == "Linear Fixture":
		data.update(doctype="ilL-Configured-Fixture", fixture_template=template)
	elif family == "LED Sheet":
		data.update(doctype="ilL-Configured-LED-Sheet", sheet_template=template, sheet_spec=build["spec"])
	else:
		data.update(doctype="ilL-Configured-Tape-Neon", tape_neon_template=template, product_category=family)
		data["manufacturable_length_mm"] = data.get(
			"total_manufacturable_length_mm", data.get("manufacturable_length_mm")
		)
	data["segments"] = (
		data.get("segments") or data.get("user_segments") or member["geometry"].get("segments", [])
	)
	data["is_multi_segment"] = len(data["segments"]) > 1

	def objectify(value):
		if isinstance(value, dict):
			return frappe._dict({key: objectify(val) for key, val in value.items()})
		if isinstance(value, list):
			return [objectify(val) for val in value]
		return value

	return objectify(data)


def generate_group(name, warnings=None, schedule_line=None):
	from frappe.utils.pdf import get_pdf

	from illumenate_lighting.illumenate_lighting.api import spec_submittal as pdf
	from illumenate_lighting.illumenate_lighting.api.exports import _save_file_ignore_permissions
	from illumenate_lighting.illumenate_lighting.api.fixture_group_bom import snapshot
	from illumenate_lighting.illumenate_lighting.api.manufacturing_order import traveler

	if not frappe.flags.get("ill_packet_job"):
		raise ValueError("Group specifications must be generated in an authorized private packet")
	warnings = warnings if warnings is not None else []
	schedule, project, line = pdf._explicit_schedule_context("configured_group", name, schedule_line)
	if not schedule:
		raise ValueError("Choose the owning schedule line for this group")
	build = snapshot(frappe.get_doc("ilL-Configured-Group", name))
	family = build["request"]["family"]
	renderer = (
		pdf.generate_filled_submittal
		if family == "Linear Fixture"
		else pdf.generate_filled_sheet_submittal
		if family == "LED Sheet"
		else pdf.generate_filled_neon_submittal
	)
	parts, provenance = [], []
	labels = {}
	if line.get("ill_configurator_request"):
		from illumenate_lighting.illumenate_lighting.api.group_contract import member_presentation, normalize

		raw = json.loads(line.ill_configurator_request)
		raw = (raw.get("selections") or {}).get("group_request") or raw
		if raw.get("members") and normalize(raw) == build["request"]:
			labels = {row["member_key"]: row["label"] for row in member_presentation(raw, build["request"])}
	for member in build["members"]:
		member_line = frappe._dict(copy.deepcopy(line.as_dict()))
		key = member["member_key"]
		member_line.line_id = f"{line.line_id} / {labels.get(key, key)} ({key})"
		result = renderer(
			member["member_key"],
			warnings=warnings,
			_configured_doc=member_document(build, member),
			_schedule_context=(schedule, project, member_line),
		)
		if not result.get("success"):
			return {
				"success": False,
				"message": f"{member_line.line_id}: {result.get('message', 'Filled specification failed')}",
			}
		content = pdf._get_pdf_bytes_from_url(result["file_url"])
		if not content:
			raise ValueError("Generated member specification is unavailable")
		parts.append(content)
		provenance.append({"member": member["member_key"], "source": result.get("provenance")})
	label = html.escape(f"{line.line_id} - {line.location or ''}")
	content = f"""<html><head><style>body{{font-family:Arial,sans-serif;font-size:11pt;line-height:1.55}} h1{{font-size:18pt}} .identity{{font-size:9pt;overflow-wrap:anywhere}}</style></head><body>
	<h1>{label}: group instructions</h1><p>Schedule quantity: {int(line.qty)} complete groups.</p>
	<p class="identity">Pinned build: {html.escape(name)}</p><p>{traveler(build)}</p></body></html>"""
	parts.append(get_pdf(content))
	merged = pdf._merge_pdfs(parts)
	if not merged:
		raise ValueError("Group specification assembly failed")
	file = _save_file_ignore_permissions(
		f"Group_{name}.pdf", merged, "ilL-Export-Job", frappe.flags.ill_packet_job
	)
	return {"success": True, "file_url": file.file_url, "warnings": warnings, "provenance": provenance}
