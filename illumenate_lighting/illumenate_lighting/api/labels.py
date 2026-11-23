"""Label queue: Dymo 1.5 x 2.5 and Rollo 4 x 6 labels from work orders, reels and shelves.

Labels plan, Phase 1 (revised Nov 23 for two printers) and the reel PDR's count kit.

* The server only queues. Frappe Cloud can't reach the USB printers, so Work Order hooks
  enqueue ``sync_work_order``, which writes one ilL-Label-Print-Job per physical label.
  The warehouse browser asks for a batch PDF per roll and prints it to that roll's printer.
* Every value a label prints is frozen in the job's ``context_json``, so a reprint matches
  the original. Layouts (templates/labels/<layout>.html) read only that context.
* A label problem never blocks saving a Work Order: every hook checks the flag, catches
  everything and logs with ``frappe.log_error``.
* Pure functions (no ``frappe`` calls) come first and are unit-tested without a site:
  ``work_order_kind``, ``plan_labels``, ``reconcile``, ``order_groups``, ``fit_pt`` and the
  formatters. Database code follows, then the hooks, then the endpoints, then rendering.
"""

import base64
import hashlib
import json
from datetime import date, datetime
from urllib.parse import quote, unquote

import frappe

SETTINGS = "ilL-Production-Settings"
STOCK = "ilL-Label-Stock"
TEMPLATE = "ilL-Label-Template"
JOB = "ilL-Label-Print-Job"
BATCH = "ilL-Label-Print-Batch"
API = "illumenate_lighting.illumenate_lighting.api.labels"

LABEL_ROLES = {
	"System Manager",
	"Manufacturing Manager",
	"Manufacturing User",
	"Stock Manager",
	"Stock User",
}
DEFAULT_LOGO = "/files/ilLumenate%20Logo_DW_Black_Main.png"
MM_PER_INCH = 25.4

KINDS = ("light_engine", "group_run", "assembled", "tape_neon", "led_sheet", "not_configured")
APPLIES_TO = {
	"All": set(KINDS),
	"Not light engine": set(KINDS) - {"light_engine", "group_run"},
	"Assembled": {"assembled"},
	"Light engine": {"light_engine", "group_run"},
	"Ship-in-pieces line": {"light_engine"},
	"Group bundle run": {"group_run"},
	"Tape/neon": {"tape_neon"},
	"LED sheet": {"led_sheet"},
	"Not configured": {"not_configured"},
}
BANDS = {
	"work_order": "WORK ORDER",
	"product": "SALES ORDER",
	"light_engine": "LIGHT ENGINE",
	"kit_piece": "KIT PIECE",
	"packet_4x6": "WORK ORDER PACKET",
	"reel": "REEL",
	"reel_tag": "REEL",
	"location": "SHELF",
}
# A Work Order save only re-plans its labels when one of these changed.
WATCHED_FIELDS = ("qty", "production_item", "sales_order", "sales_order_item", "expected_delivery_date")
LIVE = ("Queued", "Sent", "Printed")
CHECKLIST_ITEMIZE = 8  # more labels of one template than this are listed as one line
PULL_LINES = 10


# ---------------------------------------------------------------- pure helpers


def feet_inches(mm):
	"""Builder-friendly length, e.g. 20' 6"; whole feet drop the inches.

	Same output as ``fixture_group_bom.feet_inches``; kept here so this module doesn't
	import the build stack.
	"""
	inches = round(float(mm) / MM_PER_INCH, 1)
	feet, rest = divmod(inches, 12)
	rest = round(rest, 1)
	if rest >= 12:
		feet, rest = feet + 1, 0
	text = f"{int(feet)}'" if feet else ""
	if rest or not feet:
		text += (" " if text else "") + f'{rest:g}"'
	return text


def fmt_date(value):
	"""MM/DD/YY, or "" for nothing."""
	if not value:
		return ""
	if isinstance(value, (date, datetime)):
		return value.strftime("%m/%d/%y")
	text = str(value)[:10]
	try:
		return datetime.strptime(text, "%Y-%m-%d").strftime("%m/%d/%y")
	except ValueError:
		return text


def iso_date(value):
	return str(value)[:10] if value else None


def fmt_qty(value):
	number = float(value or 0)
	return f"{number:g}"


def fit_pt(text, box_chars, max_pt, min_pt):
	"""Font size (pt) that fits ``text`` in a box ``box_chars`` wide at ``max_pt``.

	wkhtmltopdf can't shrink text to fit, so the size is picked here. Never below ``min_pt``
	(the layout truncates with an ellipsis past that), rounded down to half points.
	"""
	length = len(str(text or ""))
	if length <= box_chars or length == 0:
		return float(max_pt)
	size = max_pt * box_chars / length
	return max(float(min_pt), int(size * 2) / 2)


def truncate(text, chars):
	text = str(text or "")
	return text if len(text) <= chars else text[: max(chars - 1, 1)].rstrip() + "…"


