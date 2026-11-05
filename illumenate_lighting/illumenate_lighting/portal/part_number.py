"""Plan 3.5: read a linear fixture part number back into configurator selections.

``ilL-Configured-Fixture._generate_part_number`` writes
``ILL-{series}-{led}-{env}-{cct}-{output}-{lens}-{mount}-{finish}-{length}-{tail}[-V(..)]``,
where ``tail`` is ``J``/``J(hash)`` for jointed fixtures or ``{feed}{leader ft}-{C|end}``.
Decoding walks that layout in reverse. Each code is matched against the options the
fixture template offers now (its allowed options and tape offerings), and against its
Part Number Builder rows. A code that matches nothing, several things, or a code the
builder no longer lists is reported, never guessed. Nothing is read from configured
fixtures: reopening a configuration stays tied to the schedule that owns it.
"""

import re

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

FIXTURE_TEMPLATE = "ilL-Fixture-Template"
MAX_LENGTH = 200
PLACEHOLDER = "XX"
JOINT = re.compile(r"^J(\([A-Z0-9]+\))?$")
VARIANT = re.compile(r"-V\([^()]*\)$")
NUMBER = re.compile(r"^\d+(\.\d+)?$")
MM_PER_INCH = 25.4
MM_PER_FOOT = 304.8
HEAD = ("led_package", "environment", "cct", "output", "lens", "mounting", "finish")

# Allowed-option codes: PN key -> (builder section, option type, row field, selection key, attribute)
OPTIONS = {
	"environment": (
		"Dry/Wet",
		"Environment Rating",
		"environment_rating",
		"environment_rating_code",
		"ilL-Attribute-Environment Rating",
	),
	"lens": ("Lens", "Lens Appearance", "lens_appearance", "lens_appearance_code", "ilL-Attribute-Lens Appearance"),
	"mounting": (
		"Mounting",
		"Mounting Method",
		"mounting_method",
		"mounting_method_code",
		"ilL-Attribute-Mounting Method",
	),
	"finish": ("Finish", "Finish", "finish", "finish_code", "ilL-Attribute-Finish"),
}
BUILDER_SECTIONS = {"cct": "CCT", "output": "Output", "feed": "Start Feed Type"}


class NotAPartNumber(ValueError):
	pass


def parse(part_number):
	"""Split a fixture part number into its coded positions, or raise ``NotAPartNumber``."""
	text = re.sub(r"\s+", "", str(part_number or "")).upper()
	if not text or len(text) > MAX_LENGTH:
		raise NotAPartNumber(_("Enter a fixture part number"))
	variant = VARIANT.search(text)
	if variant:
		text = text[: variant.start()]
	tokens = text.split("-")
	if len(tokens) < 11 or tokens[0] != "ILL":
		raise NotAPartNumber(_("{0} is not a fixture part number").format(part_number))
	if JOINT.match(tokens[-1]):
		length, head, tail = tokens[-2], tokens[1:-2], {"joint": True, "feed": None, "end": None}
	else:
		length, head, tail = tokens[-3], tokens[1:-3], {"joint": False, "feed": tokens[-2], "end": tokens[-1]}
	if not NUMBER.match(length) or len(head) < len(HEAD) + 1 or not all(head):
		raise NotAPartNumber(_("{0} is not a fixture part number").format(part_number))
	# Only the series (a template's profile family) may itself contain hyphens.
	parsed = {"series": "-".join(head[: -len(HEAD)]), **dict(zip(HEAD, head[-len(HEAD) :], strict=True)), **tail}
	parsed["length_inches"] = float(length)
	parsed["variant"] = bool(variant)
	return parsed


def _codes(doctype, names, field="code"):
	if not names:
		return {}
	rows = frappe.get_all(
		doctype, filters={"name": ["in", sorted(names)]}, fields=["name", field], ignore_permissions=True
	)
	return {row.name: str(row.get(field) or "").upper() for row in rows}


def _builder(template):
	sections = {}
	for row in template.get("part_number_builder") or []:
		code = str(row.get("option_code") or "").upper()
		if code:
			sections.setdefault(row.get("section_name"), {})[code] = row.get("option_label") or code
	return sections


