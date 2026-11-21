"""Read-only probe of a Bluebeam Revu-marked-up PDF (draw-to-quote spike, WP 2.2-2.6).

Usage::

	python3 -m tools.bluebeam_spike.probe_pdf plan.pdf [--out report.json] [--lenient]

``probe(path_or_bytes)`` returns a JSON-safe dict: per page the MediaBox/CropBox, /UserUnit,
rotation, the /VP viewports (BBox, Name, Measure) and every annotation with its standard keys,
its vertices, a computed length when a measure applies, and ``extra_keys`` (every key outside the
ISO 32000 annotation key set: candidates for Bluebeam private data such as custom columns).

Safety
------
The file is untrusted. Nothing in it is executed or rendered; the probe only walks the object
graph with pypdf. The same checks as the portal (``portal/file_validation.py``) are applied,
reimplemented here so the tool runs without Frappe: strict parsing (``PdfReader(strict=True)``,
``--lenient`` retries non-strict and records the strict error, since the portal would refuse
such a file), encrypted files refused, 1-500 pages, and a document-level /OpenAction, /AA or
/Names /JavaScript refused. The size cap is 200 MB (the portal's upload cap is 20 MiB; the spike
corpus must still respect that). Malformed values are recorded in a per-page ``errors`` list.

Length formula (ISO 32000-1:2008 §12.9, "Measurement Properties"; Table 261 rectilinear
measure dictionary, Table 262 number format dictionary)
-----------------------------------------------------------------------------------------
Vertices (/Vertices for PolyLine and Polygon, /L for Line, and the PDF 2.0 /Path when present)
are in default user space, the same space as the page's /VP viewport /BBox. The measure applied
is the annotation's own /Measure if it has one, else the measure of the viewport whose /BBox
contains the annotation's first vertex; viewports are examined from last to first, so a later
viewport wins where viewports overlap (§12.9.2). Only /Subtype /RL (rectilinear, the default) is
computed; /GEO is recorded but not computed.

For each segment with deltas (dx, dy) in default user space units::

	fx = X[0].C                       # user space units -> largest X unit (e.g. ft)
	fy = Y[0].C * CYX  if Y present   # Y unit -> X unit via CYX
	   = fx            otherwise
	d  = D[0].C                       # largest X unit -> largest distance unit
	segment = d * sqrt((dx * fx)^2 + (dy * fy)^2)

``computed_length`` is the sum over segments (Polygon closes back to the first vertex) in the
unit ``D[0].U`` (``X[0].U`` if /D is missing); ``computed_length_in`` converts that to inches
when the unit label is recognised (in, ", ft, ', yd, mm, cm, m). The later elements of each
number format array only split the value into smaller display units (ft then in) and do not
change it. Polygon ``computed_area`` is the shoelace area of the scaled vertices times
``A[0].C``. Bezier segments in /Path are integrated numerically.

/UserUnit does not appear in the formula: the C factors are defined against default user space,
which already includes it. Whether Revu writes /Measure, /VP and C that way (and what it does on
pages with /UserUnit != 1, rotated pages, or curves) must be confirmed in the spike against the
AutoCAD ground truth (``compare_lengths``); this is the reading of the standard, not of Revu.

``contents_length_in`` is a heuristic parse of a length written in /Contents (Revu typically
shows the measured value there); it is evidence for the "Revu's own stored length" question,
not a trusted value.
"""

import argparse
import hashlib
import io
import json
import math
import os
import re
import sys
from collections import Counter
from itertools import pairwise
from pathlib import Path

MAX_BYTES = 200 * 1024 * 1024
MAX_PAGES = 500
MAX_ANNOTS_PER_PAGE = 5000
MAX_ARRAY_ITEMS = 1000
MAX_DICT_ITEMS = 200
MAX_DEPTH = 6
VALUE_LIMIT = 500
BEZIER_STEPS = 64

