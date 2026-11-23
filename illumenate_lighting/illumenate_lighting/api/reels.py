"""Reel tracking for LED tape and neon: the count kit (reel PDR, phase R1).

* One ilL-Reel per physical reel, with a permanent ID (``R-00001``) printed as Code 128.
  Tags are printed in a block before the count as "Tag only" reels; counting a tag fills
  in its item, length and shelf.
* Lengths change only through ilL-Reel-Movement rows (append-only). ERPNext keeps the item
  totals; ``count_summary`` compares the two, and ``make_stock_reconciliation`` drafts a
  Stock Reconciliation that sets each counted item to its reel total.
* Scans are routed by what they contain (``route_scan``), not by which box has focus.

Pure functions come first (no ``frappe`` calls), then database code, then endpoints.
Cutting, receiving and the reel planner (R2, R3) build on this later.
"""

import re
from urllib.parse import unquote

import frappe

REEL = "ilL-Reel"
MOVEMENT = "ilL-Reel-Movement"
LOCATION = "ilL-Reel-Location"
SETTINGS = "ilL-Production-Settings"

COUNT_ROLES = {"System Manager", "Manufacturing Manager", "Manufacturing User", "Stock Manager", "Stock User"}
RECONCILE_ROLES = {"System Manager", "Stock Manager"}
ACTIVE = ("Sealed", "Open", "Remnant", "In use")
UOM_MM = {"Millimeter": 1, "Meter": 1000, "Foot": 304.8, "Feet": 304.8, "Inch": 25.4}
MAX_TAGS = 500
DEFAULTS_MM = {"scrap": 610, "min_useful": 1219, "remnant": 3048}

REEL_ID = re.compile(r"^R-\d{5,}$", re.IGNORECASE)
LOCATION_CODE = re.compile(r"^LOC-(.+)$", re.IGNORECASE)
WORK_ORDER_URL = re.compile(r"/(?:app|desk)/work-order/([^/?#\s]+)", re.IGNORECASE)


# ---------------------------------------------------------------- pure helpers


def feet_inches(mm):
	"""Same format as ``labels.feet_inches`` (20' 6")."""
	inches = round(float(mm or 0) / 25.4, 1)
	feet, rest = divmod(inches, 12)
	rest = round(rest, 1)
	if rest >= 12:
		feet, rest = feet + 1, 0
	text = f"{int(feet)}'" if feet else ""
	if rest or not feet:
		text += (" " if text else "") + f'{rest:g}"'
	return text


def route_scan(text):
	"""What a scanned value is: ``{"kind": reel|location|work_order|item|empty, "value"}``."""
	value = (text or "").strip()
	if not value:
		return {"kind": "empty", "value": ""}
	if REEL_ID.match(value):
		return {"kind": "reel", "value": value.upper()}
	match = LOCATION_CODE.match(value)
	if match:
		return {"kind": "location", "value": match.group(1).strip()}
	match = WORK_ORDER_URL.search(value)
	if match:
		return {"kind": "work_order", "value": unquote(match.group(1))}
	return {"kind": "item", "value": value}


def item_rules(item):
	"""An item's reel numbers (mm), with the agreed defaults where blank."""
	item = item or {}
	return {
		"standard": float(item.get("ill_standard_reel_length_mm") or 0),
		"scrap": float(item.get("ill_reel_scrap_line_mm") or DEFAULTS_MM["scrap"]),
		"min_useful": float(item.get("ill_reel_min_useful_mm") or DEFAULTS_MM["min_useful"]),
		"remnant": float(item.get("ill_reel_remnant_line_mm") or DEFAULTS_MM["remnant"]),
		"g_per_m": float(item.get("ill_reel_weight_g_per_m") or 0),
		"core_g": float(item.get("ill_reel_core_weight_g") or 0),
	}


def classify(length_mm, item, *, sealed=False):
	"""Status for a reel with ``length_mm`` left: Sealed, Open, Remnant or Empty."""
	length = float(length_mm or 0)
	if length <= 0:
		return "Empty"
	if sealed:
		return "Sealed"
	return "Remnant" if length < item_rules(item)["remnant"] else "Open"


def under_scrap_line(length_mm, item):
	length = float(length_mm or 0)
	return 0 < length < item_rules(item)["scrap"]


def weight_to_length(weight_g, item):
	"""Length (mm) of tape on a reel from its weight, using the item's weight per metre."""
	rules = item_rules(item)
	if rules["g_per_m"] <= 0:
		raise ValueError("Set the item's weight per metre before weighing its reels")
	net = float(weight_g or 0) - rules["core_g"]
	if net <= 0:
		raise ValueError("That weight is no more than the empty reel")
	return round(net / rules["g_per_m"] * 1000, 1)


