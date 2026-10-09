# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Design Catalog adapter: engine-shaped catalog snapshots built from the spec doctypes (plan H7, WP-2.1).

``build_payload`` maps the spec records the readiness report loads (:mod:`.readiness`) into the riser
``CatalogItem`` and ``WireType`` shapes. A record that fails a readiness rule becomes an ``incomplete``
item whose ``missingFields`` are the same ERP fieldnames the report lists, so the report and the designer
never disagree. The mapping functions are pure; only the ``load_*`` / snapshot functions touch the
database.

D6: nothing here emits a cost. Driver ``cost`` orders the supply ``rank`` and is then dropped;
:func:`forbidden_keys` is the guard the tests (and :func:`build_snapshot`) run on every payload.
"""

import base64
import gzip
import hashlib
import json

import frappe
from frappe import _

from illumenate_lighting.illumenate_lighting.system_design import readiness, units, wire
from illumenate_lighting.illumenate_lighting.system_design.errors import DesignError

ENGINE_CONTRACT_VERSION = "catalog-1"
CODE_TABLES_VERSION = "nec-2023-1"
BRAND = "ilLumenate"
SNAPSHOT_DOCTYPE = "ilL-Design-Catalog-Snapshot"
CACHE_PREFIX = "ill:design_catalog:"
CURRENT_KEY = CACHE_PREFIX + "current"
CACHE_SECONDS = 24 * 60 * 60
FORBIDDEN_KEYS = frozenset(
	{"cost", "valuation_rate", "last_purchase_rate", "standard_rate", "selection_cost", "buying_price"}
)

DRIVES = {"CV": "CV", "CV with CC IC": "CV-CC-IC"}
POWER_BASES = {"All Channel Max": "all-channel-max", "Max Operating": "max-operating"}
PIXEL_PROTOCOLS = {"WS2811": "WS2811", "WS2815": "WS2815", "SK6812": "SK6812", "SPI Other": "SPI-other"}
INPUT_TYPES = {"VAC": "AC", "VDC": "DC"}
PHASE_OUTPUTS = {"Phase Forward": "phase-forward", "Phase Reverse": "phase-reverse"}
PORT_DIRECTIONS = {"In": "in", "Out": "out", "Bidirectional": "bidirectional"}
AMPACITY_BASES = {"310.16": "310.16", "402.5 fallback": "402.5-fallback", "Manufacturer": "manufacturer"}
SALES_UOMS = {"Per Foot": "foot", "Per Spool": "spool"}


# --- Pure helpers ------------------------------------------------------------------------------


def _num(value):
	"""A positive number rounded for the payload (H7.3), else ``None``."""
	try:
		number = float(value)
	except (TypeError, ValueError):
		return None
	if number != number or number <= 0:
		return None
	return int(number) if number.is_integer() else round(number, units.PAYLOAD_DECIMALS)


def _count(value):
	try:
		number = int(value or 0)
	except (TypeError, ValueError):
		return None
	return number if number > 0 else None


def _label(value):
	return f"{value:g}" if isinstance(value, (int, float)) else str(value)


def _compact(values):
	return {key: value for key, value in values.items() if value is not None}


def _protocols(names, engine_protocols):
	seen = []
	for name in names:
		value = engine_protocols.get(name)
		if value and value not in seen:
			seen.append(value)
	return seen


def _item_fields(item, fallback):
	name = (item or {}).get("item_name") or fallback
	return {"model": name, "description": (item or {}).get("description_text") or name}


def catalog_item(item_id, sku, item_code, category, kind, specs, check, item, source_doc):
	"""Wrap ``specs`` as a CatalogItem, or as ``incomplete`` when ``check`` lists missing fields."""
	body = {
		"id": item_id,
		"sku": sku,
		"brand": BRAND,
		**_item_fields(item, item_code),
		"category": category,
		"erpItemCode": item_code,
		"isExample": False,
		"source": {"kind": "manufacturer", "reference": f"ERPNext {source_doc[0]} {source_doc[1]}"},
		"sourceData": {"doctype": source_doc[0], "name": source_doc[1]},
		"localOverrides": [],
	}
	if check["missing"]:
		body["specs"] = {
			"kind": "incomplete",
			"intendedKind": kind,
			"available": _compact({key: value for key, value in specs.items() if key != "kind"}),
			"missingFields": check["missing"],
			"notes": check["notes"],
		}
	else:
		body["specs"] = {"kind": kind, **_compact(specs)}
	return body


# --- Tape (A.1) --------------------------------------------------------------------------------


def tape_groups(spec, offerings):
	"""Group active offerings by effective W/ft and cut increment: ``[(w, cut_mm), ...]`` sorted."""
	groups = set()
	for offering in offerings:
		watts = _num(offering.get("watts_per_ft_override")) or _num(spec.get("watts_per_foot"))
		cut = (
			None
			if spec.get("is_free_cutting")
			else _num(offering.get("cut_increment_mm_override")) or _num(spec.get("cut_increment_mm"))
		)
		groups.add((watts, cut))
	return sorted(groups, key=lambda group: (group[0] or 0, group[1] or 0))


def tape_specs(spec, watts, cut_mm, volts):
	channels = _count(spec.get("channels"))
	limits = spec.get("channel_limits") or []
	names = [str(row.get("channel_name") or "").strip() for row in limits]
	if channels and len(limits) == channels:
		channel_map = names
	else:
		channel_map = [f"CH{index}" for index in range(1, (channels or 0) + 1)]
	maxima = [_num(row.get("max_w_per_ft")) for row in limits]
	pixel = None
	protocol = PIXEL_PROTOCOLS.get(spec.get("pixel_protocol"))
	if protocol and _num(spec.get("pixels_per_m")) and _num(spec.get("amps_per_pixel_max")):
		pixel = {
			"protocol": protocol,
			"pixelsPerFt": units.per_m_to_per_ft(spec["pixels_per_m"]),
			"ampsPerPixelMax": _num(spec["amps_per_pixel_max"]),
		}
	free = bool(spec.get("is_free_cutting"))
	return {
		"kind": "tape",
		"voltage": int(volts) if volts and float(volts) in readiness.TAPE_VOLTAGES else None,
		"drive": DRIVES.get(spec.get("drive_type")),
		"wPerFtMax": watts,
		"powerBasis": POWER_BASES.get(spec.get("power_basis")),
		"channelWPerFtMax": maxima if channels and len(maxima) == channels and all(maxima) else None,
		"channels": channels,
		"channelMap": channel_map or None,
		"maxSimultaneousPct": _num(spec.get("max_simultaneous_pct")),
		"maxRunFtSingleFeed": _num(spec.get("max_run_single_feed_ft"))
		or _num(spec.get("voltage_drop_max_run_length_ft")),
		"maxRunFtDoubleFeed": _num(spec.get("max_run_double_feed_ft")),
		"freeCutting": free,
		"cutIntervalIn": None if free or not cut_mm else units.mm_to_in(cut_mm),
		"minOperatingV": _num(spec.get("min_operating_voltage_v")),
		"reelLengthFt": units.m_to_ft(spec["reel_length_m"]) if _num(spec.get("reel_length_m")) else None,
		"pixel": pixel,
	}


def tape_items(spec, offerings, context, items):
	"""One catalog item per (W/ft, cut) group of the spec's active offerings."""
	check = readiness.tape_check(spec, context)
	volts = context["voltages"].get(spec.get("input_voltage"))
	groups = tape_groups(spec, offerings)
	result = []
	for watts, cut_mm in groups:
		check_group = check
		if not watts and "watts_per_foot" not in check["missing"]:
			check_group = {**check, "missing": [*check["missing"], "watts_per_foot"]}
		item_id = f"tape:{spec['name']}:{_label(watts or 0)}:{'free' if cut_mm is None else _label(cut_mm)}"
		sku = spec["item"]
		if len(groups) > 1:
			sku = f"{sku} {_label(watts or 0)} W/ft" + ("" if cut_mm is None else f" {_label(cut_mm)} mm cut")
		result.append(
			catalog_item(
				item_id,
				sku,
				spec["item"],
				"tape",
				"tape",
				tape_specs(spec, watts, cut_mm, volts),
				check_group,
				items.get(spec["item"]),
				(readiness.TAPE, spec["name"]),
			)
		)
	return result


