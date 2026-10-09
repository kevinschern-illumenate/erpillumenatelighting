# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Unit helpers: ERP stores millimetres, the engine works in feet, the UI shows feet and inches (H7.3)."""

import re

MM_PER_IN = 25.4
MM_PER_FT = 304.8
FT_PER_M = 3.28084
PAYLOAD_DECIMALS = 4

_VOLTS = re.compile(r"(\d+(?:\.\d+)?)\s*V", re.IGNORECASE)


def mm_to_in(mm):
	return round(float(mm) / MM_PER_IN, PAYLOAD_DECIMALS)


def mm_to_ft(mm):
	return round(float(mm) / MM_PER_FT, PAYLOAD_DECIMALS)


def m_to_ft(m):
	return round(float(m) * FT_PER_M, PAYLOAD_DECIMALS)


def per_m_to_per_ft(value):
	return round(float(value) / FT_PER_M, PAYLOAD_DECIMALS)


def parse_voltage(*texts):
	"""First voltage found in ``texts`` ("24VDC" → 24.0, "12 V" → 12.0), else ``None``."""
	for text in texts:
		match = _VOLTS.search(str(text or ""))
		if match:
			return float(match.group(1))
	return None
