# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Jinja methods for the ilL print formats (print_format/ill_*).

Frappe renders print formats in a sandbox that only exposes whitelisted helpers, so
anything that needs a lookup or real Python lives here and is registered under
``jinja.methods`` in hooks.py. The shared layout and macros are in
``templates/print/ill_print.html``.

Every function here returns a safe empty value instead of raising: a failed lookup
must never stop a quote, order or invoice from printing.
"""

import html
import re

import frappe
from frappe.utils.html_utils import sanitize_html

# Shown when the Company record has no phone, email or website of its own.
# Set them on the Company (Phone No, Email, Website) to override these.
COMPANY_FALLBACK = {
	"phone": "(425) 381-2447",
	"email": "sales@illumenate.lighting",
	"website": "illumenate.lighting",
	# Vendor-facing documents (purchase orders, RFQs) ask for replies here.
	"purchasing_email": "purchasing@illumenate.lighting",
}

# Terms and Conditions records the print formats fall back to when a document has no
# terms of its own. patches/seed_print_terms.py creates them; staff edit them in Desk.
TERMS = {
	"sales": "ilL Sales Terms",
	"retail": "ilL Retail Terms",
	"purchase": "ilL Purchase Terms",
}

# Short unit names for quantity columns.
UOM_SHORT = {
	"inch": "in",
	"inches": "in",
	"nos": "ea",
	"ea": "ea",
	"each": "ea",
	"unit": "ea",
	"foot": "ft",
	"feet": "ft",
	"meter": "m",
	"millimeter": "mm",
}

# Description keys that are internal, repeated elsewhere on the line, or not useful on paper.
_SKIP_KEYS = {
	"part number",
	"template",
	"assembly mode",
	"build description",
	"pcb mounting",
	"pcb finish",
	"feed type",
}
_RENAME_KEYS = {"output level": "Output", "total watts": "Watts"}
_EMPTY_VALUES = {"", "-", "n/a", "na", "none", "null"}
_TAG = re.compile(r"<[^>]+>")
_BREAK = re.compile(r"<\s*(br|/p|/div|/li)\b[^>]*>", re.I)


def _log(title):
	try:
		frappe.log_error(title=title)
	except Exception:
		pass


def _plain_text(value) -> str:
	text = _BREAK.sub("\n", str(value or ""))
	return html.unescape(_TAG.sub("", text)).replace("\xa0", " ")


def ill_print_asset_base() -> str:
	"""The site URL for font and image assets (wkhtmltopdf needs absolute URLs)."""
	try:
		return frappe.utils.get_url().rstrip("/")
	except Exception:
		return ""


def ill_print_specs(item, max_specs=8, max_notes=3) -> dict:
	"""A line's configured description, condensed for print.

	Configured items carry a long description: an internal reference, the part number,
	``Key: Value`` specs, then a "Build Description" dump meant for production. Returns
	``{"part_number", "specs": [(label, value)], "notes": [str]}`` with the internal
	parts and "N/A" values dropped. Pipe-separated summaries are dropped too: they
	repeat the item name.
	"""
	result = {"part_number": "", "specs": [], "notes": []}
	try:
		description = _plain_text(item.get("description"))
		name = (item.get("item_name") or "").strip()
		code = (item.get("item_code") or "").strip()
		if not description.strip() or description.strip() in (name, code):
			return result
		description = re.split(r"\n\s*Build Description\s*:", description, maxsplit=1, flags=re.I)[0]
		seen = set()
		for raw in description.split("\n"):
			line = " ".join(raw.split())
			if not line or line in (name, code):
				continue
			if line.lower().startswith("configured ") and ":" in line:
				continue  # "Configured LED Tape: ILL-CTN-00297" is an internal reference
			if " | " in line:
				continue
			key, sep, value = line.partition(":")
			key, value = key.strip(), value.strip()
			if sep and key and len(key) <= 24 and not key.lower().startswith(("http", "https")):
				low = key.lower()
				if low == "part number":
					result["part_number"] = value
					continue
				if low in _SKIP_KEYS or value.lower() in _EMPTY_VALUES:
					continue
				if low == "length":
					value = value.split("(requested")[0].strip()
				label = _RENAME_KEYS.get(low, key)
				if label.lower() in seen:
					continue
				seen.add(label.lower())
				if len(result["specs"]) < max_specs:
					result["specs"].append((label, value))
				continue
			if (name and name in line) or (code and code in line):
				continue
			if len(result["notes"]) < max_notes:
				result["notes"].append(line)
	except Exception:
		_log("ilL print: could not read a line description")
	return result


def ill_print_note(text) -> str:
	"""A plain-text note without generated build summaries ("A: x | B: y | ...") pasted into it.

	Notes are plain text, so nothing that looks like markup is removed; templates escape them.
	"""
	lines = []
	for line in str(text or "").replace("\r\n", "\n").split("\n"):
		if line.count(" | ") >= 2 and line.count(":") >= 2:
			continue
		if line.strip():
			lines.append(line.strip())
	return "\n".join(lines)


def ill_print_warehouse(name) -> str:
	"""A warehouse without the company abbreviation: "Stores - ilL" -> "Stores"."""
	return re.sub(r"\s+-\s+[A-Za-z]{2,6}$", "", str(name or ""))


def ill_print_qty(qty, uom=None) -> str:
	"""``792 in``, ``2 ea``, ``1.5 ft``: no trailing zeros, short unit names."""
	try:
		number = float(qty or 0)
		text = f"{number:,.0f}" if number == int(number) else f"{number:,.3f}".rstrip("0").rstrip(".")
	except (TypeError, ValueError):
		text = str(qty or "")
	unit = (uom or "").strip()
	unit = UOM_SHORT.get(unit.lower(), unit)
	return f"{text} {unit}".strip()


def ill_print_sections(items) -> list:
	"""Group lines into sections (rooms / areas) in document order.

	A row with a section label, no item code and zero quantity is a section header; the
	rows after it inherit its label until the next one. Returns
	``[{"label", "items", "subtotal", "list_subtotal"}]`` with one unlabelled section
	when nothing is labelled.
	"""
	sections, by_label, current = [], {}, ""
	try:
		for item in items or []:
			label = (item.get("ill_section_label") or item.get("custom_ill_section_label") or "").strip()
			if label and not item.get("item_code") and not item.get("qty"):
				current = label
				if label.lower() not in by_label:
					by_label[label.lower()] = {
						"label": label,
						"items": [],
						"subtotal": 0.0,
						"list_subtotal": 0.0,
					}
					sections.append(by_label[label.lower()])
				continue
			effective = label or current
			key = effective.lower()
			if key not in by_label:
				by_label[key] = {"label": effective, "items": [], "subtotal": 0.0, "list_subtotal": 0.0}
				sections.append(by_label[key])
			section = by_label[key]
			section["items"].append(item)
			section["subtotal"] += float(item.get("amount") or 0)
			section["list_subtotal"] += ill_print_msrp(item) * float(item.get("qty") or 0)
	except Exception:
		_log("ilL print: could not group lines into sections")
		return [{"label": "", "items": list(items or []), "subtotal": 0.0, "list_subtotal": 0.0}]
	return sections


def ill_print_msrp(item) -> float:
	"""A line's suggested retail unit price: the Standard Selling list rate.

	Dealer pricing rules take a percentage off that rate, so the list rate (with any
	margin) is the MSRP. A line priced above list, or with no list rate, uses its rate.
	"""
	try:
		listed = float(item.get("rate_with_margin") or 0) or float(item.get("price_list_rate") or 0)
		return max(listed, float(item.get("rate") or 0))
	except (TypeError, ValueError):
		return 0.0


def ill_print_pricing(items) -> dict:
	"""Which price columns a dealer document needs and its list-price total."""
	info = {"has_discount": False, "list_total": 0.0}
	try:
		for item in items or []:
			listed = float(item.get("price_list_rate") or 0)
			rate = float(item.get("rate") or 0)
			if float(item.get("discount_percentage") or 0) or (listed and rate < listed - 0.005):
				info["has_discount"] = True
			info["list_total"] += ill_print_msrp(item) * float(item.get("qty") or 0)
	except Exception:
		_log("ilL print: could not read line pricing")
	return info


def ill_print_discount(item) -> float:
	"""The line's discount off list, in percent (0 when sold at or above list)."""
	try:
		pct = float(item.get("discount_percentage") or 0)
		if pct:
			return round(pct, 2)
		listed = float(item.get("price_list_rate") or 0)
		rate = float(item.get("rate") or 0)
		if listed and rate < listed:
			return round((listed - rate) / listed * 100, 2)
	except (TypeError, ValueError):
		pass
	return 0.0