# ISO 32000-1 Tables 164 (all annotations), 170 (markup) and the per-subtype tables 172-190,
# plus ISO 32000-2 additions, and the field keys a merged Widget/field dictionary carries.
STANDARD_ANNOT_KEYS = frozenset(
	(
		# Table 164, common
		"/Type",
		"/Subtype",
		"/Rect",
		"/Contents",
		"/P",
		"/NM",
		"/M",
		"/F",
		"/AP",
		"/AS",
		"/Border",
		"/C",
		"/StructParent",
		"/OC",
		"/AF",
		"/ca",
		"/CA",
		"/BM",
		"/Lang",
		# Table 170, markup
		"/T",
		"/Popup",
		"/RC",
		"/CreationDate",
		"/IRT",
		"/Subj",
		"/RT",
		"/IT",
		"/ExData",
		# Text, Link, FreeText, Line, Square/Circle, Polygon/PolyLine, markup text, Caret,
		# Rubber stamp, Ink, Popup, File attachment, Sound, Movie, Screen, Widget, Printer mark,
		# Trap network, Watermark, Redact, 3D, RichMedia, Projection
		"/Open",
		"/Name",
		"/State",
		"/StateModel",
		"/A",
		"/AA",
		"/Dest",
		"/H",
		"/PA",
		"/QuadPoints",
		"/BS",
		"/DA",
		"/Q",
		"/DS",
		"/CL",
		"/BE",
		"/RD",
		"/LE",
		"/L",
		"/IC",
		"/LL",
		"/LLE",
		"/Cap",
		"/LLO",
		"/CP",
		"/Measure",
		"/CO",
		"/Vertices",
		"/Path",
		"/Sy",
		"/InkList",
		"/Parent",
		"/FS",
		"/Sound",
		"/Movie",
		"/MK",
		"/MN",
		"/LastModified",
		"/Version",
		"/AnnotStates",
		"/FontFauxing",
		"/FixedPrint",
		"/RO",
		"/OverlayText",
		"/Repeat",
		"/3DD",
		"/3DV",
		"/3DA",
		"/3DI",
		"/3DB",
		"/3DU",
		"/GEO",
		"/RichMediaSettings",
		"/RichMediaContent",
		# Field dictionary keys (Widget annotations merged with their field)
		"/FT",
		"/Ff",
		"/V",
		"/DV",
		"/TU",
		"/TM",
		"/Kids",
		"/Opt",
		"/MaxLen",
		"/TI",
		"/I",
		"/RV",
		"/Lock",
		"/SV",
	)
)
STANDARD_PAGE_KEYS = frozenset(
	(
		"/Type",
		"/Parent",
		"/LastModified",
		"/Resources",
		"/MediaBox",
		"/CropBox",
		"/BleedBox",
		"/TrimBox",
		"/ArtBox",
		"/BoxColorInfo",
		"/Contents",
		"/Rotate",
		"/Group",
		"/Thumb",
		"/B",
		"/Dur",
		"/Trans",
		"/Annots",
		"/AA",
		"/Metadata",
		"/PieceInfo",
		"/StructParents",
		"/ID",
		"/PZ",
		"/SeparationInfo",
		"/Tabs",
		"/TemplateInstantiated",
		"/PresSteps",
		"/UserUnit",
		"/VP",
		"/AF",
		"/OutputIntents",
		"/DPart",
	)
)
STANDARD_CATALOG_KEYS = frozenset(
	(
		"/Type",
		"/Version",
		"/Extensions",
		"/Pages",
		"/PageLabels",
		"/Names",
		"/Dests",
		"/ViewerPreferences",
		"/PageLayout",
		"/PageMode",
		"/Outlines",
		"/Threads",
		"/OpenAction",
		"/AA",
		"/URI",
		"/AcroForm",
		"/Metadata",
		"/StructTreeRoot",
		"/MarkInfo",
		"/Lang",
		"/SpiderInfo",
		"/OutputIntents",
		"/PieceInfo",
		"/OCProperties",
		"/Perms",
		"/Legal",
		"/Requirements",
		"/Collection",
		"/NeedsRendering",
		"/DSS",
		"/AF",
		"/DPartRoot",
	)
)
STANDARD_VIEWPORT_KEYS = frozenset(("/Type", "/BBox", "/Name", "/Measure", "/PtData"))
STANDARD_MEASURE_KEYS = frozenset(
	(
		"/Type",
		"/Subtype",
		"/R",
		"/X",
		"/Y",
		"/D",
		"/A",
		"/T",
		"/S",
		"/O",
		"/CYX",
		"/Bounds",
		"/GCS",
		"/DCS",
		"/GPTS",
		"/LPTS",
		"/PDU",
	)
)
NON_MARKUP_SUBTYPES = frozenset(
	("/Link", "/Widget", "/Popup", "/PrinterMark", "/TrapNet", "/Watermark", "/Screen", "/Movie")
)
MEASURED_SUBTYPES = frozenset(("/PolyLine", "/Polygon", "/Line"))

UNIT_TO_IN = {
	"in": 1.0,
	"inch": 1.0,
	"inches": 1.0,
	'"': 1.0,
	"ft": 12.0,
	"feet": 12.0,
	"foot": 12.0,
	"'": 12.0,
	"yd": 36.0,
	"yard": 36.0,
	"yards": 36.0,
	"mm": 1 / 25.4,
	"cm": 1 / 2.54,
	"m": 1 / 0.0254,
	"meter": 1 / 0.0254,
	"meters": 1 / 0.0254,
	"metre": 1 / 0.0254,
	"metres": 1 / 0.0254,
}

