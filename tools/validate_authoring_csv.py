"""Validate flat Spec/PDF-mapping import CSVs against shipped DocType fields.

No import or network access. ERP readiness still checks linked records and PDFs.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from illumenate_lighting.illumenate_lighting.api.authoring_contract import record_issues


def validate(path, doctype=None):
	doctype = doctype or Path(path).stem
	schemas = [
		json.loads(file.read_text(encoding="utf-8"))
		for file in (ROOT / "illumenate_lighting/illumenate_lighting/doctype").glob("*/*.json")
	]
	schema = next((doc for doc in schemas if doc.get("name") == doctype), None)
	if not schema or not (doctype.startswith("ilL-Spec-") or doctype.endswith("Submittal-Mapping")):
		raise ValueError(
			"Choose a shipped Spec or Submittal-Mapping DocType; child-table template imports use native Data Import"
		)
	columns = {
		key: field for field in schema["fields"] for key in (field["fieldname"], field.get("label")) if key
	}
	errors = []
	with Path(path).open(newline="", encoding="utf-8-sig") as source:
		reader = csv.DictReader(source)
		headers = reader.fieldnames or []
		if not headers or len(headers) != len(set(headers)):
			raise ValueError("CSV requires unique, nonempty headers")
		for header in headers:
			if header not in columns and header not in ("ID", "name"):
				errors.append(
					{"row": 1, "field": header, "message": "Unknown field label/name for this DocType"}
				)
		for index, values in enumerate(reader, 2):
			if None in values:
				errors.append({"row": index, "field": "columns", "message": "More values than headers"})
			data = {columns[key]["fieldname"]: value for key, value in values.items() if key in columns}
			data["name"] = values.get("ID") or values.get("name") or data.get("item") or f"row-{index}"
			for field in schema["fields"]:
				value = data.get(field["fieldname"])
				if (
					field.get("reqd")
					and not value
					and field.get("default") is None
					and field["fieldtype"] not in ("Table", "Section Break", "Column Break")
				):
					errors.append(
						{"row": index, "field": field["fieldname"], "message": "Required field is blank"}
					)
				if (
					field["fieldtype"] == "Select"
					and value
					and value not in str(field.get("options") or "").split("\n")
				):
					errors.append(
						{"row": index, "field": field["fieldname"], "message": "Unknown Select value"}
					)
			# Driver/controller input protocols are child tables: native import and
			# linked-record readiness validate those, not this flat-file preflight.
			if doctype not in ("ilL-Spec-Driver", "ilL-Spec-Controller"):
				errors.extend({"row": index, **issue} for issue in record_issues(doctype, data))
	return {"doctype": doctype, "valid": not errors, "issues": errors, "linked_records_verified": False}


def main():
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("csv")
	parser.add_argument("--doctype")
	args = parser.parse_args()
	result = validate(args.csv, args.doctype)
	print(json.dumps(result, indent=2))
	return 0 if result["valid"] else 1


if __name__ == "__main__":
	raise SystemExit(main())