def ill_print_totals(doc) -> dict:
	"""Subtotal, discount and charge rows plus the grand total of a sales or purchase document.

	Charges are the taxes table (shipping, sales tax, card fees) with zero rows dropped;
	a percentage charge shows its rate. Returns ``{"rows": [(label, amount)], "grand"}``.
	"""
	rows = []
	try:
		rows.append(("Subtotal", float(doc.get("total") or 0)))
		discount = float(doc.get("discount_amount") or 0)
		if discount:
			pct = float(doc.get("additional_discount_percentage") or 0)
			rows.append((f"Discount ({pct:g}%)" if pct else "Discount", -discount))
		for tax in doc.get("taxes") or []:
			amount = float(tax.get("tax_amount_after_discount_amount") or tax.get("tax_amount") or 0)
			if not amount:
				continue
			label = (tax.get("description") or tax.get("account_head") or "Charges").strip()
			rate = float(tax.get("rate") or 0)
			if tax.get("charge_type") != "Actual" and rate and f"{rate:g}" not in label:
				label = f"{label} ({rate:g}%)"
			if tax.get("add_deduct_tax") == "Deduct":
				amount = -amount
			rows.append((label, amount))
		grand = float(doc.get("rounded_total") or 0) or float(doc.get("grand_total") or 0)
		if doc.get("rounded_total") and abs(float(doc.get("rounding_adjustment") or 0)) >= 0.005:
			rows.append(("Rounding", float(doc.rounding_adjustment)))
		return {"rows": rows, "grand": grand}
	except Exception:
		_log("ilL print: could not read the totals")
		return {"rows": rows, "grand": float(doc.get("grand_total") or 0) if doc else 0.0}