# --- Supplies and drivers (A.2) ----------------------------------------------------------------


def power_specs(spec, context):
	constant_current = spec.get("output_type") == "Constant Current"
	count = _count(spec.get("independent_outputs_count"))
	per_output = _num(spec.get("max_wattage_per_output"))
	outputs = [
		{"name": f"OUT{index}", "maxW": per_output, "class2": bool(spec.get("class2_outputs"))}
		for index in range(1, (count or 0) + 1)
	]
	at_v = _num(spec.get("max_input_a_at_v"))
	return {
		"kind": "driver" if constant_current else "psu",
		"inputType": INPUT_TYPES.get(spec.get("input_voltage_type")),
		"inputPhase": spec.get("input_phase") or None,
		"inputVMin": _num(spec.get("input_voltage_min")),
		"inputVMax": _num(spec.get("input_voltage_max")),
		"outputType": "CC" if constant_current else "CV",
		"outputV": None if constant_current else _num(context["voltages"].get(spec.get("voltage_output"))),
		"outputmA": _num(spec.get("output_current_ma")) if constant_current else None,
		"outputVMin": _num(spec.get("compliance_v_min")) if constant_current else None,
		"outputVMax": _num(spec.get("compliance_v_max")) if constant_current else None,
		"ratedW": _num(spec.get("max_wattage")),
		"outputs": outputs if per_output else None,
		"efficiency": _num(spec.get("efficiency")),
		"powerFactor": _num(spec.get("power_factor")),
		"maxInputA": _num(spec.get("max_input_a")) if at_v else None,
		"maxInputAAtV": at_v if _num(spec.get("max_input_a")) else None,
		"inrushA": _num(spec.get("inrush_a")),
		"maxUnitsPer20ABreaker": _count(spec.get("max_units_per_20a_breaker")),
		"dimming": _protocols(spec.get("input_protocols") or [], context["engine"]),
		"terminalMinAwg": spec.get("terminal_min_awg") or None,
		"terminalMaxAwg": spec.get("terminal_max_awg") or None,
		"listings": sorted({name for name in spec.get("certifications") or [] if name}),
		"usableLoadFactor": _num(spec.get("usable_load_factor")),
	}


