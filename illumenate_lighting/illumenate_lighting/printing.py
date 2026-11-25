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


# Brand fonts for print (the Fixture Schedule): (family, weight, file in public/fonts/print/).
# Each face is its own family: wkhtmltopdf's WebKit does not pick between weights of one
# @font-face family (it set all body text in Poppins Medium), so the stylesheet names the
# exact face it wants and keeps font-weight normal.
PRINT_FONTS = (
	("ilL Poppins", 400, "Poppins-Regular.ttf"),
	("ilL Poppins Medium", 400, "Poppins-Medium.ttf"),
	("ilL Poppins SemiBold", 400, "Poppins-SemiBold.ttf"),
	("ilL Manrope", 400, "Manrope-Bold.ttf"),
)


def ill_print_fonts() -> list:
	"""``[(family, weight, url)]`` for the print @font-face rules, or [] when they can't load.

	wkhtmltopdf needs absolute URLs, and Frappe refuses the whole PDF when any linked
	resource fails to load ("broken image links"). So a font is only linked when its file is
	in the installed app (and therefore served under /assets); otherwise the print falls
	back to Helvetica rather than failing.
	"""
	import os

	fonts = []
	try:
		base = frappe.utils.get_url().rstrip("/")
		folder = frappe.get_app_path("illumenate_lighting", "public", "fonts", "print")
		for family, weight, filename in PRINT_FONTS:
			if os.path.isfile(os.path.join(folder, filename)):
				fonts.append((family, weight, f"{base}/assets/illumenate_lighting/fonts/print/{filename}"))
	except Exception:
		_log("ilL print: could not locate the print fonts")
		return []
	return fonts


def ill_print_item_images(items) -> dict:
	"""Look up Item images in one query for quotation rows without a saved image."""
	try:
		codes = {
			item.get("item_code")
			for item in items or []
			if item.get("item_code") and not (item.get("image") or "").strip()
		}
		if not codes:
			return {}
		rows = frappe.get_all("Item", filters={"name": ["in", sorted(codes)]}, fields=["name", "image"])
		return {row.name: row.image.strip() for row in rows if row.image}
	except Exception:
		_log("ilL print: could not read Item images")
		return {}


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


def ill_print_phone(text) -> str:
	"""A bare North American phone number as (425) 381-2447; any other text unchanged."""
	value = str(text or "").strip()
	if not value or not re.fullmatch(r"[+\d\s().-]{10,18}", value):
		return value
	digits = re.sub(r"\D", "", value)
	if len(digits) == 11 and digits.startswith("1"):
		digits = digits[1:]
	if len(digits) != 10:
		return value
	return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"


def ill_print_qty_parts(qty, uom=None) -> dict:
	"""``{"number", "unit", "inline"}``: short units (in, ea, ft) print beside the number,
	longer ones ("6.56ft Piece", "Pack of 6") on their own line beneath it."""
	full = ill_print_qty(qty, uom)
	number = ill_print_qty(qty)
	unit = full[len(number) :].strip()
	return {"number": number, "unit": unit, "inline": len(unit) <= 4}


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


# Where a line's section / fixture type / notes come from when its own row has none:
# child DocType -> (link field on the row, the source child DocType it points at).
_LINE_SOURCES = {
	"Delivery Note Item": ("so_detail", "Sales Order Item"),
	"Sales Invoice Item": ("so_detail", "Sales Order Item"),
	"Packing Slip Item": ("dn_detail", "Delivery Note Item"),
	"Pick List Item": ("sales_order_item", "Sales Order Item"),
	"Material Request Item": ("sales_order_item", "Sales Order Item"),
	"Purchase Order Item": ("sales_order_item", "Sales Order Item"),
	"Purchase Receipt Item": ("purchase_order_item", "Purchase Order Item"),
	"Purchase Invoice Item": ("po_detail", "Purchase Order Item"),
}
_LINE_FIELDS = ("ill_section_label", "ill_fixture_type", "additional_notes")


