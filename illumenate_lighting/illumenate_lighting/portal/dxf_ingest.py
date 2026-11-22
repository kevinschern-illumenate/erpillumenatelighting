"""Drawings made without the CAD toolkit: an ASCII DXF becomes an ``ilq/2`` package (plan 6.1, 6.2).

The dealer draws runs on layers named by template, and the portal's drawing import does the rest
exactly as for a toolkit package:

- ``ILM-TAPE-<template_code>``: an LED tape, COB tape or neon run of that template;
- ``ILM-LINEAR-<fixture template>``: a linear fixture run (needs a preset for its options);
- ``ILM-ROOM-<room name>``: a closed polyline per room; runs take the room their first point is in;
- ``ILM-CAB``: cabinet blocks (attribute ``TAG``, optional ``RATING``) and PSU locations.

Runs are LWPOLYLINE (with bulges), POLYLINE, LINE or ARC entities. ``$INSUNITS`` must be set (inches,
feet, millimetres, centimetres or metres), so a length is never guessed. Options come from a preset
chosen per layer (``options.presets``); without one the import asks for them (``needs_choice``). The
schedule Type of each layer comes from ``options.types`` or defaults to ``D1``, ``D2``... by layer.
Pure Python, no CAD library, so it runs on Frappe Cloud as is. Wire paths are not read: the System
Designer estimates home runs for DXF jobs.
"""

import hashlib
import itertools
import math
import re

import frappe
from frappe import _

MAX_DXF_BYTES = 20 * 1024 * 1024
UNIT_INCHES = {1: 1.0, 2: 12.0, 4: 1 / 25.4, 5: 10 / 25.4, 6: 1000 / 25.4}
UNIT_NAMES = {1: "in", 2: "ft", 4: "mm", 5: "cm", 6: "m"}
TAPE_PREFIX = "ILM-TAPE-"
LINEAR_PREFIX = "ILM-LINEAR-"
STYLE_PREFIX = "ILM-STYLE-"
SHEET_ID = "S1"
ROOM_PREFIX = "ILM-ROOM-"
CABINET_LAYER = "ILM-CAB"
RUN_TYPES = ("LWPOLYLINE", "POLYLINE", "LINE", "ARC")


class DxfError(ValueError):
	pass


# --- Reading ----------------------------------------------------------------------------------


def pairs(text):
	"""``(code, value)`` pairs of an ASCII DXF."""
	lines = text.splitlines()
	if len(lines) < 2:
		raise DxfError(_("This is not an ASCII DXF file"))
	result = []
	for index in range(0, len(lines) - 1, 2):
		code = lines[index].strip()
		try:
			result.append((int(code), lines[index + 1].strip()))
		except ValueError:
			raise DxfError(_("This is not an ASCII DXF file (line {0})").format(index + 1)) from None
	return result


def sections(items):
	"""``{section name: [(code, value), ...]}``."""
	result, name, current = {}, None, None
	for index, (code, value) in enumerate(items):
		if code == 0 and value == "SECTION" and index + 1 < len(items) and items[index + 1][0] == 2:
			name, current = items[index + 1][1], []
			continue
		if code == 0 and value == "ENDSEC":
			if name:
				result[name] = current[1:] if current and current[0][0] == 2 else current
			name, current = None, None
			continue
		if current is not None:
			current.append((code, value))
	return result


def header_units(header):
	for index, (code, value) in enumerate(header):
		if code == 9 and value == "$INSUNITS" and index + 1 < len(header):
			try:
				return int(header[index + 1][1])
			except ValueError:
				return None
	return None


def entities(items):
	"""Entities as dicts: ``type``, ``layer``, ``handle``, raw ``codes`` and nested ``children``."""
	result, current = [], None
	for code, value in items:
		if code == 0:
			if value in ("VERTEX", "ATTRIB") and current and current["type"] in ("POLYLINE", "INSERT"):
				current["children"].append({"type": value, "codes": []})
				continue
			if value == "SEQEND" and current:
				continue
			current = {"type": value, "codes": [], "children": []}
			result.append(current)
			continue
		if current is None:
			continue
		target = current["children"][-1] if current["children"] else current
		target["codes"].append((code, value))
	for entity in result:
		entity["layer"] = next((value for code, value in entity["codes"] if code == 8), "0")
		entity["handle"] = next((value for code, value in entity["codes"] if code == 5), None)
	return result