def supply_ranks(drivers, priorities, costs):
	"""D6 dense rank by (eligibility priority desc, cost asc, item code asc); integers from 1.

	``costs`` is read here and never returned.
	"""

	def key(spec):
		cost = costs.get(spec["name"])
		return (-(priorities.get(spec["name"]) or 0), cost is None, cost or 0, spec.get("item") or "")

	ranks, previous, rank = {}, None, 0
	for spec in sorted(drivers, key=key):
		if key(spec) != previous:
			rank += 1
			previous = key(spec)
		ranks[spec["name"]] = rank
	return ranks


def power_item(spec, context, items, rank=None):
	specs = power_specs(spec, context)
	item = catalog_item(
		f"drv:{spec['name']}",
		spec["item"],
		spec["item"],
		specs["kind"],
		specs["kind"],
		specs,
		readiness.driver_check(spec, context),
		items.get(spec["item"]),
		(readiness.DRIVER, spec["name"]),
	)
	if rank is not None:
		item["rank"] = rank
	return item


# --- Controls (A.3, A.5) -----------------------------------------------------------------------


def _ports(spec, engine_protocols):
	ports = []
	for row in spec.get("ports") or []:
		ports.append(
			_compact(
				{
					"name": str(row.get("port_name") or "").strip() or None,
					"direction": PORT_DIRECTIONS.get(row.get("direction")),
					"protocol": engine_protocols.get(row.get("protocol")),
					"maxDevices": _count(row.get("max_devices")),
				}
			)
		)
	return ports