_NUM = r"\d+(?:\.\d+)?"
_FRAC = r"\d+/\d+"
_UNIT_END = r"(?![A-Za-z])"
_FEET_INCHES = re.compile(
	rf"(?P<ft>{_NUM})\s*(?:'|ft\.?{_UNIT_END}|feet{_UNIT_END})"
	rf"(?:\s*-?\s*(?:(?P<inch>{_NUM})(?:\s+(?P<frac>{_FRAC}))?|(?P<frac_only>{_FRAC}))"
	rf"\s*(?:\"|in\.?{_UNIT_END}|inch(?:es)?{_UNIT_END}))?",
	re.IGNORECASE,
)
_INCHES = re.compile(
	rf"(?:(?P<inch>{_NUM})(?:\s+(?P<frac>{_FRAC}))?|(?P<frac_only>{_FRAC}))"
	rf"\s*(?:\"|in\.?{_UNIT_END}|inch(?:es)?{_UNIT_END})",
	re.IGNORECASE,
)
_METRIC = re.compile(rf"(?P<value>{_NUM})\s*(?P<unit>mm|cm|m){_UNIT_END}", re.IGNORECASE)


class PdfRefused(ValueError):
	"""The file failed one of the portal's safety checks and was not probed."""


# --------------------------------------------------------------------------- value helpers


def _generic():
	from pypdf import generic

	return generic


def resolve(obj, limit=16):
	"""Follow indirect references (bounded); a broken reference resolves to None."""
	generic = _generic()
	for _ in range(limit):
		if not isinstance(obj, generic.IndirectObject):
			break
		obj = obj.get_object()
	if isinstance(obj, (generic.IndirectObject, generic.NullObject)):
		return None
	return obj


def _is_dict(obj):
	return isinstance(obj, _generic().DictionaryObject)


def _is_array(obj):
	return isinstance(obj, (_generic().ArrayObject, list))


def _ref(obj):
	if isinstance(obj, _generic().IndirectObject):
		return f"{obj.idnum} {obj.generation} R"
	return None


def to_json(obj, depth=0, seen=frozenset()):
	"""Convert a pypdf object to JSON-safe data without executing or rendering anything.

	Names keep their leading slash (``"/PolyLine"``) so they stay distinct from strings; byte
	strings that are not valid text become ``{"hex": ...}``; streams are summarised, with a short
	decoded preview; references are followed with a cycle guard and a depth limit.
	"""
	generic = _generic()
	if isinstance(obj, generic.IndirectObject):
		key = (obj.idnum, obj.generation)
		if key in seen or depth >= MAX_DEPTH:
			return {"ref": _ref(obj)}
		try:
			target = obj.get_object()
		except Exception as exc:
			return {"ref": _ref(obj), "error": str(exc)[:200]}
		return to_json(target, depth + 1, seen | {key})
	if obj is None or isinstance(obj, generic.NullObject):
		return None
	if isinstance(obj, generic.BooleanObject):
		return bool(obj)
	if isinstance(obj, bool):
		return obj
	if isinstance(obj, generic.NameObject):
		return str(obj)
	if isinstance(obj, generic.ByteStringObject):
		raw = bytes(obj)
		try:
			return raw.decode("utf-8")
		except UnicodeDecodeError:
			return {"hex": raw[:VALUE_LIMIT].hex()}
	if isinstance(obj, str):
		return str(obj)
	if isinstance(obj, int):
		return int(obj)
	if isinstance(obj, float):
		value = float(obj)
		return value if math.isfinite(value) else str(value)
	if isinstance(obj, generic.StreamObject):
		summary = {"stream": True}
		if depth < MAX_DEPTH:
			summary["dict"] = {
				str(k): to_json(v, depth + 1, seen) for k, v in list(obj.items())[:MAX_DICT_ITEMS]
			}
		try:
			data = obj.get_data()
			summary["length"] = len(data)
			summary["preview"] = data[:VALUE_LIMIT].decode("utf-8", errors="replace")
		except Exception as exc:
			summary["error"] = str(exc)[:200]
		return summary
	if isinstance(obj, generic.DictionaryObject):
		if depth >= MAX_DEPTH:
			return {"depth_limit": True, "keys": [str(k) for k in list(obj.keys())[:MAX_DICT_ITEMS]]}
		return {str(k): to_json(v, depth + 1, seen) for k, v in list(obj.items())[:MAX_DICT_ITEMS]}
	if _is_array(obj):
		if depth >= MAX_DEPTH:
			return {"depth_limit": True, "length": len(obj)}
		return [to_json(v, depth + 1, seen) for v in list(obj)[:MAX_ARRAY_ITEMS]]
	return str(obj)[:VALUE_LIMIT]