def _float(value):
	return float(value)


def lw_vertices(codes):
	vertices, closed = [], False
	for code, value in codes:
		if code == 70:
			closed = bool(int(value) & 1)
		elif code == 10:
			vertices.append([_float(value), 0.0, 0.0])
		elif code == 20 and vertices:
			vertices[-1][1] = _float(value)
		elif code == 42 and vertices:
			vertices[-1][2] = _float(value)
	return vertices, closed


def polyline_vertices(entity):
	closed = any(code == 70 and int(value) & 1 for code, value in entity["codes"])
	vertices = []
	for child in entity["children"]:
		if child["type"] != "VERTEX":
			continue
		values = dict(child["codes"])
		vertices.append([_float(values.get(10, 0)), _float(values.get(20, 0)), _float(values.get(42, 0))])
	return vertices, closed


def entity_vertices(entity):
	"""``([[x, y, bulge], ...], closed)`` for a run-shaped entity."""
	values = dict(entity["codes"])
	if entity["type"] == "LWPOLYLINE":
		return lw_vertices(entity["codes"])
	if entity["type"] == "POLYLINE":
		return polyline_vertices(entity)
	if entity["type"] == "LINE":
		return [
			[_float(values[10]), _float(values[20]), 0.0],
			[_float(values[11]), _float(values[21]), 0.0],
		], False
	if entity["type"] == "ARC":
		cx, cy, radius = _float(values[10]), _float(values[20]), _float(values[40])
		start, end = math.radians(_float(values[50])), math.radians(_float(values[51]))
		sweep = (end - start) % (2 * math.pi) or 2 * math.pi
		first = [cx + radius * math.cos(start), cy + radius * math.sin(start), math.tan(sweep / 4)]
		last = [cx + radius * math.cos(end), cy + radius * math.sin(end), 0.0]
		return [first, last], False
	raise DxfError(_("{0} is not a run shape").format(entity["type"]))


def path_length(vertices, closed=False):
	"""``(length, smallest arc radius or None)`` in drawing units (bulges are arcs)."""
	points = [*vertices, vertices[0]] if closed and vertices else list(vertices)
	total, smallest = 0.0, None
	for start, end in itertools.pairwise(points):
		chord = math.hypot(end[0] - start[0], end[1] - start[1])
		bulge = start[2]
		if not bulge or chord == 0:
			total += chord
			continue
		angle = 4 * math.atan(abs(bulge))
		radius = chord / (2 * math.sin(angle / 2))
		total += radius * angle
		smallest = radius if smallest is None else min(smallest, radius)
	return total, smallest


def point_in_polygon(point, vertices):
	inside, count = False, len(vertices)
	for index in range(count):
		a, b = vertices[index], vertices[(index + 1) % count]
		if (a[1] > point[1]) != (b[1] > point[1]) and point[0] < a[0] + (b[0] - a[0]) * (point[1] - a[1]) / (
			b[1] - a[1]
		):
			inside = not inside
	return inside


def attributes(entity):
	values = {}
	for child in entity["children"]:
		if child["type"] == "ATTRIB":
			codes = dict(child["codes"])
			if codes.get(2):
				values[codes[2].upper()] = codes.get(1, "")
	return values


def _id(text, prefix=""):
	slug = re.sub(r"[^A-Za-z0-9._-]+", "-", str(text)).strip("-.") or "X"
	return (prefix + slug)[:38]


# --- Package ------------------------------------------------------------------------------------