def control_specs(spec, category, context):
	engine = context["engine"]
	protocol_in = _protocols(spec.get("input_protocols") or [], engine)
	protocol_out = _protocols(spec.get("output_protocols") or [], engine)
	common = {
		"inputVMin": _num(spec.get("input_voltage_min")),
		"inputVMax": _num(spec.get("input_voltage_max")),
		"terminalMinAwg": spec.get("terminal_min_awg") or None,
		"terminalMaxAwg": spec.get("terminal_max_awg") or None,
		"dmxFootprint": _count(spec.get("dmx_footprint")),
		"unitLoad": _num(spec.get("unit_load")),
	}
	if category == "dmx-decoder":
		return {
			"kind": "decoder",
			**common,
			"dmxThru": bool(spec.get("dmx_thru")),
			"powerType": INPUT_TYPES.get(spec.get("input_voltage_type")),
			"channels": _count(spec.get("channels")),
			"maxAPerChannel": _num(spec.get("max_a_per_channel")),
			"maxATotal": _num(spec.get("max_load_amps")),
			"maxWPerChannel": _num(spec.get("max_w_per_channel")),
			"maxWTotal": _num(spec.get("max_load_watts")),
			"outputDimming": PHASE_OUTPUTS.get(spec.get("output_dimming")),
			"protocolIn": protocol_in,
			"protocolOut": protocol_out or None,
		}
	standby = _num(spec.get("standby_power_watts")) or 0
	return {
		"kind": "controller",
		**common,
		"inputType": INPUT_TYPES.get(spec.get("input_voltage_type")),
		"ownPowerW": standby,
		"protocolIn": protocol_in,
		"protocolOut": protocol_out,
		"ports": _ports(spec, engine),
		"maxUniverses": _count(spec.get("max_universes")),
		"maxPixels": _count(spec.get("max_pixels")),
		"maxDataLengthFt": _num(spec.get("max_data_length_ft")),
		"maxBusDevices": _count(spec.get("max_bus_devices")),
	}


def control_item(spec, context, items):
	"""``None`` for devices the engine catalog cannot hold yet (sensors, phase dimmers)."""
	check = readiness.controller_check(spec, context)
	if check["status"] == readiness.STATUS_NOT_MODELLED:
		return None
	category = readiness.controller_category(spec.get("controller_type"), spec.get("output_dimming"))
	if category in readiness.NOT_IN_CATALOG:
		return None
	if not category:
		# The type itself is unknown: keep the record visible as an incomplete generic controller.
		category = "dmx-controller"
	specs = control_specs(spec, category, context)
	return catalog_item(
		f"ctl:{spec['name']}",
		spec["item"],
		spec["item"],
		category,
		specs["kind"],
		specs,
		check,
		items.get(spec["item"]),
		(readiness.CONTROLLER, spec["name"]),
	)


# --- Wire (A.6, D7) ----------------------------------------------------------------------------


def wire_type(spec):
	"""A ready wire spec as a riser ``WireType`` (callers drop incomplete wires first)."""
	applications, _unknown = wire.split_applications(spec.get("applications"))
	category = next(
		(key for key, label in wire.CATEGORIES.items() if label == wire.category_label(spec.get("category"))),
		None,
	)
	conductors = []
	for row in spec.get("conductors") or []:
		conductors.append(
			_compact(
				{
					"count": _count(row.get("count")),
					"awg": row.get("awg"),
					"material": row.get("material"),
					"stranding": str(row.get("stranding") or "").lower() or None,
					"role": wire.key(row.get("role")) or None,
					"colors": wire.colors_list(row.get("colors")) or None,
					"resistanceOhmPerKft": _num(row.get("resistance_ohm_per_kft")),
					"ampacityA": _num(row.get("ampacity_a")),
				}
			)
		)
	mode = spec.get("sales_uom_mode") or "Per Foot"
	return _compact(
		{
			"id": f"wire:{spec['item']}",
			"name": spec.get("wire_name"),
			"manufacturerRefs": [],
			"manufacturerRefChecks": [],
			"category": category,
			"applications": applications,
			"conductors": conductors,
			"listing": spec.get("listing"),
			"ratedV": _num(spec.get("rated_v")) or 0,
			"tempRatingC": int(spec.get("temp_rating_c")),
			"plenum": bool(spec.get("plenum")),
			"riser": bool(spec.get("riser")),
			"wet": bool(spec.get("wet")),
			"directBurial": bool(spec.get("direct_burial")),
			"sunlightResistant": bool(spec.get("sunlight_resistant")),
			"shielded": bool(spec.get("shielded")),
			"impedanceOhm": _num(spec.get("impedance_ohm")),
			"resistanceOhmPerKft": _num(spec.get("resistance_ohm_per_kft")),
			"ampacityA": _num(spec.get("ampacity_a")),
			"odIn": _num(spec.get("od_in")),
			"riserLabel": spec.get("riser_label"),
			"isExample": False,
			"verify": not spec.get("is_verified"),
			"source": {"kind": "manufacturer", "reference": spec.get("source_reference")},
			"notes": "",
			"ampacityBasis": AMPACITY_BASES.get(spec.get("ampacity_basis") or "", "not-applicable"),
			"erpItemCode": spec["item"],
			"salesUom": SALES_UOMS.get(mode, "foot"),
			"spoolLengthFt": _num(spec.get("spool_length_ft")) if mode == "Per Spool" else None,
		}
	)


