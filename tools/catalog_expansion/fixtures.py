"""Linear fixture templates for every price-listed profile family that lacks them.

Each new template ``ILL-<family>-<package>`` (SW, DW, TW, FS) is assembled from records
already on the site:

* options (finishes, lenses, mounting methods, endcap styles) from the family's extrusion
  kit, the same components the kit ships with;
* price per foot from the price list: the cheapest standard-output Dry line for the package;
  lens and mounting upgrades become per-foot ``msrp_adder`` values (the price-list difference
  between kit lines), Damp +0.50/ft as on the price list;
* tape offerings, feed lengths, driver eligibility and spec submittal field mappings copied
  from the active Rainier [SF] / St. Helens [SF] template of the same LED package;
* endcap and mounting accessory maps from the kit's endcap and mounting maps.

Existing templates are never touched: a code that already exists (including retired
``zzz_`` drafts' live replacements) is skipped.
"""

from __future__ import annotations

from collections import OrderedDict

from .common import clean_child

PACKAGES = OrderedDict(
	(("SW", "Static White"), ("DW", "Dim to Warm"), ("TW", "Tunable White"), ("FS", "Full Spectrum"))
)
REFERENCE = ("ILL-RA01-{}", "ILL-SH01-{}")  # active templates the shared rows are copied from
ENVIRONMENTS = ("Dry", "Damp")
DAMP_ADDER = 0.5
FINISH_DEFAULT_ORDER = ("Anodized Silver", "Black", "White")
LENS_DEFAULT_ORDER = ("White", "Frosted")
# Price-list lens codes that differ from the Lens Appearance attribute codes.
LENS_ALIASES = {"OH": "OX"}
POWER_FEED = "Soldered-End"


def _codes(snapshot, doctype):
	return {row.get("code"): name for name, row in snapshot.all(doctype).items() if row.get("code")}


def _first(values, order):
	for preferred in order:
		if preferred in values:
			return preferred
	return values[0] if values else None


def _kit_options(kit, option_type, field):
	seen = []
	for row in kit.get("allowed_options", []):
		if row.get("option_type") == option_type and row.get(field) and row[field] not in seen:
			seen.append(row[field])
	return seen


def pricing(lines, family, lens_codes, mount_codes):
	"""Base price per package and per-foot lens/mount adders from the price list.

	The price list prices a fixture as kit MSRP / kit length + tape MSRP/ft, so a lens or
	mounting upgrade adds the same amount per foot to every package. Adders are measured on
	the Static White standard-output Dry lines; base prices per package are the cheapest line.
	"""
	family_lines = [
		line for line in lines if line.family == family and line.environment == "20" and not line.high_output
	]
	if not family_lines:
		return None
	base = {}
	for package in PACKAGES:
		prices = [line.msrp for line in family_lines if line.package == package]
		if prices:
			base[package] = round(min(prices), 2)
	sw = [line for line in family_lines if line.package == "SW"] or family_lines
	floor = min(line.msrp for line in sw)
	cheapest = min(sw, key=lambda line: line.msrp)
	default_lenses = set(cheapest.lenses)
	mount_adder = {}
	for line in sw:
		if default_lenses & set(line.lenses):
			for mount in line.mounts:
				mount_adder[mount] = min(mount_adder.get(mount, 1e9), line.msrp - floor)
	lens_adder = {}
	for line in sw:
		least_mount = min((mount_adder.get(m, 0) for m in line.mounts), default=0)
		for lens in line.lenses:
			lens_adder[lens] = min(lens_adder.get(lens, 1e9), line.msrp - floor - least_mount)
	by_lens = {
		lens_codes.get(LENS_ALIASES.get(code, code)): round(max(value, 0), 2)
		for code, value in lens_adder.items()
		if lens_codes.get(LENS_ALIASES.get(code, code))
	}
	by_mount = {
		mount_codes.get(code): round(max(value, 0), 2)
		for code, value in mount_adder.items()
		if mount_codes.get(code)
	}
	return {"base": base, "lens": by_lens, "mount": by_mount, "name": cheapest.name}


def _count_uom(uom):
	return not uom or "pack" not in uom.lower()


def _qty_rule(accessory):
	rule = (accessory or {}).get("qty_rule_type") or "Per x mm"
	value = float((accessory or {}).get("qty_rule_value") or 0)
	if rule.lower().startswith("per x") and value:
		return {"qty_rule_type": "PER_X_MM", "qty_rule_value": value, "min_qty": 2, "rounding": "CEIL"}
	return {"qty_rule_type": "PER_X_MM", "qty_rule_value": 304.8, "min_qty": 2, "rounding": "CEIL"}


