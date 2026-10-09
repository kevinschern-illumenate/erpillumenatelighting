"""Seed the SH01 channel cross-section for the System Designer (WP-1.5).

The outlines come from the reference visualizer's ``CAD_SH01`` constant (flattened from the SH01 DWG,
1/1000 inch). They go on every SH01 profile spec whose ``cross_section_json`` is still empty: profiles
in family or series SH01, and the SH01 fixture template's default profile. Re-running changes nothing.
"""

import json

import frappe

from illumenate_lighting.illumenate_lighting.system_design.geometry import load_sh01_seed

PROFILE = "ilL-Spec-Profile"


def sh01_profiles():
	names = set()
	for field in ("family", "series"):
		names.update(frappe.get_all(PROFILE, filters={field: "SH01"}, pluck="name"))
	if frappe.db.exists("ilL-Fixture-Template", "SH01"):
		default = frappe.db.get_value("ilL-Fixture-Template", "SH01", "default_profile_spec")
		if default:
			names.add(default)
	return sorted(names)


def execute():
	if not frappe.db.has_column(PROFILE, "cross_section_json"):
		return
	value = json.dumps(load_sh01_seed(), separators=(",", ":"))
	for name in sh01_profiles():
		if not frappe.db.get_value(PROFILE, name, "cross_section_json"):
			frappe.db.set_value(PROFILE, name, "cross_section_json", value, update_modified=False)