class _Match:
	def __init__(self, builder):
		self.builder = builder
		self.selections = {}
		self.applied = []
		self.unmatched = []
		self.review = []

	def label(self, section, code, fallback):
		return (self.builder.get(section) or {}).get(code) or fallback

	def miss(self, field, code, section, offered, reason=None):
		if reason is None:
			listed = self.builder.get(section)
			if offered:
				reason = _("matches more than one option")
			elif listed and code not in listed:
				reason = _("not in this product's part number guide")
			else:
				reason = _("no longer offered on this product")
		self.unmatched.append({"field": field, "answer": code, "reason": reason})

	def pick(self, field, code, section, names, key):
		"""Select the one ``names`` entry whose code is ``code``; report anything else."""
		if code == PLACEHOLDER:
			return None
		found = sorted(name for name, value in names.items() if value == code)
		if len(found) != 1:
			self.miss(field, code, section, found)
			return None
		self.selections[key] = found[0]
		self.applied.append(
			{"field": field, "answer": code, "value": found[0], "label": self.label(section, code, found[0])}
		)
		return found[0]


def _match(template, parsed):
	match = _Match(_builder(template))
	for field, (section, option_type, row_field, key, doctype) in OPTIONS.items():
		names = {
			row.get(row_field)
			for row in template.get("allowed_options") or []
			if row.get("option_type") == option_type and row.get("is_active") and row.get(row_field)
		}
		match.pick(field, parsed[field], section, _codes(doctype, names), key)

	offerings = [row.get("tape_offering") for row in template.get("allowed_tape_offerings") or [] if row.get("tape_offering")]
	rows = (
		frappe.get_all(
			"ilL-Rel-Tape Offering",
			filters={"name": ["in", offerings], "is_active": 1},
			fields=["name", "led_package", "cct"],
			ignore_permissions=True,
		)
		if offerings
		else []
	)
	package = match.pick(
		"led_package",
		parsed["led_package"],
		"LED Package",
		_codes("ilL-Attribute-LED Package", {row.led_package for row in rows if row.led_package}),
		"led_package_code",
	)
	ccts = {row.cct for row in rows if row.cct and (package is None or row.led_package == package)}
	match.pick("cct", parsed["cct"], BUILDER_SECTIONS["cct"], _codes("ilL-Attribute-CCT", ccts), "cct_code")

	# Fixture output is tape output through the lens, so it names no single option: confirm it.
	if parsed["output"] != PLACEHOLDER:
		label = match.label(BUILDER_SECTIONS["output"], parsed["output"], parsed["output"])
		match.review.append(
			{"field": "output", "answer": parsed["output"], "label": label, "text": _("Output {0}").format(label)}
		)
	inches = parsed["length_inches"]
	match.review.append(
		{"field": "length", "answer": inches, "text": _("Length {0} in").format(f"{inches:g}")}
	)
	if parsed["joint"]:
		match.review.append({"field": "joint", "answer": "J", "text": _("Jointed runs")})
	elif parsed["feed"]:
		match.review.append(_feed(template, parsed["feed"], match))
	if parsed["variant"]:
		match.review.append({"field": "variant", "answer": "V", "text": _("Modified variant")})
	return match


def _feed(template, token, match):
	"""``{feed code}{leader ft}``: the longest offered feed code that leaves a number."""
	names = {
		row.get("power_feed_type")
		for row in template.get("allowed_options") or []
		if row.get("option_type") == "Power Feed Type" and row.get("is_active") and row.get("power_feed_type")
	}
	codes = _codes("ilL-Attribute-Power Feed Type", names)
	best = None
	for name, code in sorted(codes.items()):
		rest = token[len(code) :]
		if code and token.startswith(code) and (rest == "" or NUMBER.match(rest)):
			if best is None or len(code) > len(best[1]):
				best = (name, code, rest)
			elif len(code) == len(best[1]):
				best = (None, code, rest)
	if best is None or best[0] is None:
		return {"field": "feed", "answer": token, "text": _("Start feed code {0}").format(token)}
	name, code, rest = best
	label = match.label(BUILDER_SECTIONS["feed"], code, name)
	leader = float(rest) if rest else None
	return {
		"field": "feed",
		"answer": token,
		"value": name,
		"label": label,
		"leader_ft": leader,
		"text": _("Start feed {0}, {1} ft leader").format(label, f"{leader:g}")
		if leader is not None
		else _("Start feed {0}").format(label),
	}


