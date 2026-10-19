# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Spec submittal readiness: which templates cannot produce a spec submittal yet, and why.

The report lists every active template with its spec submittal template, spec sheet and field
mappings. A per-template dry run sends a sample build through the real generator in
``api.spec_submittal`` with ``frappe.flags.ill_submittal_dry_run`` set, so the PDF is filled in
memory, nothing is saved, and the values each mapping produced are reported against the PDF's
form fields. ``evaluate`` is pure so the unit tests and the page agree on what counts as a failure.

On a site, ``bench --site <site> execute
illumenate_lighting.illumenate_lighting.api.submittal_readiness.audit`` dry-runs every template and
prints the mappings that fail.
"""

from collections import Counter

import frappe
from frappe import _

STATUS_READY = "ready"
STATUS_INCOMPLETE = "incomplete"
SCHEDULE = "ilL-Project-Fixture-Schedule"
LINE = "ilL-Child-Fixture-Schedule-Line"

# build: the configured record the generator takes, and its link to the template.
# line_field: the schedule line field that names the template.
KINDS = {
	"Fixture": {
		"doctype": "ilL-Fixture-Template",
		"mapping": "ilL-Spec-Submittal-Mapping",
		"link": "fixture_template",
		"line_field": "fixture_template",
		"build": ("ilL-Configured-Fixture", "fixture_template", "configured_fixture"),
	},
	"Tape/Neon": {
		"doctype": "ilL-Tape-Neon-Template",
		"mapping": "ilL-Neon-Submittal-Mapping",
		"link": "tape_neon_template",
		"line_field": "tape_neon_template",
		"build": ("ilL-Configured-Tape-Neon", "tape_neon_template", "configured_tape_neon"),
	},
	"LED Sheet": {
		"doctype": "ilL-LED-Sheet-Template",
		"mapping": "ilL-LED-Sheet-Submittal-Mapping",
		"link": "led_sheet_template",
		"line_field": "led_sheet_template",
		"build": ("ilL-Configured-LED-Sheet", "sheet_template", "configured_led_sheet"),
	},
	"Driver": {
		"doctype": "ilL-Driver-Template",
		"mapping": "ilL-Driver-Submittal-Mapping",
		"link": "driver_template",
		"line_field": "driver_template",
	},
	"Controller": {
		"doctype": "ilL-Controller-Template",
		"mapping": "ilL-Controller-Submittal-Mapping",
		"link": "controller_template",
		"line_field": None,
	},
	"Extrusion Kit": {
		"doctype": "ilL-Extrusion-Kit-Template",
		"mapping": "ilL-Kit-Submittal-Mapping",
		"link": "kit_template",
		"line_field": "kit_template",
	},
}


def _blank(value):
	return value is None or str(value).strip() == ""


# --- Rules (pure) ------------------------------------------------------------------------------


def template_issues(template, mapping_count, existing_files):
	"""Attachments and mappings a template needs before it can produce a spec submittal.

	``existing_files`` is the set of attached file URLs that have a File record.
	"""
	missing, notes = [], []
	for field in ("spec_submittal_template", "spec_sheet"):
		url = template.get(field)
		if not url:
			missing.append(field)
		elif url not in existing_files:
			missing.append(field)
			notes.append(_("{0} is attached but its file is missing: {1}").format(field, url))
	if not mapping_count:
		missing.append("field_mappings")
	if "spec_submittal_template" in missing and template.get("spec_sheet") in existing_files:
		notes.append(_("Submittals fill the spec sheet until a spec submittal template is attached"))
	return {
		"status": STATUS_INCOMPLETE if missing else STATUS_READY,
		"missing": missing,
		"notes": notes,
	}


def evaluate(mappings, captured, has_field=None, blocked=None):
	"""Grade each mapping against what one dry run wrote.

	``captured`` is what ``_fill_pdf_form_fields`` recorded (``pdf_fields``, ``field_values``); it is
	empty when generation stopped before the PDF was read. ``has_field(doctype, field)`` checks the
	source against the installed schema; ``blocked(doctype, field)`` names commercial sources that
	are always blank in packets.
	"""
	pdf_fields = captured.get("pdf_fields")
	values = captured.get("field_values")
	names = Counter(row.get("pdf_field_name") for row in mappings)
	rows = []
	for row in mappings:
		field = row.get("pdf_field_name")
		source_doctype, source_field = row.get("source_doctype"), row.get("source_field")
		problems, notes = [], []
		if not field:
			problems.append(_("Enter the PDF field name"))
		elif pdf_fields is not None and field not in pdf_fields:
			problems.append(_("The PDF has no field named {0}").format(field))
		if field and names[field] > 1:
			notes.append(_("Mapped {0} times; the last mapping is used").format(names[field]))
		if not source_doctype or not source_field:
			problems.append(_("Choose the source record and field"))
		elif (
			has_field
			and not str(source_field).startswith("__")
			and not has_field(source_doctype, source_field)
		):
			problems.append(_("{0} has no field {1}").format(source_doctype, source_field))
		if row.get("webflow_field"):
			notes.append(_("Uses the {0} parameter when one is supplied").format(row["webflow_field"]))
		value = values.get(field) if values is not None and field else None
		is_blocked = bool(blocked and source_doctype and blocked(source_doctype, source_field))
		if is_blocked:
			notes.append(_("Commercial value; left blank in packets and downloads"))
		empty = values is not None and _blank(value) and not is_blocked
		if empty and not problems:
			if row.get("required_value"):
				problems.append(_("Required value is blank for this sample"))
			else:
				notes.append(_("Blank for this sample"))
		rows.append(
			{
				"pdf_field_name": field,
				"source": f"{source_doctype or '?'}.{source_field or '?'}",
				"value": None if values is None else value,
				"status": "fail" if problems else "blank" if empty else "ok",
				"problems": problems,
				"notes": notes,
			}
		)
	mapped = {row.get("pdf_field_name") for row in mappings}
	unmapped = sorted(set(pdf_fields or ()) - mapped)
	return {
		"mappings": rows,
		"unmapped_pdf_fields": unmapped,
		"failures": sum(row["status"] == "fail" for row in rows),
		"blanks": sum(row["status"] == "blank" for row in rows),
	}


# --- Report -------------------------------------------------------------------------------------


def _usage(line_field):
	"""Schedule lines naming each template (configured or not), for prioritising fixes."""
	if not line_field:
		return Counter()
	return Counter(
		frappe.get_all(
			LINE,
			filters={"parenttype": SCHEDULE, line_field: ["is", "set"]},
			pluck=line_field,
			limit_page_length=0,
		)
	)


def kind_rows(kind):
	cfg = KINDS[kind]
	templates = frappe.get_all(
		cfg["doctype"],
		filters={"is_active": 1},
		fields=["name", "template_name", "spec_submittal_template", "spec_sheet"],
		order_by="name asc",
		limit_page_length=0,
	)
	counts = Counter(frappe.get_all(cfg["mapping"], pluck=cfg["link"], limit_page_length=0))
	urls = {t.get(f) for t in templates for f in ("spec_submittal_template", "spec_sheet") if t.get(f)}
	existing = (
		set(frappe.get_all("File", filters={"file_url": ["in", list(urls)]}, pluck="file_url"))
		if urls
		else set()
	)
	usage = _usage(cfg["line_field"])
	return [
		{
			"kind": kind,
			"doctype": cfg["doctype"],
			"name": template["name"],
			"label": template.get("template_name") or template["name"],
			"spec_submittal_template": template.get("spec_submittal_template"),
			"spec_sheet": template.get("spec_sheet"),
			"mapping_count": counts.get(template["name"], 0),
			"lines": usage.get(template["name"], 0),
			**template_issues(template, counts.get(template["name"], 0), existing),
		}
		for template in templates
	]


def build_report(kinds=None):
	rows = [row for kind in (kinds or KINDS) if kind in KINDS for row in kind_rows(kind)]
	return sorted(
		rows, key=lambda row: (row["status"] != STATUS_INCOMPLETE, -row["lines"], row["kind"], row["name"])
	)


def summarize(rows):
	by_kind = {}
	for row in rows:
		bucket = by_kind.setdefault(row["kind"], {"total": 0, "incomplete": 0})
		bucket["total"] += 1
		bucket["incomplete"] += row["status"] == STATUS_INCOMPLETE
	return {
		"total": len(rows),
		"incomplete": sum(row["status"] == STATUS_INCOMPLETE for row in rows),
		"no_submittal_template": sum("spec_submittal_template" in row["missing"] for row in rows),
		"no_spec_sheet": sum("spec_sheet" in row["missing"] for row in rows),
		"by_kind": by_kind,
	}


def require_reader():
	from illumenate_lighting.illumenate_lighting.portal.staff import allowed

	if not any(allowed(c) for c in ("catalog", "engineering", "design_review")):
		frappe.throw(_("Catalog, engineering or design review access is required"), frappe.PermissionError)


@frappe.whitelist(methods=["GET"])
def get_report(kind=None, only_incomplete=0):
	"""Desk "Spec Submittal Readiness" page."""
	require_reader()
	rows = build_report([kind] if kind in KINDS else None)
	summary = summarize(rows)
	if str(only_incomplete) in ("1", "true"):
		rows = [row for row in rows if row["status"] == STATUS_INCOMPLETE]
	return {"rows": rows, "summary": summary}


# --- Dry run ------------------------------------------------------------------------------------


def _schedule_context(line_name):
	"""(schedule, project, line) for a schedule line, read without the portal access check."""
	if not line_name:
		return None, None, None
	parent = frappe.db.get_value(LINE, line_name, "parent")
	schedule = frappe.get_doc(SCHEDULE, parent)
	line = next((row for row in schedule.get("lines") or [] if row.name == line_name), None)
	project = frappe.get_doc("ilL-Project", schedule.ill_project) if schedule.get("ill_project") else None
	return schedule, project, line


def _newest_line(filters):
	return frappe.get_all(
		LINE,
		filters={"parenttype": SCHEDULE, **filters},
		pluck="name",
		order_by="modified desc",
		limit_page_length=20,
	)


def find_sample(kind, template):
	"""The newest real build of ``template`` to dry-run: ``(sample, line, description)``."""
	from illumenate_lighting.illumenate_lighting.api.spec_submittal import kit_configuration
	from illumenate_lighting.illumenate_lighting.portal.driver_configuration import driver_configuration

	cfg = KINDS[kind]
	if "build" in cfg:
		doctype, template_field, line_field = cfg["build"]
		build = frappe.get_all(
			doctype,
			filters={template_field: template},
			pluck="name",
			order_by="modified desc",
			limit_page_length=1,
		)
		if not build:
			return None, None, None
		lines = _newest_line({line_field: build[0]})
		line = lines[0] if lines else None
		return build[0], line, _("{0} {1}").format(doctype, build[0])
	if kind == "Controller":
		return None, None, _("the template's default variant")
	check = driver_configuration if kind == "Driver" else kit_configuration
	for name in _newest_line({cfg["line_field"]: template}):
		_schedule, _project, line = _schedule_context(name)
		if line and check(line):
			return name, name, _("schedule line {0}").format(line.get("line_id") or name)
	if kind == "Driver":
		return None, None, _("the template's default variant")
	return None, None, None


def _generate(kind, template, sample, line, warnings):
	from illumenate_lighting.illumenate_lighting.api import spec_submittal as pdf

	context = _schedule_context(line)
	if kind == "Fixture":
		return pdf.generate_filled_submittal(sample, warnings=warnings, _schedule_context=context)
	if kind == "Tape/Neon":
		return pdf.generate_filled_neon_submittal(sample, warnings=warnings, _schedule_context=context)
	if kind == "LED Sheet":
		return pdf.generate_filled_sheet_submittal(sample, warnings=warnings, _schedule_context=context)
	if kind == "Extrusion Kit":
		return pdf.generate_filled_kit_submittal(template, warnings=warnings, _schedule_context=context)
	if kind == "Driver" and line:
		return pdf.generate_filled_driver_line_submittal(
			template, warnings=warnings, _schedule_context=context
		)
	if kind == "Driver":
		return pdf.generate_filled_driver_submittal(template, sample, warnings=warnings)
	return pdf.generate_filled_controller_submittal(template, sample, warnings=warnings)


def has_source_field(doctype, field):
	from frappe.model import default_fields

	if field in default_fields:
		return True
	try:
		return frappe.get_meta(doctype).has_field(field)
	except Exception:
		return False


def run_dry_run(kind, template, sample=None):
	"""Fill ``template``'s spec submittal for a sample build in memory and grade every mapping.

	``sample`` is a configured record (Fixture, Tape/Neon, LED Sheet), a schedule line (Driver,
	Extrusion Kit) or a variant row (Controller); the newest build is used when it is omitted.
	"""
	from illumenate_lighting.illumenate_lighting.api import spec_submittal as pdf

	cfg = KINDS[kind]
	mappings = frappe.get_all(
		cfg["mapping"],
		filters={cfg["link"]: template},
		fields=[
			"name",
			"pdf_field_name",
			"source_doctype",
			"source_field",
			"required_value",
			"webflow_field",
		],
		order_by="pdf_field_name asc",
		limit_page_length=0,
	)
	line = None
	if sample:
		description = sample
		if kind in ("Driver", "Extrusion Kit"):
			line = sample
		elif "build" in cfg:
			lines = _newest_line({cfg["build"][2]: sample})
			line = lines[0] if lines else None
	else:
		sample, line, description = find_sample(kind, template)
	result = {"kind": kind, "template": template, "sample": description, "line": line}
	captured, warnings = {}, []
	previous = frappe.flags.get("ill_submittal_dry_run")
	# The flag keeps every write out (see spec_submittal._links_generated_file and
	# exports._save_file_ignore_permissions) and blocks commercial sources as packets do.
	frappe.flags.ill_submittal_dry_run = captured
	try:
		if not description:
			generated = {
				"success": False,
				"message": _("No configured build of this template to test with; configure one first"),
			}
		else:
			try:
				generated = _generate(kind, template, sample, line, warnings)
			except Exception as error:
				generated = {"success": False, "message": f"{type(error).__name__}: {error}"}
		graded = evaluate(mappings, captured, has_source_field, pdf._commercial_source_blocked)
	finally:
		frappe.flags.ill_submittal_dry_run = previous
	return {
		**result,
		"success": bool(generated.get("success")),
		"message": generated.get("message"),
		"pdf_template": captured.get("pdf_template"),
		"warnings": [w for w in dict.fromkeys(warnings) if not str(w).startswith("[DEBUG]")],
		**graded,
	}


@frappe.whitelist(methods=["POST"])
def dry_run(kind, template, sample=None):
	"""Desk page "Test" button: nothing is saved."""
	require_reader()
	if kind not in KINDS:
		frappe.throw(_("Choose a template type"))
	if not frappe.db.exists(KINDS[kind]["doctype"], template):
		frappe.throw(_("{0} {1} was not found").format(KINDS[kind]["doctype"], template))
	return run_dry_run(kind, template, sample or None)


def audit(kind=None, verbose=0):
	"""Dry-run every active template that has mappings and print what fails (``bench execute``)."""
	failed = 0
	results = []
	for row in build_report([kind] if kind else None):
		if not row["mapping_count"] or not (row["spec_submittal_template"] or row["spec_sheet"]):
			continue
		result = run_dry_run(row["kind"], row["name"])
		results.append(result)
		bad = not result["success"] or result["failures"]
		failed += bool(bad)
		if not bad and not int(verbose):
			continue
		print(f"\n{row['kind']} {row['name']} ({result['sample'] or 'no sample'}): {result['message']}")
		for mapping in result["mappings"]:
			if mapping["status"] == "fail" or int(verbose):
				print(
					f"  [{mapping['status']}] {mapping['pdf_field_name']} <- {mapping['source']}: "
					+ "; ".join(mapping["problems"] + mapping["notes"])
				)
		if result["unmapped_pdf_fields"]:
			print(f"  PDF fields with no mapping: {', '.join(result['unmapped_pdf_fields'])}")
	print(f"\n{failed} of {len(results)} templates have failing spec submittal mappings")
	return {"tested": len(results), "failed": failed}
