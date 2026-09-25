"""Versioned, framework-independent configuration primitives.

Canonical inputs describe engineering intent. Resolved identity additionally
includes the actual components and dependency revisions; neither contains price.
"""

import hashlib
import json
import math
from decimal import Decimal

CONTRACT_VERSION = 2
FAMILY_ALIASES = {
	"Fixture Template": "Linear Fixture",
	"Linear Fixtures": "Linear Fixture",
	"Linear Fixture": "Linear Fixture",
	"LED Tape": "LED Tape",
	"LED Neon": "LED Neon",
	"LED Sheet": "LED Sheet",
	"LED Sheets": "LED Sheet",
}


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


def cable_stock_quantity(length, length_unit, stock_uom, *, assembly_length_mm=None):
	"""Convert a physical cable once; Nos requires an exact assembly mapping."""
	mm = length_mm(length, length_unit)
	factors = {"Millimeter": 1, "Meter": 1000, "Foot": 304.8, "Feet": 304.8, "Inch": 25.4}
	if stock_uom in factors:
		return mm / factors[stock_uom]
	if stock_uom in ("Nos", "Unit") and assembly_length_mm is not None:
		if math.isclose(mm, finite_number(assembly_length_mm, minimum=0), abs_tol=1e-6):
			return 1
	raise ValueError("Cable requires a supported length UOM or an exact fixed-length assembly")