# --- Payload -----------------------------------------------------------------------------------


def build_payload(data):
	"""Pure: ``data`` holds the loaded records (see :func:`load_data`)."""
	context = data["context"]
	items_by_code = data["items"]
	result = []
	for spec in data["tapes"]:
		result.extend(tape_items(spec, data["offerings"].get(spec["name"], []), context, items_by_code))
	ready_drivers = [spec for spec in data["drivers"] if not readiness.driver_check(spec, context)["missing"]]
	ranks = supply_ranks(ready_drivers, data["priorities"], data["costs"])
	for spec in data["drivers"]:
		result.append(power_item(spec, context, items_by_code, ranks.get(spec["name"])))
	for spec in data["controllers"]:
		item = control_item(spec, context, items_by_code)
		if item:
			result.append(item)
	wires = [wire_type(spec) for spec in data["wires"] if not readiness.wire_check(spec)["missing"]]
	payload = {
		"engine_contract_version": ENGINE_CONTRACT_VERSION,
		"items": sorted(result, key=lambda item: item["id"]),
		"wires": sorted(wires, key=lambda item: item["id"]),
		"code_tables_version": CODE_TABLES_VERSION,
	}
	found = forbidden_keys(payload)
	if found:
		raise ValueError(f"Catalog payload carries forbidden keys: {', '.join(sorted(found))}")
	return payload


def forbidden_keys(value):
	"""Every forbidden (cost) key at any depth of ``value``."""
	found = set()
	if isinstance(value, dict):
		for key, child in value.items():
			if key in FORBIDDEN_KEYS:
				found.add(key)
			found |= forbidden_keys(child)
	elif isinstance(value, list):
		for child in value:
			found |= forbidden_keys(child)
	return found


def payload_json(payload):
	return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def payload_hash(payload):
	return hashlib.sha256(payload_json(payload).encode("utf-8")).hexdigest()


def summarize(payload):
	return {
		"item_count": len(payload["items"]),
		"incomplete_count": sum(1 for item in payload["items"] if item["specs"]["kind"] == "incomplete"),
		"wire_count": len(payload["wires"]),
	}


def pack(payload):
	return base64.b64encode(gzip.compress(payload_json(payload).encode("utf-8"), mtime=0)).decode("ascii")


def unpack(text):
	return json.loads(gzip.decompress(base64.b64decode(text)).decode("utf-8"))


# --- Database ----------------------------------------------------------------------------------


def _items(codes):
	if not codes:
		return {}
	rows = frappe.get_all(
		"Item",
		filters={"name": ["in", sorted(codes)]},
		fields=["name", "item_name", "disabled", "is_sales_item", "has_variants"],
	)
	return {row["name"]: row for row in rows}


