"""Python reference for the AutoLISP math subset (draw-to-quote plan 1.7).

The AutoCAD toolkit shows hints only; the configurators decide. This module is the readable copy of
the few rules the LISP mirrors, so the golden fixtures in ``tools/system_designer/fixtures/cad`` can be
checked in Python CI (and against the server functions they copy) and by ``accoreconsole`` on a staff
machine (plan 3.10):

- cut snap: ``configuration_contract.whole_increments`` as ``tape_neon_configurator`` applies it;
- max run, percent of max run and the equal split: ``tape_neon_configurator._compute_run_split``;
- PSU load sum: watts per run against the supply's usable watts (rated x ``usable_load_factor``);
- path length of a polyline with bulges, and its smallest arc radius (the bend check).
"""

import itertools
import math

MM_PER_IN = 25.4
MM_PER_FT = 304.8
MAX_WATTS_PER_RUN = 85.0  # tape_neon_configurator.MAX_WATTS_PER_RUN


def round_half_even(value, digits=0):
	"""Python's ``round`` (banker's rounding), written out so the LISP copy is exact."""
	return round(value, digits)


def whole_increments(length, increment):
	return math.floor(length / increment + 1e-9)


def cut_snap(length_in, cut_mm, free_cut=False):
	"""Manufacturable length of one segment: whole cut increments, at least one."""
	requested_mm = length_in * MM_PER_IN
	if free_cut or not cut_mm or cut_mm <= 0 or requested_mm <= 0:
		return {"mfg_in": round(length_in, 4), "increments": None, "diff_in": 0.0}
	increments = max(1, whole_increments(requested_mm, cut_mm))
	mfg_mm = increments * cut_mm
	return {
		"mfg_in": round(mfg_mm / MM_PER_IN, 4),
		"increments": increments,
		"diff_in": round((requested_mm - mfg_mm) / MM_PER_IN, 4),
	}


def max_run_ft(w_per_ft, max_run_vd_ft=None, override_ft=None):
	"""The configurator's effective max run: min(85 W / W/ft, voltage-drop run); override wins."""
	if override_ft and override_ft > 0:
		return float(override_ft)
	by_watts = MAX_WATTS_PER_RUN / w_per_ft if w_per_ft and w_per_ft > 0 else math.inf
	if max_run_vd_ft and max_run_vd_ft > 0:
		return min(by_watts, float(max_run_vd_ft))
	return by_watts


def run_split(length_in, w_per_ft, cut_mm=None, free_cut=False, max_run_vd_ft=None, override_ft=None):
	"""Runs a tape length splits into, distributed like ``_compute_run_split``."""
	length_mm = length_in * MM_PER_IN
	effective = max_run_ft(w_per_ft, max_run_vd_ft, override_ft)
	max_mm = effective * MM_PER_FT if effective != math.inf else math.inf
	runs_count = math.ceil(length_mm / max_mm) if max_mm != math.inf and length_mm > max_mm else 1
	increment = cut_mm if (not free_cut and cut_mm and cut_mm > 0) else 0
	if runs_count == 1:
		runs_mm = [length_mm]
	elif increment:
		total = round_half_even(length_mm / increment)
		base, extra = divmod(total, runs_count)
		runs_mm = [(base + (1 if index < extra else 0)) * increment for index in range(runs_count)]
	else:
		runs_mm = [length_mm / runs_count] * runs_count
	return {
		"max_run_ft": None if effective == math.inf else round(effective, 2),
		"pct_of_max": None if effective == math.inf else round(100 * length_mm / MM_PER_FT / effective, 1),
		"runs_count": runs_count,
		"runs_in": [round(value / MM_PER_IN, 2) for value in runs_mm],
	}


def psu_load(loads_w, rated_w, usable_load_factor=None):
	"""Provisional PSU tag: total watts and percent of the usable watts (D: hint only, not sizing)."""
	total = sum(loads_w)
	usable = rated_w * (usable_load_factor or 1.0)
	return {
		"total_w": round(total, 2),
		"usable_w": round(usable, 2),
		"pct_of_usable": round(100 * total / usable, 1) if usable > 0 else None,
		"over": total > usable,
	}


def run_watts(length_in, w_per_ft):
	return round(length_in / 12 * w_per_ft, 2)


def path_length(vertices, closed=False):
	"""Length of an LWPOLYLINE given ``[[x, y, bulge], ...]`` and its smallest arc radius (or None)."""
	points = list(vertices)
	if closed and points:
		points = [*points, points[0]]
	total, smallest = 0.0, None
	for start, end in itertools.pairwise(points):
		chord = math.hypot(end[0] - start[0], end[1] - start[1])
		bulge = start[2] if len(start) > 2 else 0.0
		if not bulge or chord == 0:
			total += chord
			continue
		angle = 4 * math.atan(abs(bulge))
		radius = chord / (2 * math.sin(angle / 2))
		total += radius * angle
		smallest = radius if smallest is None else min(smallest, radius)
	return {"length_in": round(total, 4), "min_arc_radius_in": None if smallest is None else round(smallest, 4)}