def read_drawing(text):
	"""Units, rooms, cabinets and runs (raw) of a DXF, in inches. Pure."""
	parsed = sections(pairs(text))
	units = header_units(parsed.get("HEADER", []))
	if units not in UNIT_INCHES:
		raise DxfError(
			_(
				"Set the drawing units before saving the DXF ($INSUNITS is {0}; use inches, feet, mm, cm or m)"
			).format(units if units is not None else _("not set"))
		)
	scale = UNIT_INCHES[units]
	rooms, cabinets, runs, handles = [], [], [], set()
	for index, entity in enumerate(entities(parsed.get("ENTITIES", []))):
		layer = entity["layer"].upper()
		handle = (entity["handle"] or format(0x1000 + index, "X")).upper()
		if handle in handles:
			continue
		handles.add(handle)
		if layer.startswith(ROOM_PREFIX) and entity["type"] in ("LWPOLYLINE", "POLYLINE"):
			vertices, closed = entity_vertices(entity)
			if closed and len(vertices) >= 3:
				name = entity["layer"][len(ROOM_PREFIX) :].replace("_", " ").strip() or "Room"
				rooms.append({"id": _id(name, "Z-"), "name": name[:120], "vertices": vertices})
		elif layer == CABINET_LAYER and entity["type"] == "INSERT":
			values = attributes(entity)
			codes = dict(entity["codes"])
			cabinets.append(
				{
					"id": _id(values.get("TAG") or f"CAB-{len(cabinets) + 1}"),
					"rating": values.get("RATING", "Dry").title()
					if values.get("RATING", "Dry").title() in ("Dry", "Damp", "Wet")
					else "Dry",
					"point": [_float(codes.get(10, 0)), _float(codes.get(20, 0))],
				}
			)
		elif (
			layer.startswith(TAPE_PREFIX) or layer.startswith(LINEAR_PREFIX) or layer.startswith(STYLE_PREFIX)
		) and entity["type"] in RUN_TYPES:
			vertices, closed = entity_vertices(entity)
			if len(vertices) < 2:
				continue
			length, smallest = path_length(vertices, closed)
			if length <= 0:
				continue
			linear = layer.startswith(LINEAR_PREFIX)
			styled = layer.startswith(STYLE_PREFIX)
			prefix = STYLE_PREFIX if styled else LINEAR_PREFIX if linear else TAPE_PREFIX
			runs.append(
				{
					"layer": entity["layer"],
					"template": "" if styled else entity["layer"][len(prefix) :],
					"style_code": entity["layer"][len(prefix) :].upper() if styled else None,
					"linear": linear,
					"handle": handle[-16:],
					"length_in": round(length * scale, 4),
					"min_arc_radius_in": round(smallest * scale, 4) if smallest else None,
					"start": vertices[0],
				}
			)
	return {"units": UNIT_NAMES[units], "rooms": rooms, "cabinets": cabinets, "runs": runs}


def _room_of(point, rooms):
	return next((room for room in rooms if point_in_polygon(point, room["vertices"])), None)


def package_from_drawing(drawing, styles, types, filename, digest, snapshot_hash):
	"""The ``ilq/2`` package. ``styles`` maps a layer to its style; ``types`` a layer to its Type."""
	if not drawing["runs"]:
		raise DxfError(
			_("No runs found: draw runs on layers named ILM-TAPE-<template code> or ILM-LINEAR-<template>")
		)
	layers = sorted({run["layer"] for run in drawing["runs"]})
	type_for = {layer: types.get(layer) or f"D{index}" for index, layer in enumerate(layers, start=1)}
	counters, runs = {}, []
	for run in sorted(drawing["runs"], key=lambda item: (item["layer"], item["handle"])):
		fixture_type = type_for[run["layer"]]
		counters[fixture_type] = counters.get(fixture_type, 0) + 1
		room = _room_of(run["start"], drawing["rooms"])
		segment = {"path_length_in": run["length_in"], "end_type": "ENDCAP"}
		if run["min_arc_radius_in"]:
			segment["min_arc_radius_in"] = run["min_arc_radius_in"]
		entry = {
			"id": _id(f"{fixture_type}-{counters[fixture_type]:02d}"),
			"handle": run["handle"],
			"sheet": SHEET_ID,
			"identity": "dxf_handle",
			"fixture_type": fixture_type,
			"style": styles[run["layer"]],
			"segments": [segment],
			"erp": {},
		}
		if room:
			entry["room"] = room["id"]
			entry["location"] = room["name"]
		runs.append(entry)
	return {
		"schema": "ilq/2",
		"toolkit": {"version": "dxf-1", "platform": "DXF upload"},
		"source": {"tool": "dxf", "version": "dxf-1", "platform": "DXF upload", "input": "dxf"},
		"catalog": {"snapshot_hash": snapshot_hash, "generated_at": ""},
		"target": {},
		# A DXF declares its units; nothing says an underlay was calibrated (WP 1.3).
		"drawing": {
			"file": filename[:260],
			"rev": 0,
			"hash": f"sha256:{digest}",
			"units": "in",
			"scale_verified": False,
		},
		"sheets": [
			{
				"id": SHEET_ID,
				"label": "Model",
				"scale": {"status": "declared", "unit": drawing.get("units") or "in"},
			}
		],
		"rooms": [{"id": room["id"], "name": room["name"]} for room in drawing["rooms"]],
		"cabinets": [
			{
				"id": cabinet["id"],
				"location_rating": cabinet["rating"],
				**({"room": room["id"]} if (room := _room_of(cabinet["point"], drawing["rooms"])) else {}),
			}
			for cabinet in drawing["cabinets"]
		],
		"runs": runs,
		"check": {"errors": 0, "warnings": 0},
	}