def kit_components(snapshot, lines, family):
	"""The family's components: from its extrusion kit, or, without one, from its own records.

	Without a kit, finishes come from the profile specs, lenses from the profiles'
	Profile-Lens relationships, mounting methods from the price list's kit line, and endcaps
	and mounting accessories from the family's accessory specs.
	"""
	kit = snapshot.get("ilL-Extrusion-Kit-Template", f"KIT-{family}")
	if kit:
		return {
			"source": kit["name"],
			"series": kit.get("series"),
			"finishes": _kit_options(kit, "Finish", "finish"),
			"lenses": _kit_options(kit, "Lens Appearance", "lens_appearance"),
			"mounts": _kit_options(kit, "Mounting Method", "mounting_method"),
			"styles": _kit_options(kit, "Endcap Style", "endcap_style"),
			"endcaps": [
				{k: row[k] for k in ("endcap_style", "endcap_color", "endcap_item")}
				for row in snapshot.where("ilL-Rel-Kit-Endcap-Map", kit_template=kit["name"])
				if row.get("is_active") and row.get("endcap_item")
			],
			"mounting": [
				{k: row[k] for k in ("mounting_method", "accessory_item")}
				for row in snapshot.where("ilL-Rel-Kit-Mounting-Map", kit_template=kit["name"])
				if row.get("is_active") and row.get("accessory_item")
			],
			"lens_specs": [
				row["lens_spec"]
				for row in snapshot.where("ilL-Rel-Kit-Lens-Map", kit_template=kit["name"])
				if row.get("lens_spec")
			],
		}
	profiles = [p for p in snapshot.where("ilL-Spec-Profile", family=family) if p.get("is_active")]
	finish_by_code = {row.get("code"): name for name, row in snapshot.all("ilL-Attribute-Finish").items()}
	lens_specs = []
	for profile in profiles:
		relation = snapshot.get("ilL-Rel-Profile Lens", profile["name"]) or {}
		lens_specs += [
			row["lens_spec"] for row in relation.get("compatible_lenses", []) if row.get("lens_spec")
		]
	lens_specs = list(dict.fromkeys(lens_specs))
	lenses = list(
		dict.fromkeys(
			(snapshot.get("ilL-Spec-Lens", spec) or {}).get("lens_appearance") for spec in lens_specs
		)
	)
	mount_codes = _codes(snapshot, "ilL-Attribute-Mounting Method")
	mounts = list(
		dict.fromkeys(
			mount_codes[code]
			for line in lines
			if line.family == family
			for code in line.mounts
			if code in mount_codes
		)
	)
	accessories = [a for a in snapshot.where("ilL-Spec-Accessory", profile_family=family)]
	endcaps = []
	for accessory in accessories:
		if accessory.get("type") == "Endcap" and accessory.get("endcap_style"):
			color = accessory["item"].split("-")[2] if accessory["item"].count("-") >= 3 else None
			if color:
				endcaps.append(
					{
						"endcap_style": accessory["endcap_style"],
						"endcap_color": color,
						"endcap_item": accessory["item"],
					}
				)
	mounting = [
		{"mounting_method": a["mounting_method"], "accessory_item": a["item"]}
		for a in accessories
		if a.get("type") == "Mounting" and a.get("mounting_method") in mounts
	]
	return {
		"source": "family records (no extrusion kit)",
		"series": profiles[0].get("series") if profiles else None,
		"finishes": [
			finish_by_code[p["variant_code"]] for p in profiles if p.get("variant_code") in finish_by_code
		],
		"lenses": [lens for lens in lenses if lens],
		"mounts": mounts,
		"styles": list(dict.fromkeys(row["endcap_style"] for row in endcaps)),
		"endcaps": endcaps,
		"mounting": mounting,
		"lens_specs": lens_specs,
	}