def decode(part_number):
	"""What a fixture part number says, resolved against the templates offered to the user.

	``status`` is ``decoded`` (every coded option matched one offered option),
	``partial`` (some codes are reported in ``unmatched``), ``ambiguous`` (several
	templates fit equally; ``candidates`` lists them and none is chosen) or
	``unknown`` (no offered template uses this series).
	"""
	from illumenate_lighting.illumenate_lighting.portal_listing import template_filters

	parsed = parse(part_number)
	result = {
		"part_number": re.sub(r"\s+", "", str(part_number)).upper(),
		"family": "Linear Fixture",
		"series": parsed["series"],
		"template": None,
		"template_name": None,
		"selections": {},
		"applied": [],
		"unmatched": [],
		"review": [],
		"candidates": [],
		"length_inches": parsed["length_inches"],
	}
	rows = frappe.get_all(
		FIXTURE_TEMPLATE,
		filters=template_filters(),
		fields=["name", "template_name", "default_profile_family"],
		ignore_permissions=True,
	)
	rows = [row for row in rows if str(row.default_profile_family or "").upper() == parsed["series"]]
	if not rows:
		result["status"] = "unknown"
		result["unmatched"].append(
			{"field": "series", "answer": parsed["series"], "reason": _("no fixture with this series is offered")}
		)
		return result
	matches = [(row, _match(frappe.get_cached_doc(FIXTURE_TEMPLATE, row.name), parsed)) for row in rows]
	fewest = min(len(match.unmatched) for _row, match in matches)
	best = [(row, match) for row, match in matches if len(match.unmatched) == fewest]
	if len(best) > 1:
		result["status"] = "ambiguous"
		result["candidates"] = [{"value": row.name, "label": row.template_name or row.name} for row, _m in best]
		return result
	row, match = best[0]
	segments = _segments(parsed, match)
	result.update(
		{
			"template": row.name,
			"template_name": row.template_name or row.name,
			"selections": {"fixture_template_code": row.name, **match.selections},
			"segments": segments,
			"applied": match.applied,
			"unmatched": match.unmatched,
			"review": match.review,
			"status": "partial" if match.unmatched else "decoded",
		}
	)
	return result


def _segments(parsed, match):
	"""The fixture's single segment as the configurator restores it: length, start feed, leader, end.

	A jointed part number (``J``/``J(hash)``) does not record its segment lengths, and no part
	number records the feed direction, so those are left for the dealer (the review notes say so).
	"""
	if parsed["joint"]:
		return []
	segment = {"segment_index": 1, "requested_length_mm": round(parsed["length_inches"] * MM_PER_INCH, 1)}
	feed = next((row for row in match.review if row.get("field") == "feed"), {})
	if feed.get("value"):
		segment["start_power_feed_type"] = feed["value"]
	if feed.get("leader_ft") is not None:
		segment["start_leader_cable_length_mm"] = round(feed["leader_ft"] * MM_PER_FOOT)
	if parsed["end"] == "C":
		segment["end_type"] = "Endcap"
	elif parsed["end"]:
		match.review.append(
			{"field": "end", "answer": parsed["end"], "text": _("End feed {0}: choose the end option").format(parsed["end"])}
		)
	match.review.append({"field": "feed_direction", "text": _("Choose the feed direction")})
	return [segment]


@frappe.whitelist()
@rate_limit(limit=60, seconds=60)
def decode_part_number(part_number, schedule=None):
	"""Decode ``part_number`` for the configurator. Nothing is saved."""
	from illumenate_lighting.illumenate_lighting.portal.configurator_access import require_configurator
	from illumenate_lighting.illumenate_lighting.portal.site_flags import part_number_decode_enabled

	if frappe.session.user == "Guest":
		raise frappe.PermissionError
	if not part_number_decode_enabled():
		frappe.throw(_("Part number lookup is turned off"))
	require_configurator(schedule or None)
	try:
		return {"success": True, **decode(part_number)}
	except NotAPartNumber as exc:
		return {"success": False, "error": str(exc)}
