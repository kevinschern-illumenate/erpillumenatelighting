"""Fill a generated spec sheet for one schedule line, on the server.

The generated spec sheets (n8n plus the PDF generator; plan 4.20) carry form fields:

- ``project_name``, ``fixture_type``, ``project_location`` (and, once the generator adds it,
  ``line_summary``): one text field each with a widget on every page;
- ``step_N``: a radio group per Part Number Builder step. Its ``/Opt`` lists the option codes
  in order, and the widget states are their indexes (``/0``, ``/1``, ...), not the codes;
- ``display_step_N``: the code box above each step (the fixture Length is a free text box);
- the PDF Subject: a JSON list of highlight boxes ``{code, pageIndex, x, y, width, height,
  isRow}``, where ``code`` holds space-separated ``<step>:<code>`` tags.

``fill`` does on the server what ``webflow_scripts/configured-spec-sheet.html`` does in the
visitor's browser, then flattens the sheet so copies merged into one packet cannot share
field values. It needs only pypdf and has no Frappe lookups.
"""

import io
import json

TEXT_FIELDS = ("project_name", "fixture_type", "project_location", "line_summary")
STEP_PREFIX = "step_"
DISPLAY_PREFIX = "display_step_"
HIGHLIGHT_RGB = (1, 0.92, 0.25)
HIGHLIGHT_OPACITY = 0.3


def _writer(source):
	from pypdf import PdfWriter

	return PdfWriter(clone_from=io.BytesIO(source))


def _fields(writer):
	form = writer._root_object.get("/AcroForm")
	if not form:
		return {}
	form = form.get_object()
	fields = {}

	def walk(refs, prefix=""):
		for ref in refs or []:
			field = ref.get_object()
			name = field.get("/T")
			full = f"{prefix}.{name}" if prefix and name else (name or prefix)
			kids = field.get("/Kids") or []
			# A kid with its own /T is a child field; without it, a widget of this field.
			if any("/T" in kid.get_object() for kid in kids):
				walk(kids, full)
			elif full:
				fields[str(full)] = field

	walk(form.get("/Fields"))
	return fields


def _field_type(field):
	value = field.get("/FT")
	parent = field.get("/Parent")
	while value is None and parent is not None:
		parent = parent.get_object()
		value = parent.get("/FT")
		parent = parent.get("/Parent")
	return str(value or "")


def _options(field):
	return [str(option) for option in field.get("/Opt") or []]


def _subject_boxes(writer_or_reader):
	try:
		metadata = writer_or_reader.metadata or {}
		boxes = json.loads(metadata.get("/Subject") or "[]")
	except (ValueError, TypeError, AttributeError):
		return []
	return [box for box in boxes if isinstance(box, dict)] if isinstance(boxes, list) else []


def _highlight_style(boxes):
	if not boxes:
		return "none"
	tagged = any(":" in str(box.get("code") or "") for box in boxes)
	return "steps" if tagged else "rows"


def inspect(source):
	"""What a sheet offers the fill: its text fields, its steps and their codes, its highlight style."""
	from pypdf import PdfReader

	reader = PdfReader(io.BytesIO(source))
	info = {
		"has_form": False,
		"pages": len(reader.pages),
		"text_fields": [],
		"steps": {},
		"display_steps": [],
		"highlight_style": _highlight_style(_subject_boxes(reader)),
	}
	form = reader.trailer["/Root"].get("/AcroForm")
	if not form:
		return info
	fields = reader.get_fields() or {}
	info["has_form"] = bool(fields)
	for name, field in fields.items():
		kind = str(field.get("/FT") or "")
		if name.startswith(STEP_PREFIX):
			step = name[len(STEP_PREFIX) :]
			if kind == "/Btn":
				info["steps"][step] = _options(field)
			elif kind == "/Tx":
				info["steps"][step] = []
		elif name.startswith(DISPLAY_PREFIX):
			info["display_steps"].append(name[len(DISPLAY_PREFIX) :])
		elif kind == "/Tx":
			info["text_fields"].append(name)
	return info


def _widgets(field):
	return [kid.get_object() for kid in field.get("/Kids") or []] or [field]


def _page_of(writer, widget):
	for page in writer.pages:
		for annot in page.get("/Annots") or []:
			if annot.get_object() is widget:
				return page
	return None