def _source_lines(doctype, names, depth) -> dict:
	"""``{row name: {section, type, notes}}`` for rows of a source child DocType, following
	that DocType's own source link while a field is still missing (at most ``depth`` hops)."""
	found = {}
	if not names or depth <= 0:
		return found
	meta = frappe.get_meta(doctype)
	fields = ["name", *[f for f in _LINE_FIELDS if meta.has_field(f)]]
	link = _LINE_SOURCES.get(doctype)
	if link and meta.has_field(link[0]):
		fields.append(link[0])
	rows = frappe.get_all(doctype, filters={"name": ["in", list(names)]}, fields=fields)
	deeper = {}
	if link:
		wanted = {r.get(link[0]) for r in rows if r.get(link[0])}
		deeper = _source_lines(link[1], wanted, depth - 1) if wanted else {}
	for r in rows:
		parent = deeper.get(r.get(link[0])) if link else None
		parent = parent or {}
		found[r.name] = {
			"section": r.get("ill_section_label") or parent.get("section") or "",
			"type": r.get("ill_fixture_type") or parent.get("type") or "",
			"notes": r.get("additional_notes") or parent.get("notes") or "",
		}
	return found


# Purchase Order and Material Request prints show repeated rows as one line: a configured
# fixture breaks into parts, so the same part repeats once per fixture. Rows merge when
# they match on these fields and on the line's fixture type and notes.
_MERGE_KEY_FIELDS = (
	"item_code",
	"uom",
	"rate",
	"schedule_date",
	"supplier_part_no",
	"ill_supplier_description",
	"warehouse",
	"from_warehouse",
	"bom_no",
)
# Added up on a merged line. Stock on hand (actual_qty) is per item and warehouse, so the
# merged rows already agree on it and it is not summed.
_MERGE_SUM_FIELDS = (
	"qty",
	"stock_qty",
	"amount",
	"base_amount",
	"net_amount",
	"base_net_amount",
	"ordered_qty",
	"received_qty",
	"returned_qty",
	"billed_amt",
)


class _MergedRow:
	"""Several rows printed as one: reads like a Document row (attribute access and .get())."""

	def __init__(self, values):
		self._values = values

	def __getattr__(self, key):
		if key.startswith("_"):
			raise AttributeError(key)
		return self._values.get(key)

	def get(self, key, default=None):
		value = self._values.get(key)
		return default if value is None else value


def _row_values(item) -> dict:
	as_dict = getattr(item, "as_dict", None)
	if callable(as_dict):
		return dict(as_dict())
	if isinstance(item, dict):
		return dict(item)
	return dict(vars(item))


def _merge_key_value(value):
	if isinstance(value, (int, float)) and not isinstance(value, bool):
		return round(float(value), 6)
	return str(value).strip() if value is not None else ""


def _orders(rows) -> list:
	orders = []
	for row in rows:
		order = row.get("sales_order")
		if order and order not in orders:
			orders.append(order)
	return orders


def _merge_same_lines(label, lines) -> list:
	"""One line per repeated row group (see _MERGE_KEY_FIELDS), at its first row's position.

	Rows without an item code and rows with a page break are left alone, so a break staff
	placed stays where it was. Section headers are worked out again for the merged lines.
	"""
	merged, groups = [], {}
	for entry in lines:
		item = entry["item"]
		if entry["page_break"] or not item.get("item_code"):
			merged.append(entry)
			continue
		key = (
			entry["type"],
			entry["notes"],
			*(_merge_key_value(item.get(field)) for field in _MERGE_KEY_FIELDS),
		)
		group = groups.get(key)
		if group is None:
			groups[key] = group = dict(entry, rows=[])
			merged.append(group)
		group["rows"].append(item)
	for index, entry in enumerate(merged):
		rows = entry.pop("rows", None)
		if rows and len(rows) > 1:
			values = _row_values(rows[0])
			for field in _MERGE_SUM_FIELDS:
				if any(row.get(field) is not None for row in rows):
					values[field] = round(sum(float(row.get(field) or 0) for row in rows), 9)
			entry["orders"] = _orders(rows)
			values["sales_order"] = ", ".join(entry["orders"]) or values.get("sales_order")
			values["merged_rows"] = len(rows)
			entry["item"] = _MergedRow(values)
		previous = merged[index - 1] if index else None
		entry["header"] = (
			label
			if previous is None
			else (f"{label} (continued)" if previous["page_break"] and label else "")
		)
	return merged