def ill_print_packed(doc) -> dict:
	"""Product bundle (kit) components by the line they ship with: ``{row name: [rows]}``."""
	packed = {}
	try:
		for row in doc.get("packed_items") or []:
			parent = row.get("parent_detail_docname")
			if parent:
				packed.setdefault(parent, []).append(row)
	except Exception:
		_log("ilL print: could not read kit components")
	return packed


def _mm(value) -> str:
	"""``2134 mm (84.0")`` for a length in millimetres; "" for none."""
	try:
		mm = float(value or 0)
	except (TypeError, ValueError):
		return ""
	return f'{mm:,.0f} mm ({mm / 25.4:.1f}")' if mm else ""


def ill_print_build(doc) -> dict:
	"""Production details for a Work Order traveler.

	Finds the configured record behind the production item (from the "Configured ...:
	<ref>" line of its description, else by work order or configured item) and returns
	``{"ref", "kind", "facts": [(label, value)], "cuts": {"columns", "rows"}, "runs",
	"steps": [build description parts]}``. Empty parts when nothing is configured.
	"""
	build = {"ref": "", "kind": "", "facts": [], "cuts": {"columns": [], "rows": []}, "runs": [], "steps": []}
	try:
		text = _plain_text(doc.get("description"))
		head, _sep, tail = text.partition("Build Description:")
		build["steps"] = [part.strip() for part in tail.replace("\n", " | ").split(" | ") if part.strip()][
			:40
		]
		match = re.search(r"Configured [^:\n]*:\s*(ILL-[A-Z]+-[0-9A-Za-z]+)", head)
		ref = match.group(1) if match else ""
		item = doc.get("production_item")
		for doctype in ("ilL-Configured-Fixture", "ilL-Configured-Tape-Neon"):
			if ref:
				if (ref.startswith("ILL-CF-") and doctype == "ilL-Configured-Fixture") or (
					ref.startswith("ILL-CTN-") and doctype == "ilL-Configured-Tape-Neon"
				):
					name = ref if frappe.db.exists(doctype, ref) else None
				else:
					continue
			else:
				name = frappe.db.get_value(doctype, {"work_order": doc.get("name")}) or (
					frappe.db.get_value(doctype, {"configured_item": item}) if item else None
				)
			if not name:
				continue
			record = frappe.get_doc(doctype, name)
			build["ref"], build["kind"] = name, doctype
			if doctype == "ilL-Configured-Fixture":
				build["facts"] = [
					("Template", record.fixture_template),
					("Finish", record.finish),
					("Lens", record.lens_appearance),
					("Mounting", record.mounting_method),
					(
						"Endcaps",
						" / ".join(v for v in (record.endcap_style_start, record.endcap_style_end) if v)
						+ (f" ({record.endcap_color})" if record.endcap_color else ""),
					),
					("Power feed", record.power_feed_type),
					("Environment", record.environment_rating),
					("Requested length", _mm(record.requested_overall_length_mm)),
					("Built length", _mm(record.manufacturable_overall_length_mm)),
					("Tape cut length", _mm(record.tape_cut_length_mm)),
					("Runs", record.runs_count),
					("Total watts", f"{record.total_watts:g} W" if record.total_watts else ""),
					("Assembly", (record.assembly_mode or "").replace("_", " ").title()),
				]
				build["cuts"] = {
					"columns": ["Profile cut", "Lens cut", "Tape cut", "Start leader", "End jumper", "Notes"],
					"rows": [
						[
							seg.segment_index,
							_mm(seg.profile_cut_len_mm),
							_mm(seg.lens_cut_len_mm),
							_mm(seg.tape_cut_len_mm),
							_mm(seg.start_leader_len_mm),
							_mm(seg.end_jumper_len_mm),
							seg.notes or "",
						]
						for seg in record.segments or []
					],
				}
				build["runs"] = [
					[
						run.run_index,
						_mm(run.run_len_mm),
						f"{run.run_watts:g} W" if run.run_watts else "",
						_mm(run.leader_len_mm),
					]
					for run in record.runs or []
				]
			else:
				build["facts"] = [
					("Category", record.product_category),
					("Template", record.tape_neon_template),
					("CCT", record.cct),
					("Output", record.output_level),
					("Environment", record.environment_rating),
					("Finish", record.finish),
					("Feed", " / ".join(v for v in (record.feed_type, record.feed_direction) if v)),
					("Requested length", _mm(record.requested_length_mm)),
					("Built length", _mm(record.manufacturable_length_mm)),
					("Cut increment", f"{record.cut_increment_mm:g} mm" if record.cut_increment_mm else ""),
					("Total watts", f"{record.total_watts:g} W" if record.total_watts else ""),
					("Assembly", (record.assembly_mode or "").replace("_", " ").title()),
				]
				build["cuts"] = {
					"columns": ["Built length", "Tape cut", "Start", "End", "Watts", "Notes"],
					"rows": [
						[
							seg.segment_index,
							_mm(seg.manufacturable_length_mm),
							_mm(seg.tape_cut_len_mm),
							" ".join(
								str(v)
								for v in (
									seg.start_feed_direction,
									seg.start_power_feed_type,
									f'{seg.start_lead_length_inches:g}" lead'
									if seg.start_lead_length_inches
									else "",
								)
								if v
							),
							" ".join(
								str(v)
								for v in (
									seg.end_type,
									f'{seg.end_cable_length_inches:g}" cable'
									if seg.end_cable_length_inches
									else "",
								)
								if v
							),
							f"{seg.watts:g} W" if seg.watts else "",
							seg.notes or "",
						]
						for seg in record.segments or []
					],
				}
			build["facts"] = [(label, value) for label, value in build["facts"] if value]
			break
	except Exception:
		_log("ilL print: could not read the build for a work order")
	return build