def load_data():
	"""Every record the payload needs, in bulk queries (no N+1)."""
	tapes, drivers = readiness.load_tapes(), readiness.load_drivers()
	controllers, wires = readiness.load_controllers(), readiness.load_wires()
	codes = {
		spec["item"] for group in (tapes, drivers, controllers, wires) for spec in group if spec.get("item")
	}
	items = _items(codes)

	def sellable(spec, sales=False):
		item = items.get(spec.get("item"))
		return bool(item) and not item.get("disabled") and (not sales or item.get("is_sales_item"))

	tapes = [spec for spec in tapes if sellable(spec)]
	drivers = [spec for spec in drivers if sellable(spec, sales=True)]
	controllers = [spec for spec in controllers if sellable(spec)]
	wires = [spec for spec in wires if sellable(spec, sales=True)]
	offerings = {}
	if tapes:
		for row in frappe.get_all(
			"ilL-Rel-Tape Offering",
			filters={"is_active": 1, "tape_spec": ["in", [spec["name"] for spec in tapes]]},
			fields=["name", "tape_spec", "watts_per_ft_override", "cut_increment_mm_override"],
			order_by="name asc",
		):
			offerings.setdefault(row["tape_spec"], []).append(row)
	names = [spec["name"] for spec in drivers]
	priorities, costs = {}, {}
	if names:
		for row in frappe.get_all(
			"ilL-Rel-Driver-Eligibility",
			filters={"driver_spec": ["in", names], "is_active": 1, "is_allowed": 1},
			fields=["driver_spec", "priority"],
		):
			current = priorities.get(row["driver_spec"])
			priorities[row["driver_spec"]] = max(current or 0, int(row["priority"] or 0))
		# Read only to order ``rank`` (D6); never copied into the payload.
		costs = {
			row["name"]: row["cost"]
			for row in frappe.get_all(
				readiness.DRIVER, filters={"name": ["in", names]}, fields=["name", "cost"]
			)
		}
	return {
		"context": readiness.context(),
		"items": items,
		"tapes": tapes,
		"offerings": offerings,
		"drivers": drivers,
		"priorities": priorities,
		"costs": costs,
		"controllers": controllers,
		"wires": wires,
	}


def _cache():
	return frappe.cache()


def build_snapshot():
	"""Build, store and cache the current catalog; return its hash."""
	payload = build_payload(load_data())
	snapshot_hash = payload_hash(payload)
	if not frappe.db.exists(SNAPSHOT_DOCTYPE, snapshot_hash):
		try:
			frappe.get_doc(
				{
					"doctype": SNAPSHOT_DOCTYPE,
					"snapshot_hash": snapshot_hash,
					"engine_contract_version": ENGINE_CONTRACT_VERSION,
					"generated_on": frappe.utils.now_datetime(),
					"catalog_json": pack(payload),
					**summarize(payload),
				}
			).insert(ignore_permissions=True)
			request = getattr(frappe.local, "request", None)
			if request is not None and request.method == "GET":
				# Frappe does not commit GET requests; designs keep this hash, so it must persist.
				frappe.db.commit()  # nosemgrep
		except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
			pass  # A concurrent build stored the same snapshot.
	_cache().set_value(CACHE_PREFIX + snapshot_hash, payload, expires_in_sec=CACHE_SECONDS)
	_cache().set_value(CURRENT_KEY, snapshot_hash, expires_in_sec=CACHE_SECONDS)
	return snapshot_hash


def current_snapshot_hash():
	return _cache().get_value(CURRENT_KEY) or build_snapshot()


def get_snapshot(snapshot_hash):
	"""The stored payload for ``snapshot_hash``, or ``None``."""
	if not isinstance(snapshot_hash, str) or len(snapshot_hash) != 64:
		return None
	payload = _cache().get_value(CACHE_PREFIX + snapshot_hash)
	if payload is None:
		text = frappe.db.get_value(SNAPSHOT_DOCTYPE, snapshot_hash, "catalog_json")
		if not text:
			return None
		payload = unpack(text)
		_cache().set_value(CACHE_PREFIX + snapshot_hash, payload, expires_in_sec=CACHE_SECONDS)
	return payload


def invalidate(*_args, **_kwargs):
	"""``doc_events`` hook: the next read rebuilds the current snapshot. Stored snapshots stay."""
	_cache().delete_value(CURRENT_KEY)


def catalog_response(snapshot_hash):
	payload = get_snapshot(snapshot_hash)
	if payload is None:
		raise DesignError("NOT_FOUND", _("Catalog snapshot not found"))
	headers = getattr(frappe.local, "response_headers", None)
	if headers is not None:
		headers["ETag"] = f'"{snapshot_hash}"'
	return {"hash": snapshot_hash, **payload}