# --- Resolving styles (database) -----------------------------------------------------------------


def layer_style(run, preset_name):
	"""The style a layer's runs get: its preset, else the template with no options chosen yet."""
	from illumenate_lighting.illumenate_lighting.portal import presets

	if preset_name:
		loaded = presets.load(preset_name)
		request = loaded.get("request")
		if not request:
			raise DxfError(
				_("Preset {0} cannot be used: {1}").format(
					preset_name, "; ".join(loaded.get("problems") or [])
				)
			)
		style = {
			"preset": loaded.get("label") or preset_name,
			"family": request["family"],
			"template": request["template"] or run["template"],
			"selections": request.get("selections") or {},
		}
		if request.get("segments"):
			style["segments"] = request["segments"]
		return style
	if run.get("style_code"):
		found = presets.find_by_cad_code(run["style_code"])
		if not found:
			raise DxfError(
				_("Layer {0}: no drawing style with code {1} is available to you").format(
					run["layer"], run["style_code"]
				)
			)
		return layer_style({**run, "style_code": None}, found)
	if run["linear"]:
		# Previewed as needing a choice, so the dialog can offer a preset for the layer.
		return {"family": "Linear Fixture", "template": run["template"], "selections": {}}
	category = frappe.db.get_value(
		"ilL-Tape-Neon-Template", {"template_code": run["template"]}, "product_category"
	) or frappe.db.get_value("ilL-Tape-Neon-Template", run["template"], "product_category")
	if not category:
		raise DxfError(_("Layer {0}: no tape or neon template {1}").format(run["layer"], run["template"]))
	return {"family": category, "template": run["template"], "selections": {}}


def package_from_dxf(data, filename, options=None, report=None):
	"""Read DXF ``data`` (bytes) and return the ``ilq/2`` package for the drawing import."""
	from illumenate_lighting.illumenate_lighting.system_design import catalog

	options = options or {}
	if len(data) > MAX_DXF_BYTES:
		raise DxfError(_("The DXF is larger than 20 MB"))
	if data[:4] == b"AC10" or data.startswith(b"AutoCAD Binary DXF"):
		raise DxfError(_("Save the drawing as an ASCII DXF (not binary or DWG)"))
	try:
		text = data.decode("utf-8-sig")
	except UnicodeDecodeError:
		text = data.decode("cp1252", errors="replace")
	drawing = read_drawing(text)
	presets = options.get("presets") or {}
	styles = {}
	for run in drawing["runs"]:
		if run["layer"] not in styles:
			styles[run["layer"]] = layer_style(run, presets.get(run["layer"]))
	package = package_from_drawing(
		drawing,
		styles,
		options.get("types") or {},
		filename,
		hashlib.sha256(data).hexdigest(),
		catalog.current_snapshot_hash(),
	)
	if isinstance(report, dict):
		report["layers"] = layer_report(drawing, styles, package)
	return package


def layer_report(drawing, styles, package):
	"""Per layer: run count, the style it resolved to and its schedule Type, for the dialog's pickers."""
	types = {}
	for run in package["runs"]:
		types.setdefault(run["fixture_type"], run["fixture_type"])
	result = []
	for layer in sorted({run["layer"] for run in drawing["runs"]}):
		runs = [run for run in drawing["runs"] if run["layer"] == layer]
		style = styles.get(layer) or {}
		fixture_type = next(
			(item["fixture_type"] for item in package["runs"] if item["handle"] == runs[0]["handle"]), None
		)
		result.append(
			{
				"layer": layer,
				"runs": len(runs),
				"family": style.get("family"),
				"template": style.get("template"),
				"preset": style.get("preset"),
				"needs_preset": not style.get("preset") and not style.get("selections"),
				"fixture_type": fixture_type,
			}
		)
	return result