def _append_content(writer, page, data):
	"""Draw ``data`` over the page. The page's own content is wrapped in q/Q once, so its graphics
	state cannot leak into what is drawn here."""
	from pypdf.generic import ArrayObject, DecodedStreamObject, NameObject

	def stream(raw):
		item = DecodedStreamObject()
		item.set_data(raw)
		return writer._add_object(item)

	contents = page.get("/Contents")
	if contents is None:
		existing = ArrayObject()
	else:
		resolved = contents.get_object()
		existing = ArrayObject(resolved) if isinstance(resolved, ArrayObject) else ArrayObject([contents])
	if not page.get("/IllWrapped"):
		existing = ArrayObject([stream(b"q\n"), *existing, stream(b"\nQ\n")])
		page[NameObject("/IllWrapped")] = NameObject("/true")
	page[NameObject("/Contents")] = ArrayObject([*existing, stream(data)])


def _resources(page, kind):
	from pypdf.generic import DictionaryObject, NameObject

	resources = page.get("/Resources")
	resources = resources.get_object() if resources is not None else DictionaryObject()
	page[NameObject("/Resources")] = resources
	entry = resources.get(kind)
	entry = entry.get_object() if entry is not None else DictionaryObject()
	resources[NameObject(kind)] = entry
	return entry


def _stamp_appearance(writer, page, widget, state, counter):
	"""Draw a widget's appearance for ``state`` into the page, where the widget sits.

	pypdf's own flattening draws radio groups with several options wrongly (only one-option
	groups showed as selected), so selected radios are drawn here before widgets are removed.
	"""
	from pypdf.generic import NameObject

	appearance = (widget.get("/AP") or {}).get("/N")
	appearance = appearance.get_object() if appearance is not None else None
	if appearance is None or state not in appearance:
		return False
	stream = appearance[state]
	stream_object = stream.get_object()
	x1, y1, x2, y2 = (float(value) for value in widget["/Rect"])
	bbox = [float(value) for value in stream_object.get("/BBox") or (0, 0, x2 - x1, y2 - y1)]
	scale_x = (x2 - x1) / ((bbox[2] - bbox[0]) or 1)
	scale_y = (y2 - y1) / ((bbox[3] - bbox[1]) or 1)
	name = f"/IllFill{counter}"
	reference = stream if hasattr(stream, "idnum") else writer._add_object(stream_object)
	_resources(page, "/XObject")[NameObject(name)] = reference
	offset_x = x1 - bbox[0] * scale_x
	offset_y = y1 - bbox[1] * scale_y
	_append_content(
		writer,
		page,
		f"q {scale_x:.6f} 0 0 {scale_y:.6f} {offset_x:.4f} {offset_y:.4f} cm {name} Do Q\n".encode(),
	)
	return True


def _draw_highlights(writer, boxes, tokens):
	from pypdf.generic import DictionaryObject, FloatObject, NameObject

	drawn = 0
	pages = list(writer.pages)
	by_page = {}
	for box in boxes:
		tags = {tag.lower() for tag in str(box.get("code") or "").split()}
		if not tags & tokens:
			continue
		try:
			index = int(box.get("pageIndex") or 0)
			x, y = float(box["x"]), float(box["y"])
			width, height = float(box["width"]), float(box["height"])
		except (KeyError, TypeError, ValueError):
			continue
		page = pages[index] if 0 <= index < len(pages) else pages[0]
		pad_x, pad_y = (0, 0.5) if box.get("isRow") else (2, 1.5)
		by_page.setdefault(id(page), (page, []))[1].append(
			(x - pad_x, y - pad_y, width + pad_x * 2, height + pad_y * 2)
		)
	red, green, blue = HIGHLIGHT_RGB
	for page, rects in by_page.values():
		state = DictionaryObject(
			{
				NameObject("/Type"): NameObject("/ExtGState"),
				NameObject("/ca"): FloatObject(HIGHLIGHT_OPACITY),
				NameObject("/CA"): FloatObject(HIGHLIGHT_OPACITY),
			}
		)
		_resources(page, "/ExtGState")[NameObject("/IllHighlight")] = writer._add_object(state)
		ops = [f"q /IllHighlight gs {red} {green} {blue} rg"]
		ops += [f"{x:.3f} {y:.3f} {w:.3f} {h:.3f} re f" for x, y, w, h in rects]
		ops.append("Q\n")
		_append_content(writer, page, "\n".join(ops).encode())
		drawn += len(rects)
	return drawn