def clip(value):
	"""Keep a JSON value whole when it serialises to at most 500 chars, else a preview."""
	text = json.dumps(value, ensure_ascii=False, default=str)
	if len(text) <= VALUE_LIMIT:
		return value
	return {"truncated": True, "chars": len(text), "preview": text[:VALUE_LIMIT]}


def number(obj):
	obj = resolve(obj)
	if obj is None or isinstance(obj, (bool, _generic().BooleanObject)):
		return None
	value = float(obj)
	if not math.isfinite(value):
		raise ValueError(f"non-finite number {obj!r}")
	return value


def numbers(obj, expected=None):
	obj = resolve(obj)
	if obj is None:
		return None
	if not _is_array(obj):
		raise ValueError(f"expected an array, got {type(obj).__name__}")
	values = [number(item) for item in list(obj)[: MAX_ARRAY_ITEMS * 10]]
	if any(value is None for value in values):
		raise ValueError("array contains a non-number")
	if expected is not None and len(values) != expected:
		raise ValueError(f"expected {expected} numbers, got {len(values)}")
	return values


def text(obj):
	obj = resolve(obj)
	if obj is None:
		return None
	value = to_json(obj)
	if isinstance(value, str):
		return value
	return json.dumps(value, ensure_ascii=False)[:VALUE_LIMIT]


def _extra(dictionary, standard):
	return {str(k): clip(to_json(v)) for k, v in dictionary.items() if str(k) not in standard}


def _pairs(values):
	if len(values) % 2:
		raise ValueError(f"odd number of coordinates ({len(values)})")
	return [[values[i], values[i + 1]] for i in range(0, len(values), 2)]


def _record(errors, label, fn, default=None):
	try:
		return fn()
	except Exception as exc:
		errors.append(f"{label}: {type(exc).__name__}: {str(exc)[:200]}")
		return default


# --------------------------------------------------------------------------- measure model


def number_formats(obj):
	"""A number format array (Table 262) as a list of dicts; C is a float when present."""
	obj = resolve(obj)
	if obj is None:
		return None
	items = [obj] if _is_dict(obj) else list(obj) if _is_array(obj) else None
	if items is None:
		raise ValueError("number format is neither an array nor a dictionary")
	formats = []
	for item in items[:20]:
		item = resolve(item)
		if not _is_dict(item):
			raise ValueError("number format entry is not a dictionary")
		entry = {str(k).lstrip("/"): clip(to_json(v)) for k, v in item.items()}
		entry["U"] = text(item.get("/U"))
		entry["C"] = number(item.get("/C"))
		formats.append(entry)
	return formats


def parse_measure(obj, errors, label):
	measure = resolve(obj)
	if measure is None:
		return None
	if not _is_dict(measure):
		errors.append(f"{label}: /Measure is not a dictionary")
		return None
	out = {"Subtype": text(measure.get("/Subtype")) or "/RL", "R": text(measure.get("/R"))}
	for key in ("X", "Y", "D", "A", "T", "S"):
		out[key] = _record(errors, f"{label}./{key}", lambda key=key: number_formats(measure.get(f"/{key}")))
	out["O"] = _record(errors, f"{label}./O", lambda: numbers(measure.get("/O")))
	out["CYX"] = _record(errors, f"{label}./CYX", lambda: number(measure.get("/CYX")))
	if out["Subtype"] == "/GEO":
		out["geo"] = clip(to_json(measure))
	out["extra_keys"] = _extra(measure, STANDARD_MEASURE_KEYS)
	return out


def scale(measure):
	"""Return the factors of the §12.9 distance formula, or raise ValueError saying why not."""
	if measure is None:
		raise ValueError("no measure applies")
	if measure.get("Subtype") != "/RL":
		raise ValueError(f"measure subtype {measure.get('Subtype')} is not computed")
	x_formats = measure.get("X") or []
	if not x_formats or x_formats[0].get("C") is None:
		raise ValueError("measure has no /X[0] /C conversion factor")
	notes = []
	fx = x_formats[0]["C"]
	fy = fx
	y_formats = measure.get("Y") or []
	if y_formats and y_formats[0].get("C") is not None:
		cyx = measure.get("CYX")
		if cyx is None:
			notes.append("/Y present without /CYX; assumed CYX = 1")
			cyx = 1.0
		fy = y_formats[0]["C"] * cyx
	d_formats = measure.get("D") or []
	if d_formats and d_formats[0].get("C") is not None:
		d_factor, unit = d_formats[0]["C"], d_formats[0].get("U")
	else:
		notes.append("measure has no /D[0] /C; length reported in /X[0] units")
		d_factor, unit = 1.0, x_formats[0].get("U")
	a_formats = measure.get("A") or []
	if a_formats and a_formats[0].get("C") is not None:
		a_factor, a_unit = a_formats[0]["C"], a_formats[0].get("U")
	else:
		x_unit = x_formats[0].get("U")
		a_factor, a_unit = 1.0, f"{x_unit}^2" if x_unit else None
	return {
		"fx": fx,
		"fy": fy,
		"d": d_factor,
		"unit": unit,
		"a": a_factor,
		"area_unit": a_unit,
		"notes": notes,
	}