def ill_print_order_line(name) -> dict:
	"""Fixture type, section and notes of a Sales Order line, for the traveler."""
	try:
		if name:
			values = frappe.db.get_value(
				"Sales Order Item",
				name,
				["ill_fixture_type", "ill_section_label", "additional_notes", "parent"],
				as_dict=True,
			)
			if values:
				return values
	except Exception:
		_log("ilL print: could not read the sales order line")
	return {}


def ill_print_schedule(doc) -> dict:
	"""A fixture schedule for print: its project and its lines grouped by location.

	Each line becomes ``{"type", "qty", "maker", "name", "code", "specs", "notes",
	"status"}``. ilLumenate lines take their name and specs from the configured Item;
	power supplies say which line they feed; other manufacturers' lines list the
	model and electrical details entered on the schedule.
	"""
	info = {"project": {}, "sections": []}
	try:
		if doc.get("ill_project"):
			info["project"] = (
				frappe.db.get_value(
					"ilL-Project",
					doc.ill_project,
					["project_name", "location", "estimated_start_date", "description"],
					as_dict=True,
				)
				or {}
			)
		lines = doc.get("lines") or []
		ids = {line.get("line_key"): line.get("line_id") for line in lines if line.get("line_key")}
		sections, by_label = [], {}
		for line in lines:
			maker = line.get("manufacturer_type") or ""
			entry = {
				"type": line.get("line_id") or "",
				"qty": line.get("qty") or 0,
				"maker": "ilLumenate"
				if maker in ("ILLUMENATE", "ACCESSORY", "")
				else (line.get("manufacturer_name") or "Other"),
				"name": "",
				"code": "",
				"specs": [],
				"notes": ill_print_note(line.get("notes")),
				"status": "",
			}
			if maker == "OTHER":
				entry["name"] = (
					line.get("fixture_model_number") or line.get("manufacturer_name") or "Other manufacturer"
				)
				entry["specs"] = [
					(label, line.get(field))
					for label, field in (
						("Housing", "housing_model_number"),
						("Trim", "trim_info"),
						("Lamp", "lamp_info"),
						("Driver", "driver_model_number"),
						("Dimming", "dimming_protocol"),
						("Voltage", "input_voltage"),
						("Finish", "other_finish"),
					)
					if line.get(field)
				]
				if line.get("watts_each"):
					entry["specs"].append(("Watts", f"{line.watts_each:g} W"))
			else:
				code = (
					line.get("ill_item_code")
					or line.get("accessory_item")
					or line.get("group_part_number")
					or ""
				)
				item = (
					frappe.db.get_value("Item", code, ["item_name", "description"], as_dict=True)
					if code
					else None
				)
				template = (
					line.get("fixture_template")
					or line.get("tape_neon_template")
					or line.get("led_sheet_template")
					or line.get("kit_template")
					or line.get("driver_template")
				)
				entry["name"] = (
					(item and item.item_name)
					or line.get("accessory_item_name")
					or template
					or line.get("product_type")
					or ""
				)
				entry["code"] = code
				if item:
					parsed = ill_print_specs(
						{"description": item.description, "item_name": item.item_name, "item_code": code}
					)
					entry["specs"] = parsed["specs"]
					entry["code"] = parsed["part_number"] or code
				if not any(label == "Length" for label, _value in entry["specs"]) and line.get(
					"manufacturable_length_mm"
				):
					entry["specs"].insert(0, ("Length", _mm(line.manufacturable_length_mm)))
				fed = ids.get(line.get("power_supply_for_line"))
				if fed:
					per = line.get("power_supply_qty_per_build")
					entry["specs"].append(
						("Powers", f"{fed}" + (f" ({per} per build)" if per and per > 1 else ""))
					)
				if line.get("configuration_status") == "Pending" and maker != "ACCESSORY":
					entry["status"] = "To be configured"
			label = (line.get("location") or "").strip()
			key = label.lower()
			if key not in by_label:
				by_label[key] = {"label": label, "lines": []}
				sections.append(by_label[key])
			by_label[key]["lines"].append(entry)
		info["sections"] = sections
	except Exception:
		_log("ilL print: could not read the fixture schedule")
	return info


