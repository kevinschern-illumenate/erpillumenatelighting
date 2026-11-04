"""Saved configuration presets (plan 3.6).

A preset is the configurator's exported request (``{family, template, selections[, segments]}``)
saved under a label by a dealer, kept private or shared with the dealer's company. Presets only
pre-fill the configurator: nothing is priced or saved from a preset, so the configurator's
validation and ``portal.configuration.save`` stay the single path onto a schedule.

Every load re-checks the preset against what is offered now. A template that is gone, inactive,
not offered to the user, or in a family the user cannot configure makes the preset unusable, and
linear fixture options the template no longer offers are dropped and reported, never applied.
Presets are ``ilL-Configuration-Preset`` rows (System Manager in Desk); portal users reach them
only through this module.
"""

import json

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from illumenate_lighting.illumenate_lighting.portal import site_flags

DOCTYPE = "ilL-Configuration-Preset"
MAX_REQUEST_BYTES = 64 * 1024
MAX_PRESETS_PER_USER = 200
MAX_LABEL = 140
REQUEST_KEYS = ("schema_version", "family", "template", "selections", "segments")
FIELDS = ["name", "label", "user", "customer", "shared_with_company", "family", "template", "modified"]
TAPE_NEON = "ilL-Tape-Neon-Template"
FAMILY_DOCTYPES = {
	"Linear Fixture": "ilL-Fixture-Template",
	"LED Tape": TAPE_NEON,
	"COB Tape": TAPE_NEON,
	"LED Neon": TAPE_NEON,
	"LED Sheet": "ilL-LED-Sheet-Template",
	"Extrusion Kit": "ilL-Extrusion-Kit-Template",
	"Driver": "ilL-Driver-Template",
	"Controller": "ilL-Controller-Template",
}
# Linear selection key -> (allowed option type, allowed option row field, label)
LINEAR_OPTIONS = {
	"environment_rating_code": ("Environment Rating", "environment_rating", "Environment"),
	"lens_appearance_code": ("Lens Appearance", "lens_appearance", "Lens"),
	"mounting_method_code": ("Mounting Method", "mounting_method", "Mounting"),
	"finish_code": ("Finish", "finish", "Finish"),
}


def _actor(schedule_name=None):
	"""The signed-in configurator user (catalog access, or edit rights on ``schedule_name``)."""
	if frappe.session.user == "Guest":
		frappe.throw(_("Please log in to use saved presets"), frappe.PermissionError)
	from illumenate_lighting.illumenate_lighting.portal.access import get_actor
	from illumenate_lighting.illumenate_lighting.portal.configurator_access import require_configurator

	require_configurator(schedule_name or None)
	return get_actor()


def _family(value):
	from illumenate_lighting.illumenate_lighting.api.configuration_contract import FAMILY_ALIASES

	family = FAMILY_ALIASES.get(str(value or "").strip())
	if family not in FAMILY_DOCTYPES:
		frappe.throw(_("Choose a product family for this preset"))
	return family


def _request(value):
	"""The canonical, price-free request to keep, or a user-facing error."""
	from illumenate_lighting.illumenate_lighting.api.configuration_contract import canonical_json
	from illumenate_lighting.illumenate_lighting.portal.configurator_access import strip_prices

	if isinstance(value, str):
		try:
			value = json.loads(value)
		except ValueError:
			frappe.throw(_("The preset is not valid JSON"))
	if not isinstance(value, dict):
		frappe.throw(_("The preset must contain the configurator request"))
	request = {key: value[key] for key in REQUEST_KEYS if key in value and value[key] is not None}
	request["family"] = _family(request.get("family"))
	request["template"] = str(request.get("template") or "").strip()
	selections = request.get("selections") or {}
	if not isinstance(selections, dict):
		frappe.throw(_("Preset selections must be an object"))
	request["selections"] = selections
	if "segments" in request and not isinstance(request["segments"], list):
		frappe.throw(_("Preset segments must be a list"))
	request = strip_prices(request)
	encoded = canonical_json(request)
	if len(encoded.encode()) > MAX_REQUEST_BYTES:
		frappe.throw(_("This configuration is too large to save as a preset"))
	return request, encoded