def unit_to_inches(unit):
	if not unit:
		return None
	return UNIT_TO_IN.get(unit.strip().lower().rstrip("."))


def _bezier_length(p0, p1, p2, p3, steps=BEZIER_STEPS):
	total, previous = 0.0, p0
	for step in range(1, steps + 1):
		t = step / steps
		u = 1 - t
		point = (
			u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
			u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1],
		)
		total += math.hypot(point[0] - previous[0], point[1] - previous[1])
		previous = point
	return total


def path_length(path, fx, fy):
	"""Length in /X units of a PDF 2.0 /Path (moveto/lineto pairs and 6-number curveto)."""
	total, current = 0.0, None
	for entry in path:
		points = [(entry[i] * fx, entry[i + 1] * fy) for i in range(0, len(entry), 2)]
		if len(points) == 1:
			if current is not None:
				total += math.hypot(points[0][0] - current[0], points[0][1] - current[1])
			current = points[0]
		elif len(points) == 3 and current is not None:
			total += _bezier_length(current, *points)
			current = points[2]
		else:
			raise ValueError(f"/Path entry with {len(entry)} numbers")
	return total


def polyline_length(vertices, fx, fy, closed=False):
	points = [(x * fx, y * fy) for x, y in vertices]
	if closed and len(points) > 2:
		points.append(points[0])
	return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in pairwise(points))


def shoelace(vertices, fx, fy):
	points = [(x * fx, y * fy) for x, y in vertices]
	total = 0.0
	for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1], strict=False):
		total += x1 * y2 - x2 * y1
	return abs(total) / 2


def _normalised_box(box):
	if not box or len(box) != 4:
		return None
	return min(box[0], box[2]), min(box[1], box[3]), max(box[0], box[2]), max(box[1], box[3])


def viewport_for(point, viewports):
	"""The last viewport whose /BBox contains the point (ISO 32000-1 §12.9.2)."""
	for viewport in reversed(viewports):
		box = _normalised_box(viewport.get("BBox"))
		if box and box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]:
			return viewport
	return None


def parse_length_text(value):
	"""Heuristic: the first length written in a string (12' 6", 12'-6 1/2", 150.5", 3.81 m), in inches."""
	if not value:
		return None
	value = re.sub(r"(?<=\d),(?=\d{3})", "", value)
	candidates = []
	match = _FEET_INCHES.search(value)
	if match:
		inches = float(match["ft"]) * 12 + float(match["inch"] or 0)
		fraction = match["frac"] or match["frac_only"]
		candidates.append((match.start(), inches + _fraction(fraction)))
	match = _INCHES.search(value)
	if match:
		fraction = match["frac"] or match["frac_only"]
		candidates.append((match.start(), float(match["inch"] or 0) + _fraction(fraction)))
	match = _METRIC.search(value)
	if match:
		candidates.append((match.start(), float(match["value"]) * UNIT_TO_IN[match["unit"].lower()]))
	if not candidates:
		return None
	return round(min(candidates)[1], 6)


def _fraction(value):
	if not value:
		return 0.0
	numerator, denominator = value.split("/")
	return float(numerator) / float(denominator) if float(denominator) else 0.0


# --------------------------------------------------------------------------- page walk


def parse_viewport(index, obj, errors):
	label = f"VP[{index}]"
	viewport = resolve(obj)
	if not _is_dict(viewport):
		errors.append(f"{label}: not a dictionary")
		return None
	return {
		"index": index,
		"Name": _record(errors, f"{label}./Name", lambda: text(viewport.get("/Name"))),
		"BBox": _record(errors, f"{label}./BBox", lambda: numbers(viewport.get("/BBox"), 4)),
		"Measure": parse_measure(viewport.get("/Measure"), errors, f"{label}./Measure"),
		"extra_keys": _extra(viewport, STANDARD_VIEWPORT_KEYS),
	}


def _vertices(annot, subtype):
	if subtype == "/Line":
		values = numbers(annot.get("/L"), 4)
		return (_pairs(values), "/L") if values else (None, None)
	values = numbers(annot.get("/Vertices"))
	if values:
		return _pairs(values), "/Vertices"
	return None, None