def ill_print_sections(items, follow_links=False, merge_same=False) -> list:
	"""Group lines into sections (rooms / areas) in document order.

	A row with a section label, no item code and zero quantity is a section header; the
	rows after it inherit its label until the next one. Labels match case-insensitively.
	Each line's section, fixture type and additional notes come from its own row, or with
	``follow_links`` from the line it was made from (packing slip -> delivery note,
	receipt -> purchase order -> sales order, ...). With ``merge_same``, repeated rows in a
	section print as one line with their quantities added up (``_merge_same_lines``).

	Returns ``[{"label", "lines": [{"item", "type", "notes", "header", "page_break",
	"orders"}], "items", "subtotal", "list_subtotal"}]``; everything lands in one unlabelled
	section when nothing is labelled. ``header`` is the section label on a section's first
	line and "<label> (continued)" on the line after a page break; ``page_break`` is the
	line's own Page Break check; ``orders`` lists the line's sales orders. ``items`` keeps
	every row, merged or not.
	"""
	items = list(items or [])
	sources = {}
	if follow_links:
		try:
			by_source = {}
			for item in items:
				link = _LINE_SOURCES.get(item.get("doctype") or "")
				if link and item.get(link[0]):
					by_source.setdefault(link[1], set()).add(item.get(link[0]))
			for doctype, names in by_source.items():
				resolved = _source_lines(doctype, names, depth=2)
				for item in items:
					link = _LINE_SOURCES.get(item.get("doctype") or "")
					if link and link[1] == doctype and item.get(link[0]) in resolved:
						sources[id(item)] = resolved[item.get(link[0])]
		except Exception:
			_log("ilL print: could not read the source lines")

	def empty(label):
		return {"label": label, "lines": [], "items": [], "subtotal": 0.0, "list_subtotal": 0.0}

	sections, by_label, current = [], {}, ""
	try:
		for item in items:
			source = sources.get(id(item), {})
			label = (
				item.get("ill_section_label")
				or item.get("custom_ill_section_label")
				or source.get("section")
				or ""
			).strip()
			if label and not item.get("item_code") and not item.get("qty"):
				current = label
				if label.lower() not in by_label:
					by_label[label.lower()] = empty(label)
					sections.append(by_label[label.lower()])
				continue
			effective = label or current
			key = effective.lower()
			if key not in by_label:
				by_label[key] = empty(effective)
				sections.append(by_label[key])
			section = by_label[key]
			section["items"].append(item)
			previous = section["lines"][-1] if section["lines"] else None
			section["lines"].append(
				{
					"item": item,
					"type": (item.get("ill_fixture_type") or source.get("type") or "").strip(),
					"notes": ill_print_note(item.get("additional_notes") or source.get("notes")),
					# The section header prints on its first line, and again after a page break.
					"header": section["label"]
					if previous is None
					else (
						f"{section['label']} (continued)"
						if previous["page_break"] and section["label"]
						else ""
					),
					# ERPNext's per-line "Page Break" check: start a new page after this line.
					"page_break": bool(item.get("page_break")),
					"orders": _orders([item]),
				}
			)
			section["subtotal"] += float(item.get("amount") or 0)
			section["list_subtotal"] += ill_print_msrp(item) * float(item.get("qty") or 0)
	except Exception:
		_log("ilL print: could not group lines into sections")
		fallback = empty("")
		fallback["items"] = items
		fallback["lines"] = [
			{
				"item": i,
				"type": "",
				"notes": "",
				"header": "",
				"page_break": bool(i.get("page_break")),
				"orders": [i.get("sales_order")] if i.get("sales_order") else [],
			}
			for i in items
		]
		return [fallback]
	if merge_same:
		try:
			for section in sections:
				section["lines"] = _merge_same_lines(section["label"], section["lines"])
		except Exception:
			# Printing every row is better than not printing: keep the unmerged lines.
			_log("ilL print: could not merge repeated lines")
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
				"line_name": line.get("name") or "",
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
			entry["header"] = "" if by_label[key]["lines"] else label
			entry["page_break"] = False
			by_label[key]["lines"].append(entry)
		info["sections"] = sections
	except Exception:
		_log("ilL print: could not read the fixture schedule")
	return info


