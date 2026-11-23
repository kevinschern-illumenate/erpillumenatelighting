"""Dry-run quote every fixture template in the given catalogs on the site (nothing is saved).

    python -m tools.catalog_expansion.verify --site https://<site> catalogs/fixture_*.yaml

Each template is quoted with its default finish, lens and mounting and its first Dry tape
offering through ``configurator_engine.validate_and_quote`` with ``_skip_record_creation``,
so no ilL-Configured-Fixture is created. Prints the unit MSRP and resolved parts.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request

import yaml

QUOTE = "/api/method/illumenate_lighting.illumenate_lighting.api.configurator_engine.validate_and_quote"


def quote(site, template, finish, lens, mount, offering, environment="Dry", length_mm=1219):
	args = dict(
		fixture_template_code=template,
		finish_code=finish,
		lens_appearance_code=lens,
		mounting_method_code=mount,
		endcap_style_start_code="Feed Through",
		endcap_style_end_code="Solid",
		power_feed_type_code="Soldered-End",
		environment_rating_code=environment,
		tape_offering_id=offering,
		requested_overall_length_mm=length_mm,
		_skip_record_creation=1,
		include_power_supply=0,
	)
	request = urllib.request.Request(
		site.rstrip("/") + QUOTE,
		data=json.dumps(args).encode(),
		headers={"Content-Type": "application/json"},
		method="POST",
	)
	try:
		with urllib.request.urlopen(request, timeout=120) as response:
			return json.load(response)["message"]
	except urllib.error.HTTPError as error:
		return {"is_valid": False, "error": error.read().decode(errors="replace")[:400]}


def default(options, option_type, field):
	rows = [row for row in options if row["option_type"] == option_type]
	return next((row[field] for row in rows if row.get("is_default")), rows[0][field] if rows else None)


def run(site, paths):
	failed = 0
	for path in paths:
		catalog = yaml.safe_load(open(path))
		for template in catalog["records"].get("ilL-Fixture-Template", []):
			options = template["allowed_options"]
			offering = next(
				row["tape_offering"]
				for row in template["allowed_tape_offerings"]
				if row["environment_rating"] == "Dry"
			)
			result = quote(
				site,
				template["template_code"],
				default(options, "Finish", "finish"),
				default(options, "Lens Appearance", "lens_appearance"),
				default(options, "Mounting Method", "mounting_method"),
				offering,
			)
			if result.get("is_valid"):
				parts = result.get("resolved_items") or {}
				print(
					"ok  ",
					template["template_code"],
					result["pricing"].get("msrp_unit"),
					parts.get("profile_item"),
					parts.get("lens_item"),
					parts.get("mounting_item"),
				)
			else:
				failed += 1
				errors = [
					m.get("text") for m in result.get("messages", []) if m.get("severity") == "error"
				] or [result.get("error")]
				print("FAIL", template["template_code"], errors[:3])
	return failed


if __name__ == "__main__":
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("--site", required=True)
	parser.add_argument("paths", nargs="+")
	args = parser.parse_args()
	raise SystemExit(1 if run(args.site, args.paths) else 0)