def count_length(method, item, length_mm=None, weight_g=None):
	"""Length from a count: Full (the standard reel), Weighed, or Measured (typed)."""
	if method == "Full":
		standard = item_rules(item)["standard"]
		if standard <= 0:
			raise ValueError("Set the item's standard reel length to count reels as Full")
		return standard
	if method == "Weighed":
		return weight_to_length(weight_g, item)
	length = float(length_mm or 0)
	if length <= 0:
		raise ValueError("Enter the length on the reel")
	return length


def stock_qty(length_mm, uom):
	"""Length in the item's stock UOM (tape is stocked in Foot)."""
	factor = UOM_MM.get(uom)
	if not factor:
		raise ValueError(f"Reel-tracked items need a length stock UOM, not {uom}")
	return float(length_mm or 0) / factor


def summarize(reels, bins, items):
	"""Count summary rows per item and warehouse: reels, feet counted, ERPNext qty, difference.

	``reels``: rows with item_code, warehouse, current_length_mm. ``bins``: {(item, wh): qty}.
	``items``: {item_code: {stock_uom, item_name}}.
	"""
	groups = {}
	for reel in reels:
		key = (reel["item_code"], reel["warehouse"])
		group = groups.setdefault(
			key, {"item_code": key[0], "warehouse": key[1], "reels": 0, "length_mm": 0.0}
		)
		group["reels"] += 1
		group["length_mm"] += float(reel.get("current_length_mm") or 0)
	rows = []
	for (item_code, warehouse), group in sorted(
		groups.items(), key=lambda kv: (kv[0][0] or "", kv[0][1] or "")
	):
		item = items.get(item_code) or {}
		uom = item.get("stock_uom") or "Foot"
		try:
			counted = round(stock_qty(group["length_mm"], uom), 3)
		except ValueError:
			counted = None
		erp = round(float(bins.get((item_code, warehouse)) or 0), 3)
		rows.append(
			{
				**group,
				"item_name": item.get("item_name") or "",
				"stock_uom": uom,
				"length": feet_inches(group["length_mm"]),
				"counted_qty": counted,
				"erpnext_qty": erp,
				"difference": None if counted is None else round(counted - erp, 3),
			}
		)
	return rows


# ---------------------------------------------------------------- settings, roles


def reels_enabled():
	try:
		return frappe.db.get_single_value(SETTINGS, "reels_enabled") in (1, "1", True)
	except Exception:
		return False


def _has(roles):
	return bool(set(frappe.get_roles()) & roles)


def _require(roles, what):
	if not _has(roles):
		frappe.throw(f"{what} needs a stock or manufacturing role.", frappe.PermissionError)


def _require_enabled():
	if not reels_enabled():
		frappe.throw("Turn on Reels in ilL-Production-Settings first.")


ITEM_FIELDS = [
	"name",
	"item_name",
	"stock_uom",
	"ill_reel_tracked",
	"ill_standard_reel_length_mm",
	"ill_reel_scrap_line_mm",
	"ill_reel_min_useful_mm",
	"ill_reel_remnant_line_mm",
	"ill_reel_weight_g_per_m",
	"ill_reel_core_weight_g",
]


def _item(item_code):
	item = frappe.db.get_value("Item", item_code, ITEM_FIELDS, as_dict=True)
	if not item:
		frappe.throw(f"Item {item_code} not found.")
	if not item.ill_reel_tracked:
		frappe.throw(f"{item_code} is not reel tracked. Tick Reel Tracked on the Item first.")
	return item


# ---------------------------------------------------------------- controller and labels


def validate_reel(doc):
	"""ilL-Reel.validate: keep the readable length in step with the ledger value."""
	doc.length_display = (
		feet_inches(doc.current_length_mm) if doc.item_code and doc.status != "Tag only" else ""
	)