def _path(annot):
	path = resolve(annot.get("/Path"))
	if path is None:
		return None
	if not _is_array(path):
		raise ValueError("/Path is not an array")
	return [numbers(entry) for entry in list(path)[:MAX_ARRAY_ITEMS]]


def _bs_width(annot):
	border_style = resolve(annot.get("/BS"))
	if _is_dict(border_style) and border_style.get("/W") is not None:
		return number(border_style.get("/W"))
	border = numbers(annot.get("/Border"))
	if border and len(border) >= 3:
		return border[2]
	return None


def _layer(annot):
	content = resolve(annot.get("/OC"))
	if not _is_dict(content):
		return None
	if content.get("/Name") is not None:
		return text(content.get("/Name"))
	return clip(to_json(content))


def _measure_lengths(out, measure, source, page_errors, label):
	out["measure_source"] = source
	if out["vertices"] is None and out["path"] is None:
		out["length_note"] = "no vertices"
		return
	try:
		factors = scale(measure)
	except ValueError as exc:
		out["length_note"] = str(exc)
		return
	fx, fy = factors["fx"], factors["fy"]
	try:
		if out["path"]:
			length_x = path_length(out["path"], fx, fy)
			out["length_basis"] = "/Path"
		else:
			length_x = polyline_length(out["vertices"], fx, fy, closed=out["Subtype"] == "/Polygon")
			out["length_basis"] = out["vertex_source"]
	except Exception as exc:
		page_errors.append(f"{label}: length: {exc}")
		return
	out["computed_length"] = round(length_x * factors["d"], 6)
	out["computed_unit"] = factors["unit"]
	inches = unit_to_inches(factors["unit"])
	out["computed_length_in"] = round(out["computed_length"] * inches, 6) if inches else None
	if out["Subtype"] == "/Polygon" and out["vertices"] and len(out["vertices"]) > 2:
		out["computed_area"] = round(shoelace(out["vertices"], fx, fy) * factors["a"], 6)
		out["computed_area_unit"] = factors["area_unit"]
	if factors["notes"]:
		out["length_note"] = "; ".join(factors["notes"])


def parse_annotation(index, ref, viewports, page_errors):
	label = f"annot[{index}]"
	annot = resolve(ref)
	if not _is_dict(annot):
		page_errors.append(f"{label}: not a dictionary")
		return None

	def field(name, fn):
		return _record(page_errors, f"{label}.{name}", fn)

	subtype = field("/Subtype", lambda: text(annot.get("/Subtype")))
	out = {
		"index": index,
		"ref": _ref(ref),
		"Subtype": subtype,
		"Subj": field("/Subj", lambda: text(annot.get("/Subj"))),
		"NM": field("/NM", lambda: text(annot.get("/NM"))),
		"T": field("/T", lambda: text(annot.get("/T"))),
		"Contents": field("/Contents", lambda: text(annot.get("/Contents"))),
		"IT": field("/IT", lambda: text(annot.get("/IT"))),
		"Rect": field("/Rect", lambda: numbers(annot.get("/Rect"), 4)),
		"vertices": None,
		"vertex_source": None,
		"path": field("/Path", lambda: _path(annot)),
		"BS_width": field("/BS", lambda: _bs_width(annot)),
		"C": field("/C", lambda: numbers(annot.get("/C"))),
		"CreationDate": field("/CreationDate", lambda: text(annot.get("/CreationDate"))),
		"M": field("/M", lambda: text(annot.get("/M"))),
		"layer": field("/OC", lambda: _layer(annot)),
		"has_actions": "/A" in annot or "/AA" in annot,
		"Measure": parse_measure(annot.get("/Measure"), page_errors, f"{label}./Measure"),
		"extra_keys": field("extra_keys", lambda: _extra(annot, STANDARD_ANNOT_KEYS)) or {},
		"computed_length": None,
		"computed_unit": None,
		"computed_length_in": None,
		"contents_length_in": None,
	}
	vertices = field("vertices", lambda: _vertices(annot, subtype))
	if vertices:
		out["vertices"], out["vertex_source"] = vertices
	out["contents_length_in"] = _record(
		page_errors, f"{label}.contents_length", lambda: parse_length_text(out["Contents"])
	)
	if subtype in MEASURED_SUBTYPES:
		first = None
		if out["vertices"]:
			first = out["vertices"][0]
		elif out["path"] and len(out["path"][0]) >= 2:
			first = out["path"][0][:2]
		if out["Measure"] is not None:
			_measure_lengths(out, out["Measure"], "annotation", page_errors, label)
		else:
			viewport = viewport_for(first, viewports) if first else None
			measure = viewport["Measure"] if viewport else None
			source = f"viewport[{viewport['index']}]" if viewport else None
			_measure_lengths(out, measure, source, page_errors, label)
			if viewport:
				out["viewport_name"] = viewport["Name"]
	return out