def _template_name(family, template):
	doctype = FAMILY_DOCTYPES[family]
	if frappe.db.exists(doctype, template):
		return template
	if doctype == TAPE_NEON:
		return frappe.db.get_value(doctype, {"template_code": template}, "name")
	return None


def template_problem(family, template):
	"""Why a preset for ``family``/``template`` cannot be used now, or ``None``."""
	from illumenate_lighting.illumenate_lighting.portal import rollout
	from illumenate_lighting.illumenate_lighting.portal_listing import template_visible

	if not rollout.available(family):
		return _("{0} is not available for your account").format(family)
	if not template:
		return None
	doctype = FAMILY_DOCTYPES[family]
	name = _template_name(family, template)
	if not name or not frappe.db.get_value(doctype, name, "is_active") or not template_visible(doctype, name):
		return _("{0} is no longer offered").format(template)
	return None


def _linear_problems(request):
	"""Drop linear options the template no longer offers from ``request``; describe each one."""
	selections = request.get("selections") or {}
	name = _template_name("Linear Fixture", request["template"])
	template = frappe.get_cached_doc("ilL-Fixture-Template", name)
	problems = []
	for key, (option_type, row_field, label) in LINEAR_OPTIONS.items():
		value = selections.get(key)
		if not value:
			continue
		offered = {
			row.get(row_field)
			for row in template.get("allowed_options") or []
			if row.get("option_type") == option_type and row.get("is_active")
		}
		if value not in offered:
			selections.pop(key)
			problems.append(_("{0} {1} is no longer offered; choose it again").format(_(label), value))
	offering = selections.get("tape_offering_id")
	if offering:
		listed = {row.get("tape_offering") for row in template.get("allowed_tape_offerings") or []}
		if offering not in listed or not frappe.db.get_value("ilL-Rel-Tape Offering", offering, "is_active"):
			selections.pop("tape_offering_id")
			problems.append(_("LED tape {0} is no longer offered; choose it again").format(offering))
	return problems


def revalidate(request):
	"""``(request, problems)`` for a stored request; ``request`` is ``None`` when unusable."""
	family = request.get("family")
	if family not in FAMILY_DOCTYPES:
		return None, [_("This preset's product family is no longer offered")]
	problem = template_problem(family, request.get("template"))
	if problem:
		return None, [problem]
	if family == "Linear Fixture" and request.get("template"):
		return request, _linear_problems(request)
	return request, []


def _visible(row, actor):
	if row.user == actor.user:
		return True
	return bool(
		row.shared_with_company and actor.customer and not actor.is_internal and row.customer == actor.customer
	)


def _row(name, actor, *, owned=False):
	row = frappe.db.get_value(DOCTYPE, name, [*FIELDS, "request_json"], as_dict=True) if name else None
	if not row or not _visible(row, actor) or (owned and row.user != actor.user):
		frappe.throw(_("Preset not found"), frappe.DoesNotExistError)
	return row


def _summary(row, actor, available=None):
	summary = {
		"name": row.name,
		"label": row.label,
		"family": row.family,
		"template": row.template or "",
		"shared": bool(row.shared_with_company),
		"mine": row.user == actor.user,
		"modified": str(row.modified or ""),
	}
	if available is not None:
		summary["available"] = available
	return summary


