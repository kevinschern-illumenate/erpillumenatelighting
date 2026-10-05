"""Validate version 2 product YAML and export ordered ERPNext Data Import CSVs."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from illumenate_lighting.illumenate_lighting.catalog_authoring.catalog import (
	AXES,
	CONFIGURATION_TABLES,
	NUMBERS,
	TABLES,
	WEBFLOW_TEMPLATES,
	_axis_value,
	_configuration_errors,
	_record_errors,
	_variant_errors,
	csv_data,
	identity,
	links,
	prepare_catalog,
	with_defaults,
)

from .catalog_schema import build_schema


def generate_catalog(config, output_dir, reference=None):
	schema = build_schema()
	records, batches, external = prepare_catalog(config, schema, reference)
	declared = config.get("external_links", {})
	output = Path(output_dir)
	output.mkdir(parents=True, exist_ok=True)
	results, manifest = (
		{},
		{
			"schema_version": 2,
			"product_type": config["product_type"],
			"imports": [],
			"external_links": [
				{
					"doctype": dt,
					"name": name,
					"source": "declared" if name in declared.get(dt, []) else "ERPNext export",
				}
				for dt, name in external
			],
		},
	)
	for i, (doctype, batch) in enumerate(batches, 1):
		filename = f"{i:03d}-{doctype}.csv"
		path = output / filename
		headers, rows = csv_data(doctype, batch, schema)
		with path.open("w", encoding="utf-8-sig", newline="") as handle:
			writer = csv.writer(handle)
			writer.writerow(headers)
			writer.writerows(rows)
		results[filename] = str(path)
		manifest["imports"].append(
			{
				"file": filename,
				"doctype": doctype,
				"records": len(batch),
				"rows": len(rows),
				"import_type": "Insert New Records",
			}
		)
	(output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
	(output / "records.json").write_text(
		json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
	)
	(output / "IMPORT.md").write_text(
		"# Product catalog import\n\nConfirm the existing records in manifest.json external_links first.\n"
		"Import the CSV files in manifest order through ERPNext Data Import, using the listed DocType and Insert New Records.\n"
		"A DocType can appear in several batches because its records depend on earlier records of that same type.\n"
		"Use only files listed in this manifest; older files in the output folder may belong to an earlier build.\n"
		"Review the import preview before submitting. This package does not publish or sync products.\n"
		"Configured products, BOMs, and sales transactions are created by the ERP configurators at runtime.\n"
		"Upload referenced attachments to the site first. Site custom fields and live link existence require site validation.\n",
		encoding="utf-8",
	)
	return results