def ill_print_company(doc=None) -> dict:
	"""Name, address lines, phone, email and website for the document header."""
	info = {"name": "ilLumenate Lighting", "address": [], **COMPANY_FALLBACK}
	try:
		company = (doc.get("company") if doc else None) or frappe.defaults.get_user_default("Company")
		if company:
			info["name"] = company
			values = frappe.db.get_value("Company", company, ["phone_no", "email", "website"], as_dict=True)
			for key, field in (("phone", "phone_no"), ("email", "email"), ("website", "website")):
				if values and values.get(field):
					info[key] = values.get(field)
		address = doc.get("company_address_display") if doc else ""
		if not address and company:
			name = frappe.db.get_value(
				"Dynamic Link",
				{"link_doctype": "Company", "link_name": company, "parenttype": "Address"},
				"parent",
			)
			if name:
				address = _address_text(name)
		info["address"] = _lines(address)
		info["website"] = re.sub(r"^https?://(www\.)?", "", info["website"] or "").rstrip("/")
	except Exception:
		_log("ilL print: could not read company details")
	return info


def _address_text(name) -> str:
	values = frappe.db.get_value(
		"Address", name, ["address_line1", "address_line2", "city", "state", "pincode"], as_dict=True
	)
	if not values:
		return ""
	city = ", ".join(v for v in (values.city, " ".join(v for v in (values.state, values.pincode) if v)) if v)
	return "\n".join(v for v in (values.address_line1, values.address_line2, city) if v)