def build_family(snapshot, lines, family, notes):
	"""Records for one family's new templates, or None when it cannot be built."""
	profiles = {
		p["variant_code"]: p for p in snapshot.where("ilL-Spec-Profile", family=family) if p.get("is_active")
	}
	if not profiles:
		notes.append(
			f"{family}: skipped, the site has no profile specs for this family (add its profile Items and specs first)"
		)
		return None
	finish_codes = {name: row.get("code") for name, row in snapshot.all("ilL-Attribute-Finish").items()}
	price = pricing(
		lines,
		family,
		_codes(snapshot, "ilL-Attribute-Lens Appearance"),
		_codes(snapshot, "ilL-Attribute-Mounting Method"),
	)
	if not price:
		notes.append(f"{family}: skipped, not on the price list")
		return None
	parts = kit_components(snapshot, lines, family)
	finishes = [f for f in parts["finishes"] if finish_codes.get(f) in profiles]
	lenses, mounts = parts["lenses"], parts["mounts"]
	styles = parts["styles"] or ["Solid", "Feed Through"]
	if not finishes or not lenses:
		notes.append(f"{family}: skipped, no finish or lens options found ({parts['source']})")
		return None
	default_finish = _first(finishes, FINISH_DEFAULT_ORDER)
	zero_lenses = [lens for lens in lenses if not price["lens"].get(lens)]
	default_lens = _first(zero_lenses or lenses, LENS_DEFAULT_ORDER)
	zero_mounts = [m for m in mounts if not price["mount"].get(m)]
	default_mount = (zero_mounts or mounts or [None])[0]
	default_profile = profiles[finish_codes[default_finish]]
	series = default_profile.get("series") or parts["series"]

	options = []
	for finish in finishes:
		options.append(
			{
				"option_type": "Finish",
				"finish": finish,
				"is_default": int(finish == default_finish),
				"is_active": 1,
			}
		)
	for lens in lenses:
		row = {
			"option_type": "Lens Appearance",
			"lens_appearance": lens,
			"is_default": int(lens == default_lens),
			"is_active": 1,
		}
		if price["lens"].get(lens):
			row["msrp_adder"] = price["lens"][lens]
		options.append(row)
	for mount in mounts:
		row = {
			"option_type": "Mounting Method",
			"mounting_method": mount,
			"is_default": int(mount == default_mount),
			"is_active": 1,
		}
		if price["mount"].get(mount):
			row["msrp_adder"] = price["mount"][mount]
		options.append(row)
	for style in styles:
		options.append({"option_type": "Endcap Style", "endcap_style": style, "is_active": 1})
	options.append({"option_type": "Power Feed Type", "power_feed_type": POWER_FEED, "is_active": 1})
	for environment in ENVIRONMENTS:
		row = {"option_type": "Environment Rating", "environment_rating": environment, "is_active": 1}
		if environment == "Damp":
			row["msrp_adder"] = DAMP_ADDER
		options.append(row)

	endcaps, mounting = parts["endcaps"], parts["mounting"]
	# The fixture configurator counts endcaps and clips as pieces; an Item stocked in packs
	# fails every quote, so such a family is offered to staff only until its UOM is fixed.
	packs = sorted(
		{
			row[key]
			for row, key in [(r, "endcap_item") for r in endcaps] + [(r, "accessory_item") for r in mounting]
			if not _count_uom((snapshot.get("Item", row[key]) or {}).get("stock_uom"))
		}
	)
	status = "Internal Only" if packs else "Active"
	if packs:
		notes.append(
			f"{family}: {', '.join(packs)} stocked as '{snapshot.get('Item', packs[0]).get('stock_uom')}', which the fixture "
			"configurator rejects for piece-counted parts; templates set to Internal Only until the stock UOM is Ea"
		)
	records = {
		"ilL-Fixture-Template": [],
		"ilL-Rel-Endcap-Map": [],
		"ilL-Rel-Mounting-Accessory-Map": [],
		"ilL-Rel-Driver-Eligibility": [],
		"ilL-Spec-Submittal-Mapping": [],
		"ilL-Rel-Profile Lens": [],
	}
	built, existing = [], []
	for package, label in PACKAGES.items():
		code = f"ILL-{family}-{package}"
		if snapshot.exists("ilL-Fixture-Template", code):
			existing.append(package)
			continue
		if package not in price["base"]:
			notes.append(f"{code}: skipped, no {label} price on the price list")
			continue
		reference = next(
			(
				snapshot.get("ilL-Fixture-Template", pattern.format(package))
				for pattern in REFERENCE
				if snapshot.get("ilL-Fixture-Template", pattern.format(package))
			),
			None,
		)
		offerings, seen = [], set()
		for pattern in REFERENCE:
			source = snapshot.get("ilL-Fixture-Template", pattern.format(package)) or {}
			for row in source.get("allowed_tape_offerings", []):
				if row.get("environment_rating") in ENVIRONMENTS and row["tape_offering"] not in seen:
					seen.add(row["tape_offering"])
					offerings.append(clean_child(row, {"tape_offering", "environment_rating", "is_default"}))
		template = {
			"template_code": code,
			"template_name": f"{price['name']} {label}",
			"product_status": status,
			"is_active": 1,
			"series": series,
			"default_profile_family": family,
			"default_profile_spec": default_profile["name"],
			"default_profile_stock_len_mm": int(default_profile.get("stock_length_mm") or 2000),
			"assembled_max_len_mm": int(default_profile.get("max_assembled_length_mm") or 2500),
			"leader_allowance_mm_per_fixture": 15,
			"price_per_ft_msrp": price["base"][package],
			"pricing_length_basis": "L_mfg",
			"auto_populate_configurator": 1,
			"allowed_options": [dict(row) for row in options],
			"allowed_tape_offerings": offerings,
		}
		if reference and reference.get("feed_lengths"):
			template["feed_lengths"] = [
				clean_child(r, {"step", "label", "code", "display_order"}) for r in reference["feed_lengths"]
			]
		records["ilL-Fixture-Template"].append(template)
		for row in endcaps:
			records["ilL-Rel-Endcap-Map"].append(
				{
					"fixture_template": code,
					"endcap_style": row["endcap_style"],
					"endcap_color": row["endcap_color"],
					"power_feed_type": POWER_FEED,
					"endcap_item": row["endcap_item"],
					"is_active": 1,
				}
			)
		for row in mounting:
			accessory = snapshot.get("ilL-Spec-Accessory", row["accessory_item"])
			records["ilL-Rel-Mounting-Accessory-Map"].append(
				{
					"template_type": "ilL-Fixture-Template",
					"fixture_template": code,
					"mounting_method": row["mounting_method"],
					"accessory_item": row["accessory_item"],
					**_qty_rule(accessory),
					"is_active": 1,
				}
			)
		drivers = (
			sorted(
				{
					row["driver_spec"]
					for row in snapshot.where(
						"ilL-Rel-Driver-Eligibility", fixture_template=reference["name"]
					)
					if row.get("is_allowed") and row.get("is_active")
				}
			)
			if reference
			else []
		)
		for driver in drivers:
			records["ilL-Rel-Driver-Eligibility"].append(
				{
					"template_type": "ilL-Fixture-Template",
					"fixture_template": code,
					"driver_spec": driver,
					"is_allowed": 1,
					"is_active": 1,
				}
			)
		if reference:
			for row in sorted(
				snapshot.where("ilL-Spec-Submittal-Mapping", fixture_template=reference["name"]),
				key=lambda r: r["pdf_field_name"],
			):
				mapping = clean_child(
					row,
					{
						"pdf_field_name",
						"source_doctype",
						"source_field",
						"prefix",
						"suffix",
						"transformation",
						"logic",
						"webflow_field",
						"webflow_skip_transformation",
						"webflow_prefix_suffix",
						"webflow_prefix",
						"webflow_suffix",
						"required_value",
					},
				)
				records["ilL-Spec-Submittal-Mapping"].append({"fixture_template": code, **mapping})
		built.append(code)

	# Profiles the fixture configurator cannot resolve lenses for get a Profile-Lens relationship.
	kit_lenses = parts["lens_specs"]
	if built and kit_lenses:
		for profile in profiles.values():
			if not snapshot.exists("ilL-Rel-Profile Lens", profile["name"]):
				records["ilL-Rel-Profile Lens"].append(
					{
						"profile_spec": profile["name"],
						"profile_item": profile.get("item") or profile["name"],
						"series": series,
						"is_active": 1,
						"compatible_lenses": [{"lens_spec": lens} for lens in dict.fromkeys(kit_lenses)],
					}
				)
	if existing:
		notes.append(
			f"{family}: {'/'.join(existing)} already exist{'s' if len(existing) == 1 else ''}, left unchanged"
		)
	if built and not endcaps:
		notes.append(f"{family}: no endcap items found; map endcaps before ordering")
	if built and parts["source"].startswith("family"):
		notes.append(
			f"{family}: no extrusion kit on the site, so components come from its own profile, lens and accessory records"
		)
	return {"series": series, "name": price["name"], "templates": built, "records": records, "price": price}