def parse_page(number_, page):
	errors = []
	info = {"page": number_}
	info["MediaBox"] = _record(errors, "/MediaBox", lambda: [float(v) for v in page.mediabox])
	info["CropBox"] = _record(errors, "/CropBox", lambda: [float(v) for v in page.cropbox])
	info["UserUnit"] = _record(errors, "/UserUnit", lambda: number(page.get("/UserUnit")) or 1.0, 1.0)
	info["rotation"] = _record(errors, "/Rotate", lambda: int(page.rotation))
	notes = []
	if info["UserUnit"] not in (None, 1.0):
		notes.append("UserUnit != 1: confirm Revu's /C factors already include it")
	viewports = []
	raw_vp = _record(errors, "/VP", lambda: resolve(page.get("/VP")))
	if raw_vp is not None:
		if _is_array(raw_vp):
			for index, item in enumerate(list(raw_vp)[:MAX_ARRAY_ITEMS]):
				viewport = _record(
					errors, f"VP[{index}]", lambda item=item, index=index: parse_viewport(index, item, errors)
				)
				if viewport:
					viewports.append(viewport)
		else:
			errors.append("/VP: not an array")
	info["viewports"] = viewports
	annotations = []
	raw_annots = _record(errors, "/Annots", lambda: resolve(page.get("/Annots")))
	if raw_annots is not None:
		if _is_array(raw_annots):
			items = list(raw_annots)
			if len(items) > MAX_ANNOTS_PER_PAGE:
				errors.append(f"/Annots: {len(items)} annotations, only the first {MAX_ANNOTS_PER_PAGE} read")
			for index, ref in enumerate(items[:MAX_ANNOTS_PER_PAGE]):
				annot = _record(
					errors,
					f"annot[{index}]",
					lambda ref=ref, index=index: parse_annotation(index, ref, viewports, errors),
				)
				if annot:
					annotations.append(annot)
		else:
			errors.append("/Annots: not an array")
	info["annotations"] = annotations
	info["extra_keys"] = _record(errors, "page extra keys", lambda: _extra(page, STANDARD_PAGE_KEYS), {})
	info["PieceInfo"] = _record(errors, "/PieceInfo", lambda: clip(to_json(page.get("/PieceInfo"))))
	info["notes"] = notes
	info["errors"] = errors
	return info


# --------------------------------------------------------------------------- document


def _read_source(path_or_bytes):
	if isinstance(path_or_bytes, (bytes, bytearray, memoryview)):
		content, name = bytes(path_or_bytes), None
	else:
		path = Path(path_or_bytes)
		size = os.stat(path).st_size
		if size > MAX_BYTES:
			raise PdfRefused(f"File is {size} bytes; the probe reads at most {MAX_BYTES}")
		content, name = path.read_bytes(), path.name
	if not content or len(content) > MAX_BYTES:
		raise PdfRefused(f"File must contain between 1 byte and {MAX_BYTES} bytes")
	if not content.startswith(b"%PDF-"):
		raise PdfRefused("Not a PDF (missing %PDF- header)")
	return content, name


def _open(content, lenient):
	"""Apply the portal's PDF checks (portal/file_validation.py validate_content)."""
	from pypdf import PdfReader

	checks = {"strict_parse": "ok"}

	def load(strict):
		reader = PdfReader(io.BytesIO(content), strict=strict)
		encrypted = reader.is_encrypted
		return reader, encrypted, (None if encrypted else len(reader.pages))

	try:
		reader, encrypted, count = load(True)
	except Exception as exc:
		if not lenient:
			raise PdfRefused(f"PDF failed strict parsing: {exc}") from exc
		checks["strict_parse"] = f"failed (portal would refuse): {str(exc)[:300]}"
		try:
			reader, encrypted, count = load(False)
		except Exception as exc2:
			raise PdfRefused(f"PDF could not be parsed: {exc2}") from exc2
	if encrypted:
		raise PdfRefused("Encrypted PDFs are not supported")
	if not 1 <= count <= MAX_PAGES:
		raise PdfRefused(f"PDF must have 1 to {MAX_PAGES} pages (has {count})")
	try:
		root = resolve(reader.trailer["/Root"])
		names = resolve(root.get("/Names")) or {}
		has_actions = bool(root.get("/OpenAction") or root.get("/AA") or names.get("/JavaScript"))
	except Exception as exc:
		raise PdfRefused(f"PDF catalog could not be checked: {exc}") from exc
	if has_actions:
		raise PdfRefused("PDF actions are not supported (/OpenAction, /AA or /JavaScript)")
	checks.update({"encrypted": False, "pages": count, "document_actions": False})
	return reader, root, checks