def context_hash(context):
	return hashlib.sha1(json.dumps(context, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def dedupe_key(template, doctype, name, piece_key=None, unit_no=1, piece_no=1, copy=1):
	key = f"{template}:{doctype}:{name}:{piece_key or '-'}:{unit_no}:{piece_no}"
	return key if copy == 1 else f"{key}:c{copy}"


def work_order_kind(wo, so_row, engine=None):
	"""Which kind of build a Work Order is; the first rule that matches wins.

	``engine`` is ``fixture_fulfillment.engine_for_item(wo.production_item)``, passed in so
	this stays pure.
	"""
	so_row = so_row or {}
	if engine:
		return "light_engine"
	if so_row.get("ill_configured_group"):
		return "group_run"
	if wo.get("ill_configured_fixture") or so_row.get("ill_configured_fixture"):
		return "assembled"
	if so_row.get("ill_configured_tape_neon"):
		return "tape_neon"
	if so_row.get("ill_configured_led_sheet"):
		return "led_sheet"
	return "not_configured"


def template_applies(template, kind):
	return kind in APPLIES_TO.get(template.get("applies_to") or "All", set())


def _checklist(wanted):
	"""Packet checklist lines from the other labels in the packet, in packet order."""
	by_template = {}
	for row in sorted(wanted, key=lambda r: (r["packet_order"], r["unit_no"], r["piece_no"])):
		by_template.setdefault(row["template"], []).append(row)
	lines = []
	for template, rows in by_template.items():
		if len(rows) == 1 and rows[0]["unit_count"] <= 1:
			lines.append(f"{template} label")
		elif len(rows) > CHECKLIST_ITEMIZE:
			lines.append(f"{template} labels x {len(rows)}")
		else:
			lines.extend(f"{template} label, unit {r['unit_no']} of {r['unit_count']}" for r in rows)
	return lines


def plan_labels(templates, info):
	"""Every label a source document should have: ``[{dedupe_key, template, ..., context}]``.

	``templates``: enabled template dicts for the source doctype. ``info``: ``doctype``,
	``name``, ``kind`` (work orders), ``qty``, ``sales_order`` and the shared ``context``.
	Per document = one label; per unit = one per whole unit of ``qty``. Per kit piece is
	Phase 2 and makes none yet. Stock builds with no sales order get no per-unit labels
	(the plan's default: WO label and packet only). Packet checklists list the rest.
	"""
	wanted, packets = [], []
	base = info.get("context") or {}
	for template in sorted(templates, key=lambda t: (t.get("packet_order") or 0, t["name"])):
		if info.get("kind") and not template_applies(template, info["kind"]):
			continue
		rule = template.get("quantity_rule") or "Per document"
		if rule == "Per kit piece":
			continue
		if rule == "Per unit":
			if not info.get("sales_order") and info.get("doctype") == "Work Order":
				continue
			count = max(int(float(info.get("qty") or 0)), 0)
		else:
			count = 1
		layout = template["layout"]
		for unit in range(1, count + 1):
			for copy in range(1, max(int(template.get("copies") or 1), 1) + 1):
				context = dict(base)
				context["doc_label"] = BANDS.get(layout, "")
				if layout == "product" and not info.get("sales_order"):
					context["doc_label"] = "PRODUCT"
				context["unit_no"], context["unit_count"] = unit, count
				context["unit_text"] = f"Unit {unit} of {count}" if rule == "Per unit" else ""
				row = {
					"dedupe_key": dedupe_key(
						template["name"], info["doctype"], info["name"], None, unit, 1, copy
					),
					"template": template["name"],
					"layout": layout,
					"label_stock": template["label_stock"],
					"packet_order": template.get("packet_order") or 0,
					"unit_no": unit,
					"unit_count": count,
					"piece_key": None,
					"piece_no": 1,
					"piece_count": 1,
					"context": context,
				}
				(packets if layout == "packet_4x6" else wanted).append(row)
	for row in packets:
		row["context"]["checklist"] = _checklist(wanted)
	return wanted + packets


def reconcile(existing, wanted, reason="no longer needed"):
	"""What to write so the jobs match ``wanted``: ``{insert, requeue, refresh, cancel, void, stale}``.

	``existing``: job rows (name, dedupe_key, status, context_hash, is_stale).
	- wanted, no job: insert. Wanted again after Cancelled or Void: requeue it.
	- Queued and still wanted: refresh its context if the hash changed.
	- Queued, no longer wanted: cancel. Sent or Printed, no longer wanted: void with ``reason``.
	- Sent or Printed whose context changed: mark stale (kept, offered as Reprint changed).
	Running it twice changes nothing the second time.
	"""
	plan = {"insert": [], "requeue": [], "refresh": [], "cancel": [], "void": [], "stale": []}
	by_key = {row["dedupe_key"]: row for row in existing}
	wanted_keys = set()
	for row in wanted:
		key = row["dedupe_key"]
		wanted_keys.add(key)
		new_hash = context_hash(row["context"])
		job = by_key.get(key)
		if not job:
			plan["insert"].append(row)
		elif job["status"] in ("Cancelled", "Void"):
			plan["requeue"].append((job["name"], row))
		elif job["status"] == "Queued":
			if job.get("context_hash") != new_hash:
				plan["refresh"].append((job["name"], row))
		elif job.get("context_hash") != new_hash and not job.get("is_stale"):
			plan["stale"].append((job["name"], row))
	for job in existing:
		if job["dedupe_key"] in wanted_keys:
			continue
		if job["status"] == "Queued":
			plan["cancel"].append(job["name"])
		elif job["status"] in ("Sent", "Printed"):
			plan["void"].append((job["name"], reason))
	return plan


def job_sort_key(job):
	"""Each work order's labels together and in packet order; reel tags in ID order."""
	return (
		job.get("ship_by") or "9999-12-31",
		job.get("sales_order") or "",
		job.get("work_order") or "",
		job.get("packet_order") or 0,
		job.get("reference_name") or "",
		job.get("piece_key") or "",
		job.get("unit_no") or 0,
		job.get("piece_no") or 0,
		job.get("name") or "",
	)


def order_groups(groups):
	"""Groups (one per roll, so one per printer) in ``print_order``; jobs sorted inside each."""
	for group in groups:
		group["jobs"] = sorted(group.get("jobs") or [], key=job_sort_key)
	return sorted(groups, key=lambda g: (g.get("print_order") or 0, g.get("stock") or ""))


def job_summary(job, context):
	"""One line for the queue: template, what it's for and the unit."""
	parts = [job.get("label_template") or ""]
	for key in ("fixture_type", "reel_id", "location_code"):
		if context.get(key):
			parts.append(str(context[key]))
	if context.get("unit_text"):
		parts.append(context["unit_text"].lower())
	return " · ".join(p for p in parts if p)


def build_context(kind, wo, so, so_row, fixture_part=None, project=""):
	"""Every value a work order label prints, formatted. Blank values stay blank."""
	so, so_row = so or {}, so_row or {}
	length_mm = so_row.get("ill_mfg_length_mm") or so_row.get("ill_requested_length_mm")
	part = so_row.get("item_code") or fixture_part or wo.get("production_item") or ""
	ship_by = wo.get("expected_delivery_date") or so.get("delivery_date")
	pull = [
		{
			"item": row.get("item_code"),
			"qty": f"{fmt_qty(row.get('required_qty'))} {row.get('stock_uom') or ''}".strip(),
		}
		for row in (wo.get("required_items") or [])[:PULL_LINES]
	]
	return {
		"kind": kind,
		"wo": wo.get("name") or "",
		"so": wo.get("sales_order") or "",
		"customer": so.get("customer_name") or "",
		"po": so.get("po_no") or "",
		"part_number": part,
		"item_name": wo.get("item_name") or so_row.get("item_name") or "",
		"length": feet_inches(length_mm) if length_mm else "",
		"fixture_type": so_row.get("ill_fixture_type") or "",
		"section": so_row.get("ill_section_label") or "",
		"ship_by": fmt_date(ship_by),
		"project": project or "",
		"build_qty": fmt_qty(wo.get("qty")),
		"pull": pull,
		"pull_more": max(len(wo.get("required_items") or []) - PULL_LINES, 0),
		"qr_payload": wo.get("url") or "",
		"subcomponent": "",
	}


# ---------------------------------------------------------------- settings and roles


def _setting(field):
	try:
		return frappe.db.get_single_value(SETTINGS, field)
	except Exception:
		return None


def labels_enabled():
	"""True only for a stored check value; a missing column (before migrate) is off."""
	return _setting("labels_enabled") in (1, "1", True)


def reels_enabled():
	return _setting("reels_enabled") in (1, "1", True)


def queue_enabled():
	"""The queue serves work order labels and reel/shelf labels: either flag opens it."""
	return labels_enabled() or reels_enabled()


def can_print(user=None):
	return bool(set(frappe.get_roles(user)) & LABEL_ROLES)


def _require_role():
	if not can_print():
		frappe.throw("Printing labels needs a manufacturing or stock role.", frappe.PermissionError)


def _log(title):
	try:
		frappe.log_error(title=f"ilL labels: {title}", message=frappe.get_traceback())
	except Exception:
		pass


# ---------------------------------------------------------------- database: templates and jobs


def templates_for(source_doctype, *, include_manual=True, name=None):
	filters = {"enabled": 1, "source_doctype": source_doctype}
	if not include_manual:
		filters["auto_generate"] = 1
	if name:
		filters["name"] = name
	rows = frappe.get_all(
		TEMPLATE,
		filters=filters,
		fields=["name", "layout", "label_stock", "applies_to", "quantity_rule", "copies", "packet_order"],
	)
	return [dict(row) for row in rows]


def _existing_jobs(doctype, name):
	return [
		dict(row)
		for row in frappe.get_all(
			JOB,
			filters={"reference_doctype": doctype, "reference_name": name},
			fields=["name", "dedupe_key", "status", "context_hash", "is_stale", "label_template"],
		)
	]


def _job_values(row, info):
	context = row["context"]
	return {
		"label_template": row["template"],
		"layout": row["layout"],
		"label_stock": row["label_stock"],
		"reference_doctype": info["doctype"],
		"reference_name": info["name"],
		"work_order": info.get("work_order"),
		"sales_order": info.get("sales_order"),
		"sales_order_item": info.get("sales_order_item"),
		"unit_no": row["unit_no"],
		"unit_count": row["unit_count"],
		"piece_key": row.get("piece_key"),
		"piece_no": row.get("piece_no") or 1,
		"piece_count": row.get("piece_count") or 1,
		"ship_by": info.get("ship_by"),
		"context_json": json.dumps(context, sort_keys=True, default=str),
		"context_hash": context_hash(context),
	}


def apply_plan(plan, info):
	"""Write a ``reconcile`` plan. Runs as the enqueuing user, so permissions are skipped."""
	counts = {key: len(value) for key, value in plan.items()}
	for row in plan["insert"]:
		doc = frappe.get_doc(
			{"doctype": JOB, "status": "Queued", "dedupe_key": row["dedupe_key"], **_job_values(row, info)}
		)
		try:
			doc.insert(ignore_permissions=True)
		except frappe.DuplicateEntryError:
			counts["insert"] -= 1  # another worker made it first
	for name, row in plan["requeue"]:
		frappe.db.set_value(
			JOB, name, {"status": "Queued", "void_reason": None, "is_stale": 0, **_job_values(row, info)}
		)
	for name, row in plan["refresh"]:
		frappe.db.set_value(JOB, name, _job_values(row, info))
	for name in plan["cancel"]:
		frappe.db.set_value(
			JOB, name, {"status": "Cancelled", "void_reason": "No longer needed before printing"}
		)
	for name, reason in plan["void"]:
		frappe.db.set_value(
			JOB, name, {"status": "Void", "void_reason": f"{reason}. Pull this label from the folder."}
		)
	for name, row in plan["stale"]:
		values = _job_values(row, info)
		frappe.db.set_value(
			JOB,
			name,
			{"is_stale": 1, "context_json": values["context_json"], "context_hash": values["context_hash"]},
		)
	return counts


# ---------------------------------------------------------------- database: work orders


def _engine_for(item_code):
	try:
		from illumenate_lighting.illumenate_lighting.api import fixture_fulfillment

		return fixture_fulfillment.engine_for_item(item_code)
	except Exception:
		return None


SO_ROW_FIELDS = [
	"item_code",
	"item_name",
	"qty",
	"ill_fixture_type",
	"ill_section_label",
	"ill_mfg_length_mm",
	"ill_requested_length_mm",
	"ill_configured_fixture",
	"ill_configured_group",
	"ill_configured_tape_neon",
	"ill_configured_led_sheet",
]


def _safe_row(doctype, name, fields):
	"""``get_value`` that drops fields a site doesn't have yet instead of failing."""
	if not name:
		return {}
	meta = frappe.get_meta(doctype)
	present = [f for f in fields if f in ("name", "item_code", "item_name", "qty") or meta.has_field(f)]
	return frappe.db.get_value(doctype, name, present, as_dict=True) or {}


def work_order_info(work_order):
	"""Everything ``plan_labels`` needs for one Work Order, read once."""
	wo = frappe.get_doc("Work Order", work_order)
	so_row = _safe_row("Sales Order Item", wo.get("sales_order_item"), SO_ROW_FIELDS)
	so = (
		frappe.db.get_value(
			"Sales Order", wo.sales_order, ["customer_name", "po_no", "delivery_date"], as_dict=True
		)
		if wo.get("sales_order")
		else {}
	) or {}
	fixture = wo.get("ill_configured_fixture") or so_row.get("ill_configured_fixture")
	fixture_part = (
		frappe.db.get_value("ilL-Configured-Fixture", fixture, "display_part_number") if fixture else None
	)
	project = ""
	if wo.get("sales_order"):
		try:
			from illumenate_lighting.illumenate_lighting import printing

			project = (
				printing.ill_print_project(frappe.get_doc("Sales Order", wo.sales_order)).get("project") or ""
			)
		except Exception:
			project = ""
	values = wo.as_dict()
	values["url"] = frappe.utils.get_url(f"/app/work-order/{quote(wo.name)}")
	kind = work_order_kind(values, so_row, _engine_for(wo.production_item))
	return {
		"doctype": "Work Order",
		"name": wo.name,
		"docstatus": wo.docstatus,
		"kind": kind,
		"qty": wo.qty,
		"work_order": wo.name,
		"sales_order": wo.get("sales_order"),
		"sales_order_item": wo.get("sales_order_item"),
		"ship_by": iso_date(wo.get("expected_delivery_date") or so.get("delivery_date")),
		"context": build_context(kind, values, so, so_row, fixture_part, project),
	}


def sync_work_order(work_order, include_manual=False):
	"""Queue, refresh, cancel or void a Work Order's labels so they match it now.

	Background job (from the hooks) or direct call (Generate). ``include_manual`` also makes
	labels from templates that don't queue automatically.
	"""
	if not labels_enabled() or not frappe.db.exists("Work Order", work_order):
		return None
	info = work_order_info(work_order)
	if info["docstatus"] == 2:
		return release_document("Work Order", work_order, "Work order cancelled")
	wanted = plan_labels(templates_for("Work Order", include_manual=include_manual), info)
	reason = f"Work order {work_order} changed (now qty {fmt_qty(info['qty'])})"
	return apply_plan(reconcile(_existing_jobs("Work Order", work_order), wanted, reason), info)


def release_document(doctype, name, reason):
	"""Cancel unprinted and void printed labels of a cancelled or deleted document."""
	info = {"doctype": doctype, "name": name}
	return apply_plan(reconcile(_existing_jobs(doctype, name), [], reason), info)


# ---------------------------------------------------------------- hooks (never raise)


def _enqueue_sync(work_order):
	kwargs = {
		"work_order": work_order,
		"queue": "short",
		"enqueue_after_commit": True,
		"job_id": f"ill-labels-{work_order}",
	}
	try:
		frappe.enqueue(f"{API}.sync_work_order", deduplicate=True, **kwargs)
	except TypeError:  # a Frappe without ``deduplicate``: the dedupe keys keep it safe
		frappe.enqueue(f"{API}.sync_work_order", **kwargs)


def on_work_order_insert(doc, method=None):
	if not labels_enabled():
		return
	try:
		if _setting("labels_auto_work_order") in (0, "0", False):
			return
		_enqueue_sync(doc.name)
	except Exception:
		_log("queue on work order insert")


def on_work_order_update(doc, method=None):
	if not labels_enabled():
		return
	try:
		if not doc.get_doc_before_save():
			return  # a new work order: after_insert queued it
		if any(doc.has_value_changed(field) for field in WATCHED_FIELDS):
			_enqueue_sync(doc.name)
	except Exception:
		_log("re-plan on work order update")


def on_work_order_cancel(doc, method=None):
	if not labels_enabled():
		return
	try:
		release_document("Work Order", doc.name, f"Work order {doc.name} cancelled")
	except Exception:
		_log("release on work order cancel")


def on_work_order_trash(doc, method=None):
	if not labels_enabled():
		return
	try:
		release_document("Work Order", doc.name, f"Work order {doc.name} deleted")
	except Exception:
		_log("release on work order delete")


# ---------------------------------------------------------------- other sources (reels, shelves)


def queue_documents(doctype, names, template_name, *, requeue_printed=False):
	"""Queue one template's labels for reels or shelves. Returns how many were queued."""
	from illumenate_lighting.illumenate_lighting.api import reels

	templates = templates_for(doctype, name=template_name)
	if not templates:
		frappe.throw(f"The {template_name} label template is missing or disabled.")
	queued = 0
	for name in names:
		info = {
			"doctype": doctype,
			"name": name,
			"context": reels.label_context(doctype, name, templates[0]["layout"]),
		}
		wanted = plan_labels(templates, info)
		existing = [job for job in _existing_jobs(doctype, name) if job["label_template"] == template_name]
		plan = reconcile(existing, wanted)
		plan["cancel"], plan["void"] = [], []  # other templates' jobs are not ours to touch
		if requeue_printed:
			by_key = {job["dedupe_key"]: job for job in existing}
			for row in wanted:
				job = by_key.get(row["dedupe_key"])
				if job and job["status"] == "Printed":
					plan["requeue"].append((job["name"], row))
		counts = apply_plan(plan, info)
		queued += counts["insert"] + counts["requeue"]
	return queued


# ---------------------------------------------------------------- endpoints


def _template_meta():
	return {row.name: row for row in frappe.get_all(TEMPLATE, fields=["name", "packet_order"])}


def _stock_meta():
	return {
		row.name: row
		for row in frappe.get_all(
			STOCK,
			fields=[
				"name",
				"width_in",
				"height_in",
				"printer_name",
				"driver_paper_name",
				"label_part_no",
				"print_order",
				"enabled",
			],
		)
	}


JOB_FIELDS = [
	"name",
	"status",
	"label_template",
	"layout",
	"label_stock",
	"reference_doctype",
	"reference_name",
	"work_order",
	"sales_order",
	"unit_no",
	"unit_count",
	"piece_no",
	"piece_count",
	"piece_key",
	"ship_by",
	"is_stale",
	"print_count",
	"printed_at",
	"void_reason",
	"batch",
	"context_json",
]


def _job_rows(filters, limit=2000):
	templates = _template_meta()
	rows = []
	for job in frappe.get_all(
		JOB, filters=filters, fields=JOB_FIELDS, limit_page_length=limit, order_by="creation asc"
	):
		job = dict(job)
		context = json.loads(job.pop("context_json") or "{}")
		job["packet_order"] = (templates.get(job["label_template"]) or {}).get("packet_order") or 0
		job["ship_by"] = iso_date(job.get("ship_by"))
		job["summary"] = job_summary(job, context)
		job["fixture_type"] = context.get("fixture_type") or ""
		rows.append(job)
	return rows


def _as_list(value):
	if not value:
		return []
	if isinstance(value, str):
		value = value.strip()
		return (
			json.loads(value) if value.startswith("[") else [v.strip() for v in value.split(",") if v.strip()]
		)
	return list(value)


@frappe.whitelist()
def get_queue(sales_order=None, work_orders=None, include_printed=0):
	"""The print station: one group per roll (so per printer), in print order."""
	result = {
		"labels_enabled": labels_enabled(),
		"reels_enabled": reels_enabled(),
		"can_print": can_print(),
		"groups": [],
		"unconfirmed": [],
	}
	if not queue_enabled() or not result["can_print"]:
		return result
	statuses = ["Queued", "Sent", "Printed"] if int(include_printed or 0) else ["Queued"]
	filters = {"status": ["in", statuses]}
	if sales_order:
		filters["sales_order"] = sales_order
	wos = _as_list(work_orders)
	if wos:
		filters["work_order"] = ["in", wos]
	stocks = _stock_meta()
	groups = {}
	for job in _job_rows(filters):
		stock = stocks.get(job["label_stock"]) or {}
		group = groups.setdefault(
			job["label_stock"],
			{
				"stock": job["label_stock"],
				"printer_name": stock.get("printer_name") or "",
				"driver_paper_name": stock.get("driver_paper_name") or "",
				"label_part_no": stock.get("label_part_no") or "",
				"width_in": stock.get("width_in"),
				"height_in": stock.get("height_in"),
				"print_order": stock.get("print_order") or 0,
				"jobs": [],
			},
		)
		group["jobs"].append(job)
	for group in groups.values():
		queued = [j for j in group["jobs"] if j["status"] == "Queued"]
		group["count"] = len(queued)
		group["work_orders"] = len({j["work_order"] for j in queued if j["work_order"]})
		dates = [j["ship_by"] for j in queued if j["ship_by"]]
		group["earliest_ship_by"] = min(dates) if dates else None
	result["groups"] = order_groups(list(groups.values()))
	result["unconfirmed"] = [
		dict(row)
		for row in frappe.get_all(
			BATCH,
			filters={"status": "Sent"},
			fields=["name", "label_stock", "printer_name", "label_count", "sent_at", "sent_by"],
			order_by="sent_at asc",
			limit_page_length=20,
		)
	]
	return result


@frappe.whitelist()
def get_document_labels(doctype, name):
	"""All labels of a Work Order, a Sales Order (through its work orders), a reel or a shelf.

	Called on every form refresh, so it answers "off" quietly instead of raising when labels
	are off or the user has no label role.
	"""
	if not queue_enabled() or not can_print():
		return {"enabled": False, "jobs": [], "counts": {}, "stocks": {}}
	if doctype == "Sales Order":
		filters = {"sales_order": name}
	elif doctype == "Work Order":
		filters = {"work_order": name}
	else:
		filters = {"reference_doctype": doctype, "reference_name": name}
	jobs = sorted(_job_rows(filters), key=job_sort_key)
	counts = {}
	for job in jobs:
		counts[job["status"]] = counts.get(job["status"], 0) + 1
	return {"enabled": labels_enabled(), "jobs": jobs, "counts": counts, "stocks": _stock_meta()}


@frappe.whitelist(methods=["POST"])
def generate(doctype, name, template=None):
	"""Make labels now, even from templates that don't queue automatically."""
	_require_role()
	if doctype == "Work Order":
		if not labels_enabled():
			frappe.throw("Turn on Labels in ilL-Production-Settings first.")
		return {"Work Order": {name: sync_work_order(name, include_manual=True)}}
	if doctype == "Sales Order":
		if not labels_enabled():
			frappe.throw("Turn on Labels in ilL-Production-Settings first.")
		out = {}
		for wo in frappe.get_all(
			"Work Order", filters={"sales_order": name, "docstatus": ["<", 2]}, pluck="name"
		):
			out[wo] = sync_work_order(wo, include_manual=True)
		return {"Work Order": out}
	if doctype in ("ilL-Reel", "ilL-Reel-Location"):
		default = "Reel" if doctype == "ilL-Reel" else "Shelf"
		return {"queued": queue_documents(doctype, [name], template or default, requeue_printed=True)}
	frappe.throw(f"Labels are not made for {doctype}.")


def _jobs_in_order(names):
	rows = frappe.get_all(JOB, filters={"name": ["in", names]}, fields=JOB_FIELDS)
	templates = _template_meta()
	jobs = []
	for row in rows:
		row = dict(row)
		row["packet_order"] = (templates.get(row["label_template"]) or {}).get("packet_order") or 0
		row["ship_by"] = iso_date(row.get("ship_by"))
		jobs.append(row)
	return sorted(jobs, key=job_sort_key)


@frappe.whitelist(methods=["POST"])
def create_batch(label_stock, job_names):
	"""Put Queued labels of one roll in a batch (page order) and return its PDF URL.

	Jobs go to Sent, never Printed: only a person's confirm marks them printed.
	"""
	_require_role()
	names = _as_list(job_names)
	if not names:
		frappe.throw("Choose at least one label.")
	jobs = _jobs_in_order(names)
	if len(jobs) != len(set(names)):
		frappe.throw("Some of those labels no longer exist. Refresh the queue.")
	wrong_roll = [j["name"] for j in jobs if j["label_stock"] != label_stock]
	if wrong_roll:
		frappe.throw(f"{len(wrong_roll)} label(s) are not on the {label_stock} roll.")
	not_queued = [j["name"] for j in jobs if j["status"] != "Queued"]
	if not_queued:
		frappe.throw(f"{len(not_queued)} label(s) are no longer queued. Refresh the queue.")
	stock = frappe.get_doc(STOCK, label_stock)
	batch = frappe.get_doc(
		{
			"doctype": BATCH,
			"label_stock": label_stock,
			"printer_name": stock.printer_name,
			"status": "Sent",
			"label_count": len(jobs),
			"sent_by": frappe.session.user,
			"sent_at": frappe.utils.now_datetime(),
			"jobs": [
				{
					"job": job["name"],
					"position": position,
					"work_order": job.get("work_order") or job.get("reference_name"),
					"summary": truncate(job_summary(job, json.loads(job.get("context_json") or "{}")), 140),
				}
				for position, job in enumerate(jobs, start=1)
			],
		}
	).insert(ignore_permissions=True)
	for job in jobs:
		frappe.db.set_value(JOB, job["name"], {"status": "Sent", "batch": batch.name})
	return {
		"batch": batch.name,
		"pdf_url": f"/api/method/{API}.batch_pdf?batch={quote(batch.name)}",
		"printer_name": stock.printer_name or "",
		"driver_paper_name": stock.driver_paper_name or "",
		"count": len(jobs),
	}


def _send_pdf(content, filename):
	frappe.local.response.filename = filename
	frappe.local.response.filecontent = content
	frappe.local.response.type = "pdf"


@frappe.whitelist()
def batch_pdf(batch):
	"""The batch's labels as one PDF at the roll's exact size, one label per page."""
	_require_role()
	doc = frappe.get_doc(BATCH, batch)
	order = [row.job for row in sorted(doc.jobs, key=lambda r: r.position)]
	rows = {
		row.name: row
		for row in frappe.get_all(
			JOB, filters={"name": ["in", order]}, fields=["name", "layout", "context_json"]
		)
	}
	labels = [
		(rows[name].layout, json.loads(rows[name].context_json or "{}")) for name in order if name in rows
	]
	_send_pdf(render_pdf(labels, frappe.get_doc(STOCK, doc.label_stock)), f"{batch}.pdf")


@frappe.whitelist(methods=["POST"])
def confirm_batch(batch, reprint_jobs=None):
	"""A person confirms what printed. Labels to reprint go back to the queue."""
	_require_role()
	doc = frappe.get_doc(BATCH, batch)
	again = set(_as_list(reprint_jobs))
	now, user = frappe.utils.now_datetime(), frappe.session.user
	printed = 0
	for row in doc.jobs:
		status = frappe.db.get_value(JOB, row.job, "status")
		if status != "Sent":
			continue  # voided or requeued meanwhile: leave it
		if row.job in again:
			frappe.db.set_value(JOB, row.job, "status", "Queued")
			continue
		count = int(frappe.db.get_value(JOB, row.job, "print_count") or 0)
		frappe.db.set_value(
			JOB,
			row.job,
			{
				"status": "Printed",
				"print_count": count + 1,
				"printed_at": now,
				"printed_by": user,
				"is_stale": 0,
			},
		)
		printed += 1
	frappe.db.set_value(
		BATCH,
		batch,
		{"status": "Partly reprinted" if again else "Confirmed", "confirmed_at": now, "confirmed_by": user},
	)
	return {"printed": printed, "requeued": len(again)}


@frappe.whitelist(methods=["POST"])
def reprint(job_names):
	"""Printed (or stuck Sent) labels back to the queue. Void and cancelled ones stay put."""
	_require_role()
	moved = 0
	for name in _as_list(job_names):
		status = frappe.db.get_value(JOB, name, "status")
		if status not in ("Printed", "Sent"):
			continue
		frappe.db.set_value(JOB, name, "status", "Queued")
		try:
			frappe.get_doc(JOB, name).add_comment(
				"Comment", f"Requeued for reprint by {frappe.session.user} (was {status})."
			)
		except Exception:
			pass
		moved += 1
	return {"requeued": moved}


@frappe.whitelist()
def preview(template, name):
	"""PDF of what a template would print for a work order, reel or shelf, without queuing."""
	_require_role()
	row = frappe.get_doc(TEMPLATE, template)
	tmpl = {
		"name": row.name,
		"layout": row.layout,
		"label_stock": row.label_stock,
		"applies_to": "All",
		"quantity_rule": row.quantity_rule,
		"copies": 1,
		"packet_order": row.packet_order,
	}
	if row.source_doctype == "Work Order":
		info = work_order_info(name)
		# The other templates fill the packet checklist; this one shows whatever the build kind.
		others = [t for t in templates_for("Work Order") if t["name"] != row.name]
		wanted = [w for w in plan_labels([*others, tmpl], info) if w["template"] == row.name]
		if not wanted:  # per-unit on a stock build: show one anyway
			wanted = plan_labels([{**tmpl, "quantity_rule": "Per document"}], info)
	else:
		from illumenate_lighting.illumenate_lighting.api import reels

		info = {
			"doctype": row.source_doctype,
			"name": name,
			"context": reels.label_context(row.source_doctype, name, row.layout),
		}
		wanted = plan_labels([tmpl], info)
	labels = [(w["layout"], w["context"]) for w in wanted[:50]]
	_send_pdf(render_pdf(labels, frappe.get_doc(STOCK, row.label_stock)), f"preview-{row.layout}.pdf")


@frappe.whitelist()
def test_print(label_stock):
	"""One sample page with a border and a 10 mm ruler, to check size and orientation."""
	_require_role()
	stock = frappe.get_doc(STOCK, label_stock)
	_send_pdf(
		render_pdf([("_test", {"doc_label": "TEST", "stock": stock.stock_name})], stock), "test-print.pdf"
	)


# ---------------------------------------------------------------- rendering


def qr_svg(payload):
	"""QR code as an SVG data URI (vector, so it stays sharp at the printer's dpi)."""
	if not payload:
		return ""
	import segno

	return segno.make(payload, error="m").svg_data_uri(scale=1, border=0, dark="#000")


def code128_modules(value):
	"""Code 128 as a string of 1 (bar) and 0 (space) modules, quiet zones excluded."""
	import barcode

	modules = barcode.get_barcode_class("code128")(str(value)).build()[0]
	return modules.strip("0")


def code128_svg(value):
	"""Code 128 as an SVG data URI; the layout sets its width and height."""
	if not value:
		return ""
	modules = code128_modules(value)
	runs, start = [], None
	for index, bit in enumerate(modules + "0"):
		if bit == "1" and start is None:
			start = index
		elif bit == "0" and start is not None:
			runs.append(f'<rect x="{start}" y="0" width="{index - start}" height="1"/>')
			start = None
	svg = (
		f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {len(modules)} 1" '
		f'preserveAspectRatio="none" shape-rendering="crispEdges">{"".join(runs)}</svg>'
	)
	return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def _logo_src():
	"""The label logo as a data URI, or "" (a broken image link fails the whole PDF)."""
	cache = getattr(frappe.local, "ill_label_logo", None)
	if cache is not None:
		return cache
	src = ""
	try:
		url = _setting("labels_logo") or DEFAULT_LOGO
		name = None
		for candidate in (url, unquote(url)):
			name = frappe.db.get_value("File", {"file_url": candidate}, "name")
			if name:
				break
		if name:
			content = frappe.get_doc("File", name).get_content()
			if isinstance(content, str):
				content = content.encode("latin-1")
			mime = "image/png" if url.lower().endswith(".png") else "image/jpeg"
			src = f"data:{mime};base64," + base64.b64encode(content).decode("ascii")
	except Exception:
		src = ""
	frappe.local.ill_label_logo = src
	return src


def _fonts():
	try:
		from illumenate_lighting.illumenate_lighting import printing

		return printing.ill_print_fonts()
	except Exception:
		return []


def page_mm(stock):
	return round(float(stock.width_in) * MM_PER_INCH, 2), round(float(stock.height_in) * MM_PER_INCH, 2)


def render_html(labels, stock):
	"""One HTML document, one label per page, from ``[(layout, context)]``."""
	width, height = page_mm(stock)
	logo = _logo_src()
	printed_on = fmt_date(frappe.utils.nowdate())
	pages = []
	for layout, context in labels:
		c = dict(context)
		c["logo_src"] = logo
		c["printed_on"] = printed_on
		c["qr_src"] = qr_svg(c.get("qr_payload"))
		c["barcode_src"] = code128_svg(c.get("barcode"))
		pages.append(
			frappe.render_template(
				f"templates/labels/{layout}.html",
				{"c": c, "fit": fit_pt, "truncate": truncate, "width_mm": width, "height_mm": height},
			)
		)
	return frappe.render_template(
		"templates/labels/_document.html",
		{"pages": pages, "width_mm": width, "height_mm": height, "fonts": _fonts()},
	)


def _pdf_page_ok(pdf, width, height):
	try:
		from io import BytesIO

		from pypdf import PdfReader

		box = PdfReader(BytesIO(pdf)).pages[0].mediabox
		points = 72 / MM_PER_INCH
		return abs(float(box.width) - width * points) < 3 and abs(float(box.height) - height * points) < 3
	except Exception:
		return True  # can't tell: trust Frappe


def render_pdf(labels, stock):
	"""PDF bytes at the roll's exact page size, no margins."""
	from frappe.utils.pdf import get_pdf

	width, height = page_mm(stock)
	html = render_html(labels, stock)
	options = {
		"page-width": f"{width}mm",
		"page-height": f"{height}mm",
		"margin-top": "0mm",
		"margin-bottom": "0mm",
		"margin-left": "0mm",
		"margin-right": "0mm",
		"disable-smart-shrinking": "",
	}
	pdf = get_pdf(html, options=dict(options))
	if _pdf_page_ok(pdf, width, height):
		return pdf
	# Frappe added its default page size over ours: call wkhtmltopdf directly.
	try:
		import pdfkit

		return pdfkit.from_string(html, False, options={**options, "encoding": "UTF-8", "quiet": ""})
	except Exception:
		_log("label PDF came out at the wrong page size")
		return pdf
