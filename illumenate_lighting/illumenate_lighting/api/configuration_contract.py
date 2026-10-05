"""Versioned, framework-independent configuration primitives.

Canonical inputs describe engineering intent. Resolved identity additionally
includes the actual components and dependency revisions; neither contains price.
"""

import hashlib
import json
import math
from decimal import Decimal

CONTRACT_VERSION = 2
DEFAULT_UOM = "Ea"
FAMILY_ALIASES = {
	"Extrusion Kit": "Extrusion Kit",
	"Driver": "Driver",
	"Controller": "Controller",
	"Fixture Template": "Linear Fixture",
	"Linear Fixtures": "Linear Fixture",
	"Linear Fixture": "Linear Fixture",
	"LED Tape": "LED Tape",
	"COB Tape": "COB Tape",
	"LED Neon": "LED Neon",
	"LED Sheet": "LED Sheet",
	"LED Sheets": "LED Sheet",
}

# ilL-Tape-Neon-Template product categories. COB Tape is its own product family
# that configures, prices and builds exactly like LED Tape; branch on these
# groups rather than on the "LED Tape" literal so both categories share one path.
LED_TAPE, COB_TAPE, LED_NEON = "LED Tape", "COB Tape", "LED Neon"
TAPE_CATEGORIES = (LED_TAPE, COB_TAPE)
TAPE_NEON_CATEGORIES = (*TAPE_CATEGORIES, LED_NEON)


def is_tape_category(category):
	"""True for the tape (single-run, environment/PCB/feed-type) categories."""
	return category in TAPE_CATEGORIES


def is_tape_neon_category(category):
	"""True for every category configured from an ilL-Tape-Neon-Template."""
	return category in TAPE_NEON_CATEGORIES


def same_template_family(product_type, template_category):
	"""True when a product of *product_type* may use a template of *template_category*.

	Tape products and templates match across LED Tape and COB Tape, so a template
	can move to COB Tape before the products that link it.
	"""
	if is_tape_category(product_type) and is_tape_category(template_category):
		return True
	return product_type == template_category


def spec_categories_for(category):
	"""ilL-Spec-LED Tape product categories a template of *category* may use.

	COB Tape templates may keep using specs still filed as LED Tape, so the
	category can be switched on the template alone; LED Tape templates never
	pick up specs filed as COB Tape.
	"""
	if category == COB_TAPE:
		return (COB_TAPE, LED_TAPE)
	return (category,)


def parse_bool(value, *, default=False):
	if value is None or value == "":
		return default
	if isinstance(value, bool):
		return value
	if isinstance(value, str):
		value = value.strip().lower()
		if value in ("true", "1", "yes", "on"):
			return True
		if value in ("false", "0", "no", "off"):
			return False
	elif value in (0, 1):
		return bool(value)
	raise ValueError("Expected a boolean (true/false or 1/0)")


def finite_number(value, *, minimum=None, field="value"):
	if isinstance(value, bool):
		raise ValueError(f"{field} must be a finite number")
	try:
		result = float(value)
	except (TypeError, ValueError, OverflowError) as exc:
		raise ValueError(f"{field} must be a finite number") from exc
	if not math.isfinite(result) or (minimum is not None and result < minimum):
		raise ValueError(f"{field} must be finite and at least {minimum}")
	return result


def length_mm(value, unit="mm"):
	factors = {
		"mm": "1",
		"inch": "25.4",
		"in": "25.4",
		"foot": "304.8",
		"ft": "304.8",
		"meter": "1000",
		"m": "1000",
	}
	if unit.lower() not in factors:
		raise ValueError("Unsupported length unit")
	finite_number(value, minimum=0, field="length")
	return float(Decimal(str(value)) * Decimal(factors[unit.lower()]))


def optional_positive(value, *, field="value"):
	if value in (None, ""):
		return None
	result = finite_number(value, minimum=0, field=field)
	if result <= 0:
		raise ValueError(f"{field} must be greater than zero")
	return result


def optional_integer(value, *, minimum=0, field="value"):
	"""Normalize an optional form number without truncating fractional input."""
	if value in (None, ""):
		return None
	result = finite_number(value, minimum=minimum, field=field)
	if not result.is_integer():
		raise ValueError(f"{field} must be a whole number")
	return int(result)


def segment_list(value, *, field="segments"):
	"""Decode a segments payload into a list of segment objects.

	One extra JSON-string layer (as older desk clients sent) is unwrapped;
	anything else that is not a list of objects is rejected before an engine
	iterates it.
	"""
	for _layer in range(2):
		if not isinstance(value, str):
			break
		if not value.strip():
			return None
		try:
			value = json.loads(value)
		except json.JSONDecodeError as exc:
			raise ValueError(f"{field} must be valid JSON") from exc
	if value is None:
		return None
	if not isinstance(value, list) or not all(isinstance(segment, dict) for segment in value):
		raise ValueError(f"{field} must be a list of segment objects")
	return value


def string_list(value, *, field="value"):
	"""Decode an optional list of names sent as a list or a JSON-encoded list.

	frappe.call JSON-encodes arrays, and a blank form value means "none".
	"""
	if isinstance(value, str):
		if not value.strip():
			return None
		try:
			value = json.loads(value)
		except json.JSONDecodeError as exc:
			raise ValueError(f"{field} must be a JSON list") from exc
	if value is None:
		return None
	if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
		raise ValueError(f"{field} must be a list of names")
	return value


def canonical_json(value):
	return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def fingerprint(value):
	return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def build_identity(inputs, components, dependency_revision, *, engine_version):
	return fingerprint(
		{
			"contract_version": CONTRACT_VERSION,
			"inputs": inputs,
			"components": components,
			"dependency_revision": dependency_revision,
			"engine_version": engine_version,
		}
	)


def is_count_uom(uom):
	"""Recognize individual-unit UOMs while preserving the Item's stored spelling."""
	return isinstance(uom, str) and uom.lower() in {"ea", "nos", "unit", "each"}


def cable_stock_quantity(length, length_unit, stock_uom, *, assembly_length_mm=None):
	"""Convert a physical cable once; count UOMs require an exact assembly mapping."""
	mm = length_mm(length, length_unit)
	factors = {"Millimeter": 1, "Meter": 1000, "Foot": 304.8, "Feet": 304.8, "Inch": 25.4}
	if stock_uom in factors:
		return mm / factors[stock_uom]
	if is_count_uom(stock_uom) and assembly_length_mm is not None:
		if math.isclose(mm, finite_number(assembly_length_mm, minimum=0), abs_tol=1e-6):
			return 1
	raise ValueError("Cable requires a supported length UOM or an exact fixed-length assembly")