def _document(reader, root, errors):
	info = {}
	raw_info = _record(errors, "/Info", lambda: resolve(reader.trailer.get("/Info")))
	if _is_dict(raw_info):
		for key in ("/Producer", "/Creator", "/CreationDate", "/ModDate"):
			info[key.lstrip("/")] = _record(errors, f"/Info{key}", lambda key=key: text(raw_info.get(key)))
	layers = []

	def read_layers():
		properties = resolve(root.get("/OCProperties"))
		if not _is_dict(properties):
			return
		for group in list(resolve(properties.get("/OCGs")) or [])[:MAX_ARRAY_ITEMS]:
			group = resolve(group)
			if _is_dict(group):
				layers.append(text(group.get("/Name")))

	_record(errors, "/OCProperties", read_layers)
	return {
		"pdf_header": _record(errors, "header", lambda: reader.pdf_header),
		"info": info,
		"layers": layers,
		"catalog_extra_keys": _record(
			errors, "catalog extra keys", lambda: _extra(root, STANDARD_CATALOG_KEYS), {}
		),
		"catalog_PieceInfo": _record(errors, "/PieceInfo", lambda: clip(to_json(root.get("/PieceInfo")))),
	}


def _count(values):
	return dict(Counter("(none)" if value is None else str(value) for value in values).most_common())


def summarise(pages, document):
	annotations = [annot for page in pages for annot in page["annotations"]]
	markups = [annot for annot in annotations if annot["Subtype"] not in NON_MARKUP_SUBTYPES]
	extra_names = Counter(key for annot in annotations for key in annot["extra_keys"])
	return {
		"pages": len(pages),
		"annotations": len(annotations),
		"markup_annotations": len(markups),
		"by_subtype": _count(a["Subtype"] for a in annotations),
		"by_intent": _count(a["IT"] for a in annotations),
		"by_subject": _count(a["Subj"] for a in annotations),
		"by_measure_source": _count(
			a.get("measure_source") for a in annotations if a["Subtype"] in MEASURED_SUBTYPES
		),
		"measured_markups": sum(1 for a in annotations if a["computed_length"] is not None),
		"extra_key_names": dict(extra_names.most_common()),
		"flattened_or_empty": not annotations,
		"no_markups": not markups,
		"has_viewports": any(page["viewports"] for page in pages),
		"has_measures": any(vp["Measure"] for page in pages for vp in page["viewports"])
		or any(a["Measure"] for a in annotations),
		"layers": len(document["layers"]),
		"errors": sum(len(page["errors"]) for page in pages),
	}


def probe(path_or_bytes, *, lenient=False):
	"""Probe a PDF and return a JSON-safe report. Raises ``PdfRefused`` if a safety check fails."""
	content, name = _read_source(path_or_bytes)
	reader, root, checks = _open(content, lenient)
	errors = []
	document = _document(reader, root, errors)
	pages = []
	for index in range(checks["pages"]):
		try:
			page = reader.pages[index]
		except Exception as exc:
			pages.append({"page": index + 1, "viewports": [], "annotations": [], "errors": [f"page: {exc}"]})
			continue
		pages.append(parse_page(index + 1, page))
	return {
		"tool": "tools.bluebeam_spike.probe_pdf",
		"report_version": 1,
		"source": {"name": name, "size": len(content), "sha256": hashlib.sha256(content).hexdigest()},
		"portal_checks": checks,
		"document": document,
		"summary": summarise(pages, document),
		"pages": pages,
		"errors": errors,
	}


def main(argv=None):
	parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
	parser.add_argument("pdf", help="marked-up PDF to probe (never executed)")
	parser.add_argument("--out", help="write the JSON report here instead of stdout")
	parser.add_argument(
		"--lenient",
		action="store_true",
		help="if strict parsing fails, record why and retry non-strict (the portal would refuse it)",
	)
	args = parser.parse_args(argv)
	try:
		report = probe(args.pdf, lenient=args.lenient)
	except PdfRefused as exc:
		print(f"refused: {exc}", file=sys.stderr)
		return 2
	except OSError as exc:
		print(f"error: {exc}", file=sys.stderr)
		return 1
	payload = json.dumps(report, indent=2, ensure_ascii=False)
	if args.out:
		Path(args.out).write_text(payload + "\n", encoding="utf-8")
	else:
		print(payload)
	summary = report["summary"]
	print(
		f"{summary['pages']} page(s), {summary['annotations']} annotation(s), "
		f"{summary['measured_markups']} measured; viewports={summary['has_viewports']} "
		f"measures={summary['has_measures']} flattened_or_empty={summary['flattened_or_empty']} "
		f"errors={summary['errors']}",
		file=sys.stderr,
	)
	return 0


if __name__ == "__main__":
	sys.exit(main())