def label_context(doctype, name, layout):
	"""Frozen values for reel, tag and shelf labels (``labels.queue_documents``)."""
	if doctype == LOCATION:
		loc = frappe.db.get_value(LOCATION, name, ["name", "warehouse", "description"], as_dict=True) or {}
		return {
			"location_code": loc.get("name") or name,
			"barcode": f"LOC-{loc.get('name') or name}",
			"warehouse": loc.get("warehouse") or "",
			"description": loc.get("description") or "",
		}
	reel = (
		frappe.db.get_value(
			REEL,
			name,
			[
				"name",
				"item_code",
				"item_name",
				"starting_length_mm",
				"received_on",
				"counted_on",
				"supplier_lot",
				"location",
			],
			as_dict=True,
		)
		or {}
	)
	context = {"reel_id": reel.get("name") or name, "barcode": reel.get("name") or name}
	if layout == "reel_tag":
		return context
	from illumenate_lighting.illumenate_lighting.api.labels import fmt_date

	context.update(
		{
			"item_code": reel.get("item_code") or "",
			"item_name": reel.get("item_name") or "",
			"starting_length": feet_inches(reel.starting_length_mm) if reel.get("starting_length_mm") else "",
			"received": fmt_date(reel.get("received_on") or reel.get("counted_on")),
			"lot": reel.get("supplier_lot") or "",
			"shelf": reel.get("location") or "",
		}
	)
	return context


# ---------------------------------------------------------------- ledger


def add_movement(reel, movement_type, before_mm, after_mm, **extra):
	frappe.get_doc(
		{
			"doctype": MOVEMENT,
			"reel": reel.name,
			"item_code": reel.item_code,
			"warehouse": reel.warehouse,
			"location": reel.location,
			"movement_type": movement_type,
			"before_mm": before_mm,
			"after_mm": after_mm,
			"length_mm": round(float(after_mm or 0) - float(before_mm or 0), 3),
			"posting_status": "Not needed",
			"at": frappe.utils.now_datetime(),
			"user": frappe.session.user,
			**extra,
		}
	).insert(ignore_permissions=True)


def _reel_summary(reel):
	return {
		"reel": reel.name,
		"status": reel.status,
		"item_code": reel.item_code,
		"item_name": reel.item_name,
		"warehouse": reel.warehouse,
		"location": reel.location,
		"length_mm": reel.current_length_mm,
		"length": reel.length_display,
		"counted_on": str(reel.counted_on) if reel.counted_on else None,
		"supplier_lot": reel.supplier_lot,
	}


# ---------------------------------------------------------------- endpoints


@frappe.whitelist()
def get_count_setup():
	"""Everything the Reel count screen caches: items, shelves, default warehouse."""
	result = {
		"enabled": reels_enabled(),
		"can_count": _has(COUNT_ROLES),
		"can_reconcile": _has(RECONCILE_ROLES),
	}
	if not result["enabled"] or not result["can_count"]:
		return result
	items = frappe.get_all(
		"Item", filters={"ill_reel_tracked": 1, "disabled": 0}, fields=ITEM_FIELDS, order_by="name asc"
	)
	result["items"] = [
		{
			"item_code": item.name,
			"item_name": item.item_name,
			"stock_uom": item.stock_uom,
			"standard_mm": item.ill_standard_reel_length_mm or 0,
			"standard": feet_inches(item.ill_standard_reel_length_mm)
			if item.ill_standard_reel_length_mm
			else "",
			"scrap_mm": item_rules(item)["scrap"],
			"can_weigh": bool(item.ill_reel_weight_g_per_m),
		}
		for item in items
	]
	result["locations"] = frappe.get_all(
		LOCATION, filters={"enabled": 1}, fields=["name", "warehouse", "description"], order_by="name asc"
	)
	result["warehouse"] = frappe.db.get_single_value(SETTINGS, "reels_default_warehouse")
	result["tags_left"] = frappe.db.count(REEL, {"status": "Tag only"})
	return result


@frappe.whitelist()
def lookup(code):
	"""Resolve a scan: a reel (with its record), a shelf, a work order, or an item."""
	_require(COUNT_ROLES, "Reel scanning")
	route = route_scan(code)
	kind, value = route["kind"], route["value"]
	if kind == "reel":
		if not frappe.db.exists(REEL, value):
			return {
				"kind": "unknown",
				"value": value,
				"message": f"No reel {value}. Was its tag printed here?",
			}
		return {"kind": "reel", "value": value, "reel": _reel_summary(frappe.get_doc(REEL, value))}
	if kind == "location":
		if not frappe.db.exists(LOCATION, value):
			return {
				"kind": "unknown",
				"value": value,
				"message": f"No shelf {value}. Add it under ilL-Reel-Location.",
			}
		return {
			"kind": "location",
			"value": value,
			"warehouse": frappe.db.get_value(LOCATION, value, "warehouse"),
		}
	if kind == "item":
		item_code = (
			value
			if frappe.db.exists("Item", value)
			else frappe.db.get_value("Item Barcode", {"barcode": value}, "parent")
		)
		if item_code and frappe.db.get_value("Item", item_code, "ill_reel_tracked"):
			return {"kind": "item", "value": item_code}
		return {
			"kind": "unknown",
			"value": value,
			"message": f"{value} is not a reel-tracked item, reel or shelf.",
		}
	return route


