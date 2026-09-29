# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Which tape sits behind a lens for a delivered fixture output.

Low-transmission lenses (white about 56 %, black about 32 %) need brighter tape
to deliver the same lm/ft as frosted or clear lenses. A tape offers a fixture
output level when its delivered output (tape lm/ft x lens transmission) rounds
to that level. When several tapes round to the same level, the tape whose
delivered output is **closest** to the level is used (owner decision,
2026-09-29), matching the published spec sheets. Ties go to the lower-output
tape. Pure functions; no database access.
"""


def transmission_fraction(value):
	"""Lens transmission as a fraction. Accepts 0.56 or 56 (percent); blank means no lens loss."""
	try:
		transmission = float(value or 0)
	except (TypeError, ValueError):
		return 1.0
	if transmission <= 0:
		return 1.0
	return transmission / 100 if transmission > 1 else transmission


def delivered_lm_ft(tape_lm_ft, transmission):
	return float(tape_lm_ft or 0) * transmission_fraction(transmission)


def closest_tape(candidates, target_lm_ft, transmission, output_key="output_value_lm_ft"):
	"""Pick the candidate whose delivered output is closest to ``target_lm_ft``.

	``candidates`` are dicts (or objects with ``get``) carrying the tape's lm/ft under
	``output_key``. Returns None for an empty list.
	"""
	if not candidates:
		return None
	return min(
		candidates,
		key=lambda tape: (
			abs(delivered_lm_ft(tape.get(output_key), transmission) - float(target_lm_ft)),
			float(tape.get(output_key) or 0),
		),
	)