def ill_print_schedule_prices(doc) -> dict:
	"""MSRP for each schedule line, for the ``ilL Fixture Schedule - MSRP`` format (owner, 2026-11-23).

	``{"lines": {line name: {"unit", "amount"}}, "total", "unpriced", "allowed"}``. Prices are
	the PDF export's (``exports._get_schedule_data``): the latest MSRP snapshot of each build, a
	group's current estimate, or an accessory's price. Nothing is returned to a user without
	pricing permission, so a Desk print never shows prices to someone who cannot see them.
	"""
	info = {"lines": {}, "total": 0.0, "unpriced": 0, "allowed": False}
	try:
		from illumenate_lighting.illumenate_lighting.api import exports

		if not exports._check_pricing_permission():
			return info
		info["allowed"] = True
		data = exports._get_schedule_data(doc.name, include_pricing=True)
		for line in data.get("lines") or []:
			unit = line.get("unit_price")
			if unit is None:
				info["unpriced"] += 1
				continue
			amount = line.get("line_total")
			amount = float(amount if amount is not None else unit * (line.get("qty") or 1))
			price = {"unit": float(unit), "amount": amount}
			# A fixture's included power supply is priced on its own sub-line, as in the old export.
			if line.get("driver_unit_price"):
				price["driver_unit"] = float(line["driver_unit_price"])
				price["driver_amount"] = float(line.get("driver_line_total") or 0)
			info["lines"][line.get("line_name")] = price
			info["total"] += amount + price.get("driver_amount", 0)
	except Exception:
		_log("ilL print: could not price the fixture schedule")
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


def ill_print_tracking(delivery_note) -> dict:
	"""{"carrier", "numbers"} for the Delivery Note and Packing List prints.

	Every tracking number on the note's submitted, non-voided Shipments (shipping plan
	phase 3), else the manual carrier and tracking fields as before.
	"""
	info = {"carrier": "", "numbers": ""}
	try:
		if isinstance(delivery_note, str):
			name = delivery_note
			dn = (
				frappe.db.get_value(
					"Delivery Note",
					name,
					["ill_carrier", "transporter_name", "ill_tracking_number", "vehicle_no"],
					as_dict=True,
				)
				or {}
			)
		else:
			dn = delivery_note or {}
			name = dn.get("name")
		info["carrier"] = dn.get("ill_carrier") or dn.get("transporter_name") or ""
		info["numbers"] = dn.get("ill_tracking_number") or dn.get("vehicle_no") or ""
	except Exception:
		frappe.log_error(title="ilL print: tracking lookup failed")
		return info
	try:
		from illumenate_lighting.illumenate_lighting.portal.shipment_tracking import packages_by_delivery_note

		packages = packages_by_delivery_note([name]).get(name) if name else None
		if packages:
			info["carrier"] = packages[0].get("carrier") or info["carrier"]
			info["numbers"] = ", ".join(p["number"] for p in packages if p.get("number"))
	except Exception:
		frappe.log_error(title="ilL print: shipment tracking lookup failed")
	return info


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
		# An RFQ prints once per supplier; ERPNext sets ``vendor`` to the one being printed.
		supplier = doc.get("supplier") or doc.get("vendor")
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