@frappe.whitelist(methods=["POST"])
def count_reel(
	reel,
	item_code,
	method="Measured",
	length_mm=None,
	weight_g=None,
	location=None,
	warehouse=None,
	scrap=0,
	supplier_lot=None,
):
	"""Count one reel: what it is, how much is on it and where it lives.

	A Tag only reel becomes a counted reel; a counted one is recounted. Either way the change
	is a Count movement. ``scrap=1`` writes off a piece under the scrap line instead.
	"""
	_require_enabled()
	_require(COUNT_ROLES, "Counting reels")
	frappe.db.get_value(REEL, reel, "name", for_update=True)  # one scan at a time per reel
	doc = frappe.get_doc(REEL, reel)
	if doc.status in ("In use",):
		frappe.throw(f"{reel} is out for a work order. Return it before recounting.")
	item = _item(item_code)
	try:
		length = count_length(method, item, length_mm, weight_g)
	except ValueError as error:
		frappe.throw(str(error))
	before = float(doc.current_length_mm or 0) if doc.status != "Tag only" else 0.0
	if location:
		doc.location = location
		warehouse = warehouse or frappe.db.get_value(LOCATION, location, "warehouse")
	doc.warehouse = (
		warehouse or doc.warehouse or frappe.db.get_single_value(SETTINGS, "reels_default_warehouse")
	)
	if not doc.warehouse:
		frappe.throw("Set the Reel Warehouse in ilL-Production-Settings, or a warehouse on the shelf.")
	doc.item_code = item.name
	if supplier_lot:
		doc.supplier_lot = supplier_lot
	after = 0.0 if int(scrap or 0) else round(length, 1)
	if not doc.starting_length_mm or doc.status == "Tag only":
		doc.starting_length_mm = round(length, 1)
	doc.current_length_mm = after
	doc.status = "Scrapped" if int(scrap or 0) else classify(after, item, sealed=method == "Full")
	doc.counted_on = frappe.utils.nowdate()
	doc.counted_by = frappe.session.user
	doc.count_method = method
	doc.save(ignore_permissions=True)
	reason = f"Counted ({method.lower()})"
	if int(scrap or 0):
		reason = f"Counted at {feet_inches(length)}, under the scrap line: scrapped"
	add_movement(doc, "Count", before, after, reason=reason)
	return {**_reel_summary(doc), "under_scrap_line": under_scrap_line(after, item)}


@frappe.whitelist(methods=["POST"])
def set_location(reel, location):
	"""Put-away: the reel now lives on this shelf."""
	_require(COUNT_ROLES, "Moving reels")
	doc = frappe.get_doc(REEL, reel)
	if not frappe.db.exists(LOCATION, location):
		frappe.throw(f"No shelf {location}.")
	doc.location = location
	doc.warehouse = frappe.db.get_value(LOCATION, location, "warehouse") or doc.warehouse
	doc.save(ignore_permissions=True)
	add_movement(doc, "Location", doc.current_length_mm, doc.current_length_mm, reason=f"Moved to {location}")
	return _reel_summary(doc)


@frappe.whitelist(methods=["POST"])
def print_tags(count):
	"""Make ``count`` Tag only reels and queue their ID tags on the 1.5 x 2.5 roll."""
	_require_enabled()
	_require(COUNT_ROLES, "Printing reel tags")
	count = int(count or 0)
	if not 1 <= count <= MAX_TAGS:
		frappe.throw(f"Print between 1 and {MAX_TAGS} tags at a time.")
	from illumenate_lighting.illumenate_lighting.api import labels

	names = [
		frappe.get_doc({"doctype": REEL, "status": "Tag only"}).insert(ignore_permissions=True).name
		for _ in range(count)
	]
	queued = labels.queue_documents(REEL, names, "Reel ID tag")
	return {"first": names[0], "last": names[-1], "queued": queued}


@frappe.whitelist(methods=["POST"])
def print_reel_labels(reels):
	"""Queue full reel labels (item, starting length, lot, shelf) for counted reels."""
	_require(COUNT_ROLES, "Printing reel labels")
	from illumenate_lighting.illumenate_lighting.api import labels

	names = [
		name
		for name in labels._as_list(reels)
		if frappe.db.get_value(REEL, name, "status") not in (None, "Tag only")
	]
	return {"queued": labels.queue_documents(REEL, names, "Reel", requeue_printed=True)}


