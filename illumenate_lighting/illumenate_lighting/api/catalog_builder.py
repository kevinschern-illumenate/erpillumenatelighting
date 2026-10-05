"""Catalog Builder data, served only to authorized catalog staff."""

import json
from pathlib import Path

import frappe

from illumenate_lighting.illumenate_lighting.portal.staff import require

# Session 1 uses the committed snapshot; Session 2 replaces it with live records.
SNAPSHOT = Path(__file__).resolve().parents[3] / "tools/yaml_builder_ui/src/erp-reference.json"


@frappe.whitelist(methods=["GET"])
def reference():
	require("catalog")
	if not SNAPSHOT.is_file():
		return {"schema_version": 1, "exported_on": None, "doctypes": {}, "unavailable": True}
	return json.loads(SNAPSHOT.read_text(encoding="utf-8"))