def _lines(text) -> list:
	"""Address display HTML or text as a list of non-empty lines."""
	return [line.strip() for line in _plain_text(text).split("\n") if line.strip()]


def ill_print_address(display=None, name=None) -> list:
	"""An address as lines, from its display HTML or, failing that, the Address record."""
	try:
		if display:
			return _lines(display)
		if name:
			return _lines(_address_text(name))
	except Exception:
		_log("ilL print: could not read an address")
	return []


def ill_print_project(doc) -> dict:
	"""Project and fixture schedule names for the header.

	Uses the document's own fixture schedule or project, then the linked Sales Order's,
	so invoices and delivery notes show the project too.
	"""
	info = {"project": "", "schedule": "", "schedule_id": ""}
	try:
		schedule = doc.get("ill_fixture_schedule")
		project = doc.get("project")
		if not schedule:
			for item in doc.get("items") or []:
				order = item.get("sales_order") or item.get("against_sales_order")
				if order:
					schedule = frappe.db.get_value("Sales Order", order, "ill_fixture_schedule")
					project = project or frappe.db.get_value("Sales Order", order, "project")
					break
		if schedule:
			values = frappe.db.get_value(
				"ilL-Project-Fixture-Schedule", schedule, ["schedule_name", "ill_project"], as_dict=True
			)
			if values:
				info["schedule_id"] = schedule
				info["schedule"] = values.schedule_name or schedule
				if values.ill_project:
					info["project"] = (
						frappe.db.get_value("ilL-Project", values.ill_project, "project_name") or ""
					)
		if project and not info["project"]:
			info["project"] = frappe.db.get_value("Project", project, "project_name") or project
	except Exception:
		_log("ilL print: could not read the project")
	return info