@frappe.whitelist(methods=["POST"])
def create_locations(codes, warehouse=None):
	"""Add shelves from a list like "A1 A2 B1" (commas, spaces or new lines) and queue their labels."""
	_require(COUNT_ROLES, "Adding shelves")
	from illumenate_lighting.illumenate_lighting.api import labels

	made = []
	for code in re.split(r"[\s,]+", codes or ""):
		code = code.strip().upper()
		if not code or frappe.db.exists(LOCATION, code):
			continue
		frappe.get_doc(
			{"doctype": LOCATION, "location_code": code, "warehouse": warehouse, "enabled": 1}
		).insert(ignore_permissions=True)
		made.append(code)
	queued = labels.queue_documents(LOCATION, made, "Shelf") if made else 0
	return {"created": made, "queued": queued}


def _summary_rows(warehouse=None):
	filters = {"status": ["in", list(ACTIVE)]}
	if warehouse:
		filters["warehouse"] = warehouse
	reels = frappe.get_all(
		REEL, filters=filters, fields=["item_code", "warehouse", "current_length_mm"], limit_page_length=0
	)
	item_codes = sorted({r.item_code for r in reels if r.item_code})
	items = {
		row.name: row
		for row in frappe.get_all(
			"Item", filters={"name": ["in", item_codes or [""]]}, fields=["name", "item_name", "stock_uom"]
		)
	}
	bins = {}
	for row in frappe.get_all(
		"Bin",
		filters={"item_code": ["in", item_codes or [""]], **({"warehouse": warehouse} if warehouse else {})},
		fields=["item_code", "warehouse", "actual_qty", "valuation_rate"],
	):
		bins[(row.item_code, row.warehouse)] = row.actual_qty
	return summarize([dict(r) for r in reels], bins, {k: dict(v) for k, v in items.items()}), items


@frappe.whitelist()
def count_summary(warehouse=None):
	"""Per item and warehouse: reels, feet counted, ERPNext quantity and the difference."""
	_require(COUNT_ROLES, "The count summary")
	rows, _items = _summary_rows(warehouse)
	tracked = frappe.get_all("Item", filters={"ill_reel_tracked": 1, "disabled": 0}, pluck="name")
	counted = {row["item_code"] for row in rows}
	return {
		"rows": rows,
		"not_counted": sorted(set(tracked) - counted),
		"tags_left": frappe.db.count(REEL, {"status": "Tag only"}),
		"missing": frappe.db.count(REEL, {"status": "Missing"}),
		"can_reconcile": _has(RECONCILE_ROLES),
	}


@frappe.whitelist(methods=["POST"])
def make_stock_reconciliation(warehouse, items=None):
	"""A draft Stock Reconciliation setting each counted item to its reel total.

	Draft only: ops reviews and submits it as part of the count close. Items with no
	counted reels are left out, so an unfinished aisle never zeroes real stock.
	"""
	_require(RECONCILE_ROLES, "Making the stock reconciliation")
	if not warehouse:
		frappe.throw("Choose the warehouse that was counted.")
	from illumenate_lighting.illumenate_lighting.api import labels

	chosen = set(labels._as_list(items))
	rows, _items = _summary_rows(warehouse)
	rows = [
		row for row in rows if row["counted_qty"] is not None and (not chosen or row["item_code"] in chosen)
	]
	if not rows:
		frappe.throw(f"No counted reels in {warehouse}.")
	# ERPNext refuses a reconciliation that changes nothing, so only differing items go in.
	rows = [row for row in rows if row["difference"]]
	if not rows:
		frappe.throw(f"Every counted item in {warehouse} already matches ERPNext. Nothing to reconcile.")
	rates = {
		row.item_code: row.valuation_rate
		for row in frappe.get_all(
			"Bin", filters={"warehouse": warehouse}, fields=["item_code", "valuation_rate"]
		)
	}
	doc = frappe.get_doc(
		{
			"doctype": "Stock Reconciliation",
			"purpose": "Stock Reconciliation",
			"company": frappe.db.get_value("Warehouse", warehouse, "company"),
			"items": [
				{
					"item_code": row["item_code"],
					"warehouse": warehouse,
					"qty": row["counted_qty"],
					"valuation_rate": rates.get(row["item_code"])
					or frappe.db.get_value("Item", row["item_code"], "valuation_rate")
					or 0,
				}
				for row in rows
			],
		}
	)
	doc.insert()
	doc.add_comment("Comment", f"Drafted from the reel count: {len(rows)} item(s), totals from ilL-Reel.")
	return {"name": doc.name, "items": len(rows)}