def _remove_widgets(writer):
	from pypdf.generic import ArrayObject, NameObject

	for page in writer.pages:
		annots = page.get("/Annots")
		if annots is None:
			continue
		kept = ArrayObject(
			annot for annot in annots.get_object() if annot.get_object().get("/Subtype") != "/Widget"
		)
		if kept:
			page[NameObject("/Annots")] = kept
		else:
			del page[NameObject("/Annots")]
	root = writer._root_object
	if "/AcroForm" in root:
		del root[NameObject("/AcroForm")]


def fill(source, *, text=None, steps=None, display=None, title=None):
	"""Fill and flatten one generated spec sheet.

	``text``: values for the footer fields (and ``line_summary``); a field the sheet lacks is skipped.
	``steps``: ``{"1": "WL", "7": "216.0", ...}``, a step's code (or a free value for a text step).
	``display``: values for ``display_step_N`` boxes; by default each step's value upper-cased.

	Returns ``{pdf, has_form, selected, unmatched, missing_steps, highlights, highlight_style}``.
	A sheet without form fields comes back unchanged with ``has_form`` False.
	"""
	from pypdf import PdfReader
	from pypdf.generic import NameObject, TextStringObject

	text = {key: value for key, value in (text or {}).items() if value not in (None, "")}
	steps = {str(key): str(value) for key, value in (steps or {}).items() if value not in (None, "")}
	pages_before = len(PdfReader(io.BytesIO(source)).pages)
	writer = _writer(source)
	fields = _fields(writer)
	boxes = _subject_boxes(writer)
	result = {
		"pdf": source,
		"has_form": bool(fields),
		"selected": {},
		"unmatched": {},
		"missing_steps": [],
		"highlights": 0,
		"highlight_style": _highlight_style(boxes),
	}
	if not fields:
		return result

	values = {}
	for name in TEXT_FIELDS:
		if name in text and name in fields:
			values[name] = str(text[name])

	shown = dict(display or {})
	stamps = 0
	for step, code in steps.items():
		field = fields.get(STEP_PREFIX + step)
		if field is None:
			result["missing_steps"].append(step)
			continue
		if _field_type(field) == "/Tx":
			values[STEP_PREFIX + step] = code
			result["selected"][step] = code
		else:
			options = _options(field)
			index = next((i for i, option in enumerate(options) if option.lower() == code.lower()), None)
			if index is None:
				result["unmatched"][step] = code
				continue
			state = NameObject(f"/{index}")
			field[NameObject("/V")] = state
			for widget in _widgets(field):
				states = (widget.get("/AP") or {}).get("/N") or {}
				widget[NameObject("/AS")] = state if state in states else NameObject("/Off")
			result["selected"][step] = options[index]
		if DISPLAY_PREFIX + step in fields:
			values[DISPLAY_PREFIX + step] = str(shown.get(step, result["selected"][step])).upper()

	# Draw every selected radio (including the series step the generator preselects).
	for name, field in fields.items():
		if not name.startswith(STEP_PREFIX) or _field_type(field) != "/Btn":
			continue
		state = field.get("/V")
		if not state or str(state) == "/Off":
			continue
		for widget in _widgets(field):
			if str(widget.get("/AS") or "") != str(state):
				continue
			page = _page_of(writer, widget)
			if page is not None:
				stamps += 1
				_stamp_appearance(writer, page, widget, state, stamps)

	if values:
		for page in writer.pages:
			if page.get("/Annots"):
				writer.update_page_form_field_values(page, values, auto_regenerate=False, flatten=True)

	tokens = {f"{step}:{code}".lower() for step, code in result["selected"].items()}
	result["highlights"] = _draw_highlights(writer, boxes, tokens) if tokens else 0

	_remove_widgets(writer)
	for page in writer.pages:
		if "/IllWrapped" in page:
			del page[NameObject("/IllWrapped")]
	writer.add_metadata({"/Subject": TextStringObject("")})
	if title:
		writer.add_metadata({"/Title": TextStringObject(title)})
	output = io.BytesIO()
	writer.write(output)
	pdf = output.getvalue()
	if len(PdfReader(io.BytesIO(pdf)).pages) != pages_before:
		raise ValueError("Filling the spec sheet changed its page count")
	result["pdf"] = pdf
	return result