def ill_print_person(user) -> str:
	"""A user's full name, for "Prepared by"; "" for Administrator, Guest and integrations."""
	try:
		if not user or user in ("Administrator", "Guest") or "integration@" in user or "worker@" in user:
			return ""
		return frappe.db.get_value("User", user, "full_name") or ""
	except Exception:
		return ""


def ill_print_terms(doc=None, kind="sales") -> str:
	"""The terms to print: the document's own, else the default ilL record for ``kind``."""
	try:
		own = doc.get("terms") if doc else ""
		if own and _plain_text(own).strip():
			text = own
		else:
			name = TERMS.get(kind)
			if not name or not frappe.db.exists("Terms and Conditions", name):
				return ""
			text = frappe.db.get_value("Terms and Conditions", name, "terms") or ""
		return sanitize_html(text)
	except Exception:
		_log("ilL print: could not read the terms")
		return ""


def ill_print_terms_columns(doc=None, kind="sales") -> list:
	"""The terms split into two balanced columns of whole paragraphs, for a table layout.

	wkhtmltopdf's WebKit ignores CSS columns. Terms that are not a run of paragraphs come
	back whole in the first column.
	"""
	text = ill_print_terms(doc, kind)
	parts = [p for p in re.split(r"(?<=</p>)", text) if p.strip()]
	if len(parts) < 2:
		return [text, ""]
	total = sum(len(_plain_text(p)) for p in parts)
	running, split = 0, len(parts)
	for index, part in enumerate(parts):
		running += len(_plain_text(part))
		if running >= total / 2:
			split = index + 1
			break
	return ["".join(parts[:split]), "".join(parts[split:])]


def ill_print_references(doc, *fields) -> list:
	"""Distinct values of the given item fields, in line order (e.g. linked orders)."""
	values = []
	try:
		for item in doc.get("items") or []:
			for field in fields:
				value = item.get(field)
				if value and value not in values:
					values.append(value)
	except Exception:
		pass
	return values


def ill_print_supplier_parts(doc) -> dict:
	"""``{item_code: {"part_no", "description"}}`` from each Item's supplier rows."""
	parts = {}
	try:
		codes = list({item.get("item_code") for item in doc.get("items") or [] if item.get("item_code")})
		supplier = doc.get("supplier")
		if not codes or not supplier:
			return parts
		fields = ["parent", "supplier_part_no"]
		if frappe.get_meta("Item Supplier").has_field("custom_supplier_description"):
			fields.append("custom_supplier_description")
		for row in frappe.get_all(
			"Item Supplier", filters={"parent": ["in", codes], "supplier": supplier}, fields=fields
		):
			parts[row.parent] = {
				"part_no": row.get("supplier_part_no") or "",
				"description": row.get("custom_supplier_description") or "",
			}
	except Exception:
		_log("ilL print: could not read supplier part numbers")
	return parts


def ill_print_contact(name) -> dict:
	"""A contact's name, email and phone, for supplier and party blocks."""
	try:
		if name:
			values = frappe.db.get_value(
				"Contact", name, ["first_name", "last_name", "email_id", "phone", "mobile_no"], as_dict=True
			)
			if values:
				return {
					"name": " ".join(v for v in (values.first_name, values.last_name) if v),
					"email": values.email_id or "",
					"phone": values.phone or values.mobile_no or "",
				}
	except Exception:
		_log("ilL print: could not read a contact")
	return {"name": "", "email": "", "phone": ""}