def _flag(value):
	from illumenate_lighting.illumenate_lighting.api.configuration_contract import parse_bool

	return parse_bool(value, default=False)


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=30, seconds=60)
def save_preset(label, request, shared_with_company=None, preset=None, schedule_name=None):
	"""Save the configurator ``request`` as ``label``; a preset of the same label is replaced."""
	if not site_flags.presets_enabled():
		return {"success": False, "disabled": True}
	actor = _actor(schedule_name)
	label = " ".join(str(label or "").split())
	if not label or len(label) > MAX_LABEL:
		frappe.throw(_("Name the preset (up to {0} characters)").format(MAX_LABEL))
	request, encoded = _request(request)
	problem = template_problem(request["family"], request["template"])
	if problem:
		frappe.throw(problem)
	shared = _flag(shared_with_company)
	if shared and not (actor.customer and actor.is_dealer and not actor.is_internal):
		frappe.throw(_("Only dealer company users can share presets"))
	values = {
		"label": label,
		"family": request["family"],
		"template": request["template"],
		"request_json": encoded,
		"customer": actor.customer if actor.customer and not actor.is_internal else None,
		"shared_with_company": 1 if shared else 0,
		"contract_version": int(request.get("schema_version") or 0),
	}
	name = _row(preset, actor, owned=True).name if preset else None
	if not name:
		name = frappe.db.get_value(DOCTYPE, {"user": actor.user, "label": label}, "name")
	if name:
		doc = frappe.get_doc(DOCTYPE, name)
		doc.update(values)
		doc.save(ignore_permissions=True)
	else:
		if frappe.db.count(DOCTYPE, {"user": actor.user}) >= MAX_PRESETS_PER_USER:
			frappe.throw(
				_("You have {0} presets; delete some before saving more").format(MAX_PRESETS_PER_USER)
			)
		doc = frappe.get_doc({"doctype": DOCTYPE, "user": actor.user, **values})
		doc = doc.insert(ignore_permissions=True)
	return {"success": True, "preset": _summary(doc, actor)}


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=60, seconds=60)
def list_presets(family=None, schedule_name=None):
	"""The user's presets and the presets their company shares, each marked ``available``."""
	if not site_flags.presets_enabled():
		return {"success": True, "presets": [], "disabled": True}
	actor = _actor(schedule_name)
	filters = {"family": _family(family)} if family else {}
	own = frappe.get_all(DOCTYPE, filters={**filters, "user": actor.user}, fields=FIELDS)
	rows = {row.name: row for row in own}
	if actor.customer and not actor.is_internal:
		shared = frappe.get_all(
			DOCTYPE, filters={**filters, "customer": actor.customer, "shared_with_company": 1}, fields=FIELDS
		)
		rows.update({row.name: row for row in shared})
	checked = {}
	presets = []
	for row in rows.values():
		key = (row.family, row.template or "")
		if key not in checked:
			checked[key] = row.family in FAMILY_DOCTYPES and template_problem(*key) is None
		presets.append(_summary(row, actor, checked[key]))
	presets.sort(key=lambda item: (not item["mine"], item["label"].lower(), item["name"]))
	return {"success": True, "presets": presets}


def load(name, actor=None, schedule_name=None):
	"""The preset ``name`` re-checked for use now: summary, ``request`` (or ``None``) and ``problems``."""
	actor = actor or _actor(schedule_name)
	row = _row(name, actor)
	try:
		stored = json.loads(row.request_json or "{}")
	except ValueError:
		stored = {}
	request, problems = revalidate(stored) if isinstance(stored, dict) else (None, [])
	if request is None and not problems:
		problems = [_("This preset can no longer be read")]
	return {**_summary(row, actor), "request": request, "problems": problems}


@frappe.whitelist(methods=["GET"])
@rate_limit(limit=60, seconds=60)
def get_preset(preset, schedule_name=None):
	if not site_flags.presets_enabled():
		return {"success": False, "disabled": True}
	return {"success": True, "preset": load(preset, _actor(schedule_name))}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=30, seconds=60)
def delete_preset(preset, schedule_name=None):
	"""Delete one of the user's own presets; company members cannot delete each other's."""
	if not site_flags.presets_enabled():
		return {"success": False, "disabled": True}
	actor = _actor(schedule_name)
	row = _row(preset, actor, owned=True)
	frappe.delete_doc(DOCTYPE, row.name, ignore_permissions=True)
	return {"success": True}
