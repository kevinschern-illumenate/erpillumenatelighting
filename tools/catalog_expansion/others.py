"""Tape, neon, extrusion kit, driver and controller templates the site is missing.

Each product is priced from the price list and patterned on the closest active template
of the same kind: its options, certifications, feed lengths, driver eligibility and
submittal mappings are copied, and the specs for the new Items are copied from a sibling
spec with the values that differ (package, lumens, watts scaled with lumens, CRI) replaced.
The Items themselves already exist on the site; only specs, offerings, leader-cable maps,
templates and their relationships are inserted.
"""

from __future__ import annotations

import re

from .common import SYSTEM, clean_child

ENV = {"20": "Dry", "54": "Damp", "67": "Wet"}
ENV_ADDER = {"Dry": 0.0, "Damp": 0.5, "Wet": 1.0}
CCT_CODES = {
	"27K": "2700K",
	"30K": "3000K",
	"35K": "3500K",
	"40K": "4000K",
	"1840K": "1800K-4000K",
	"2765K": "2700K-6500K",
	"1830K": "1800K-3000K",
	"1835K": "1800K-3500K",
	"RGB27K": "RGB + 2700K",
	"RGB30K": "RGB + 3000K",
	"RGB40K": "RGB + 4000K",
}
LED_PACKAGES = {
	"SW": "ilLumenate Static White",
	"TW": "ilLumenate Tunable White",
	"CC": "ilLumenate RGBW",
	"PX": "ilLumenate Color Changing Pixel",
}
# Option rows rebuilt from the new specs; every other option row is copied from the pattern.
REBUILT = {"CCT", "Output Level", "Environment Rating"}
DRIVERS_FROM = {"SW": "cob-sd-sw", "multi": "cob-sd-tw"}

# One entry per new tape/neon template. ``items`` matches the Items (already on the site)
# that become its specs; ``price`` is the price-list row the per-foot MSRP comes from.
TAPES = [
	dict(
		code="cob-hd-sw",
		name="High CRI Static White COB Tape",
		category="COB Tape",
		series="COB Tape",
		pattern="cob-sd-sw",
		spec="COB-SD-SW-20-27K-300-3M-WH-8MM",
		package="SW",
		items=r"^COB-HD-SW-(20|54|67)-(27K|30K|35K|40K)-300-3M-WH-8MM$",
		price="COB-HD-SW-20-[27K/30K/35K/40K]-300-3M-WH-8MM",
		cri="95+",
		sdcm="1",
		cri_typical=95,
	),
	dict(
		code="cob-tl-sw",
		name="Thin Static White COB Tape (3mm)",
		category="COB Tape",
		series="COB Tape",
		pattern="cob-sd-sw",
		spec="COB-SD-SW-20-27K-300-3M-WH-8MM",
		package="SW",
		items=r"^COB-TL-SW-20-(27K|30K|35K|40K)-150-3M-WH-3MM$",
		price="COB-TL-SW-20-[27K/30K/35K/40K]-150-3M-WH-3MM",
		dimensions="3mm wide",
	),
	dict(
		code="cob-sd-cc",
		name="Standard Color Changing (RGBW) COB Tape",
		category="COB Tape",
		series="COB Tape",
		pattern="cob-sd-px",
		spec="LED-HD-CC-20-RGB30K-400-3M-WH-12MM",
		package="CC",
		items=r"^COB-SD-CC-(20|54|67)-(RGB30K|RGB40K)-100-3M-WH-12MM$",
		price="COB-SD-CC-20-[RGB30K/RGB35K/RGB40K]-100-3M-WH-10MM",
		drop_options={"Feed Direction", "Power Feed Type"},
	),
	dict(
		code="cob-sn-tw",
		name="Sauna Tunable White COB Tape",
		category="COB Tape",
		series="COB Tape",
		pattern="cob-sn-sw",
		spec="COB-SD-TW-67-2765K-200-3M-WH",
		package="TW",
		items=r"^COB-SN-TW-67-2765K-200-3M-WH-12MM$",
		price="COB-SN-TW-67-2765K-200-3M-WH-12MM",
	),
	dict(
		code="cob-sn-cc",
		name="Sauna Color Changing (RGBW) COB Tape",
		category="COB Tape",
		series="COB Tape",
		pattern="cob-sn-sw",
		spec="LED-HD-CC-67-RGB30K-400-3M-WH-12MM",
		package="CC",
		items=r"^COB-SN-CC-67-(RGB30K|RGB40K)-50-3M-WH-12MM$",
		price="COB-SN-CC-67-[RGB30K/RGB40K]-50-3M-WH-12MM",
		output_names={"50": "50lm/ft"},
	),
	dict(
		code="led-tl-sw",
		name="Thin Static White LED Tape",
		category="LED Tape",
		series="LED Tape",
		pattern="led-hd-sw",
		spec="LED-HD-SW-20-27K-300-3M-WH",
		package="SW",
		items=r"^LED-TL-SW-20-(27K|30K|35K|40K)-300-3M-WH$",
		price="LED-TL-SW-20-[27K/30K/35K/40K]-300-3M-WH",
	),
	dict(
		code="led-sd-px",
		name="Standard Density Pixel (RGBW) LED Tape",
		category="LED Tape",
		series="LED Tape",
		pattern="cob-sd-px",
		spec="COB-SD-PX-20-RGB30K-100-3M-WH",
		package="PX",
		items=r"^LED-SD-PX-(20|54|67)-(RGB30K|RGB40K)-250-3M-WH$",
		price="LED-SD-PX-20-[RGB30K/RGB40K]-250-3M-WH",
	),
	dict(
		code="non-pnc-tw",
		name="Pinnacle [DB] Tunable White LED Neon",
		category="LED Neon",
		series="Glacier",
		pattern="non-pnc-sw",
		spec="NON-PNC-SW-67-27K-150-WH",
		package="TW",
		channel_spec="COB-SD-TW-67-2765K-200-3M-WH",
		items=r"^NON-PNC-TW-67-(1840K|2765K)-150-WH$",
		price="NON-PNC-TW-67-[1840K/2765K]-150-WH",
		# The site prices Pinnacle well below the price list (SW $20 vs $55): keep the site's
		# Pinnacle SW price plus the price list's TW-over-SW difference.
		price_from_template=("non-pnc-sw", "NON-PNC-SW-67-[27K/30K/35K/40K]-[150/250]-WH"),
	),
	dict(
		code="non-rsk-sw",
		name="Rusk [TB] Static White LED Neon",
		category="LED Neon",
		series="Glacier",
		pattern="non-dgl-sw",
		spec="NON-DGL-SW-54-30K-150-WH",
		package="SW",
		items=r"^NON-RSK-SW-54-(27K|30K|35K|40K)-250$",
		price="NON-RSK-SW-54-[27K/30K/35K/40K]-250",
	),
]

DRIVERS = [
	dict(
		code="PS-DMX",
		name="DMX Dimming Constant Voltage Power Supply",
		pattern="PS-UNIV",
		spec_pattern="PS-UNIV-24V-100W-IP66",
		protocol="DMX512",
		variants=[
			("PS-DMX-24V-120W-IP66-4C", "PS-DMX-24V-120W-IP66-4 Channel (RGBW)", 120, 4, "4C"),
			("PS-DMX-24V-150W-IP66-4C", "PS-DMX-24V-150W-IP66-4 Channel (RGBW)", 150, 4, "4C"),
			("PS-DMX-24V-200W-IP66-2C", "PS-DMX-24V-200W-IP66-2 Channel (TW)", 200, 2, "2C"),
		],
	),
]

CONTROLLERS = [
	dict(
		item="DMXC-RGBW-BK-WALL",
		name="DMX512 / BLE Mesh In-Wall RGBW Controller",
		pattern="DMXC-RGBTW-BK-WALL",
		series="Bluetooth Mesh Decoder",
		input_protocols=["Touch", "Bluetooth Mesh"],
	),
	dict(
		item="DMXC-SC-BK-WALL",
		name="DMX512 / BLE Mesh In-Wall Single Color Controller",
		pattern="DMXC-TW-BK-WALL",
		series="Bluetooth Mesh Decoder",
		input_protocols=["Touch", "Bluetooth Mesh"],
	),
	dict(
		item="DMXS-SPLIT-2-DIN",
		name="DMX/RDM Signal Splitter / Amplifier - DIN Rail",
		pattern="DMXD-PWM-5C-SF",
		series="Bluetooth Mesh Decoder",
		spec={
			"controller_type": "Repeater",
			"mounting_type": "DIN Rail",
			"channels": 512,
			"zones": 1,
			"max_load_watts": 0,
			"max_load_amps": 0,
			"max_a_per_channel": 0,
			"max_w_per_channel": 0,
			"dmx_footprint": 0,
			"input_voltage_min": 12,
			"input_voltage_max": 24,
			"input_voltage_type": "VDC",
			"notes": "Two isolated DMX512/RDM outputs from one input; repeats and amplifies the DMX line.",
		},
		ports=[
			{"port_name": "DMX In", "direction": "In", "protocol": "DMX512"},
			{"port_name": "DMX Out 1", "direction": "Out", "protocol": "DMX512"},
			{"port_name": "DMX Out 2", "direction": "Out", "protocol": "DMX512"},
		],
		input_protocols=["DMX512"],
		output_protocols=["DMX512"],
		wireless=[],
	),
]

KITS = [
	dict(
		code="KIT-TW03",
		family="TW03",
		pattern="KIT-TW02",
		name="Tower [OP]-6.5ft Extrusion Kit",
		price="KIT-TW03-[OP/CL/FR/WH]-SF-[BK/SV/WH]",
	)
]


def _scalars(row, drop=()):
	return {
		k: v
		for k, v in row.items()
		if k not in SYSTEM and k not in drop and not isinstance(v, list) and v not in (None, "")
	}


def _children(rows, drop=()):
	return [{k: v for k, v in clean_child(r).items() if k not in drop} for r in rows or []]


def _price(prices, part):
	row = prices.find(part)
	return row.msrp if row else None


def _parse_tape(code):
	"""(environment code, cct code, lumens) from a tape Item code."""
	parts = code.split("-")
	env = next(p for p in parts if p in ENV)
	cct = parts[parts.index(env) + 1]
	lumens = parts[parts.index(env) + 2]
	return env, cct, lumens


def build_tape(snapshot, prices, product, notes):
	template_pattern = snapshot.get("ilL-Tape-Neon-Template", product["pattern"])
	spec_pattern = snapshot.get("ilL-Spec-LED Tape", product["spec"])
	if snapshot.exists("ilL-Tape-Neon-Template", product["code"]):
		notes.append(f"{product['code']}: already exists, left unchanged")
		return None
	if not template_pattern or not spec_pattern:
		notes.append(
			f"{product['code']}: skipped, pattern {product['pattern']} / {product['spec']} not on the site"
		)
		return None
	items = sorted(name for name in snapshot.all("Item") if re.match(product["items"], name))
	items = [name for name in items if not snapshot.exists("ilL-Spec-LED Tape", name)]
	if not items:
		notes.append(f"{product['code']}: skipped, no Items match {product['items']}")
		return None
	msrp = _price(prices, product["price"])
	if product.get("price_from_template"):
		site_template, list_part = product["price_from_template"]
		site_price = (snapshot.get("ilL-Tape-Neon-Template", site_template) or {}).get("price_per_ft_msrp")
		list_price = _price(prices, list_part)
		if site_price and list_price and msrp:
			notes.append(
				f"{product['code']}: price list says ${msrp:.2f}/ft, but the site prices {site_template} at ${site_price:.2f} "
				f"(list ${list_price:.2f}); priced at ${site_price + msrp - list_price:.2f} to match the site"
			)
			msrp = round(site_price + msrp - list_price, 2)
	if msrp is None:
		notes.append(f"{product['code']}: skipped, price list row {product['price']} not found")
		return None
	channel = snapshot.get("ilL-Spec-LED Tape", product.get("channel_spec") or product["spec"])
	pattern_lumens = float(spec_pattern.get("lumens_per_foot") or 0) or None
	package = LED_PACKAGES[product["package"]]
	specs, offerings, leaders, allowed = [], [], [], []
	ccts, outputs, envs = [], [], []
	for item in items:
		env_code, cct_code, lumens = _parse_tape(item)
		cct = CCT_CODES.get(cct_code)
		output = (product.get("output_names") or {}).get(lumens, f"{lumens} lm/ft")
		if not cct:
			notes.append(f"{product['code']}: {item} skipped, no CCT attribute for {cct_code}")
			continue
		spec = _scalars(spec_pattern, drop={"item", "name"})
		for key in (
			"channels",
			"power_basis",
			"max_simultaneous_pct",
			"input_protocol",
			"pixel_protocol",
			"drive_type",
		):
			if channel.get(key) not in (None, ""):
				spec[key] = channel[key]
		watts = float(spec_pattern.get("watts_per_foot") or 0)
		if pattern_lumens and watts:
			spec["watts_per_foot"] = round(watts * float(lumens) / pattern_lumens, 2)
		spec.update(
			item=item,
			led_package=package,
			product_category=product["category"],
			lumens_per_foot=float(lumens),
		)
		if product.get("cri_typical"):
			spec["cri_typical"] = product["cri_typical"]
		protocols = channel.get("supported_dimming_protocols") or spec_pattern.get(
			"supported_dimming_protocols"
		)
		if protocols:
			spec["supported_dimming_protocols"] = _children(protocols, drop={"name"})
		specs.append(spec)
		pattern_offering = next(
			iter(snapshot.where("ilL-Rel-Tape Offering", tape_spec=spec_pattern["name"])), {}
		)
		offerings.append(
			{
				"tape_spec": item,
				"cct": cct,
				"cri": product.get("cri") or pattern_offering.get("cri") or "90+",
				"sdcm": product.get("sdcm") or pattern_offering.get("sdcm") or "3",
				"led_package": package,
				"output_level": output,
				"is_active": 1,
			}
		)
		for row in snapshot.where("ilL-Rel-Leader-Cable-Map", tape_spec=spec_pattern["name"]):
			leader = {k: v for k, v in clean_child(row).items() if k not in ("tape_spec", "name")}
			leaders.append({"tape_spec": item, **leader})
		environment = ENV[env_code]
		allowed.append({"tape_spec": item, "environment_rating": environment})
		for bucket, value in ((ccts, cct), (outputs, output), (envs, environment)):
			if value not in bucket:
				bucket.append(value)

	options = []
	for environment in sorted(envs, key=list(ENV.values()).index):
		row = {
			"option_type": "Environment Rating",
			"environment_rating": environment,
			"feed_position": "Both",
			"is_active": 1,
		}
		if ENV_ADDER[environment]:
			row["msrp_adder"] = ENV_ADDER[environment]
		options.append(row)
	options += [{"option_type": "CCT", "cct": cct, "feed_position": "Both", "is_active": 1} for cct in ccts]
	options += [
		{"option_type": "Output Level", "output_level": o, "feed_position": "Both", "is_active": 1}
		for o in outputs
	]
	for row in template_pattern.get("allowed_options", []):
		if row.get("option_type") in REBUILT or row.get("option_type") in product.get("drop_options", ()):
			continue
		options.append(clean_child(row))

	template = _scalars(
		template_pattern,
		drop={
			"template_code",
			"template_name",
			"webflow_product",
			"spec_sheet",
			"spec_submittal_template",
			"photometry",
			"default_tape_spec",
			"price_per_ft_msrp",
			"product_category",
			"series",
			"description",
			"image",
			"hero_image",
			"hero_image_alt",
			"dimensions_image",
			"spec_sheet_dimensions",
			"beam_angle",
		},
	)
	template.update(
		template_code=product["code"],
		template_name=product["name"],
		product_category=product["category"],
		series=product["series"],
		product_status="Active",
		is_active=1,
		default_tape_spec=specs[0]["item"],
		price_per_ft_msrp=msrp,
		allowed_tape_specs=allowed,
		allowed_options=options,
	)
	if template_pattern.get("beam_angle"):
		template["beam_angle"] = template_pattern["beam_angle"]
	if product.get("dimensions"):
		template["spec_sheet_dimensions"] = product["dimensions"]
	for table in ("certifications", "feed_lengths"):
		if template_pattern.get(table):
			template[table] = _children(template_pattern[table], drop={"name"})
	# The site's rule: single-channel white tape takes universal dimming drivers; multi-channel
	# tape (tunable, colour, pixel) takes non-dimming drivers behind a decoder.
	source = DRIVERS_FROM["SW" if product["package"] == "SW" else "multi"]
	drivers = [
		{
			"template_type": "ilL-Tape-Neon-Template",
			"fixture_template": product["code"],
			"driver_spec": spec,
			"is_allowed": 1,
			"is_active": 1,
		}
		for spec in dict.fromkeys(
			row["driver_spec"]
			for row in snapshot.where("ilL-Rel-Driver-Eligibility", fixture_template=source)
			if row.get("is_allowed") and row.get("is_active")
		)
	]
	mappings = [
		{
			"tape_neon_template": product["code"],
			**{k: v for k, v in clean_child(row).items() if k not in ("tape_neon_template", "name")},
		}
		for row in sorted(
			snapshot.where("ilL-Neon-Submittal-Mapping", tape_neon_template=product["pattern"]),
			key=lambda r: r["pdf_field_name"],
		)
	]
	records = {
		"ilL-Spec-LED Tape": specs,
		"ilL-Rel-Tape Offering": offerings,
		"ilL-Rel-Leader-Cable-Map": leaders,
		"ilL-Tape-Neon-Template": [template],
		"ilL-Rel-Driver-Eligibility": drivers,
		"ilL-Neon-Submittal-Mapping": mappings,
	}
	product_type = "neon" if product["category"] == "LED Neon" else "tape"
	return {
		"slug": f"{product_type}_{product['code']}",
		"kind": product["category"],
		"label": product["name"],
		"product_type": product_type,
		"series": product["series"],
		"records": records,
		"templates": [product["code"]],
		"prices": {"per ft": msrp},
	}


def build_driver(snapshot, prices, product, notes):
	if snapshot.exists("ilL-Driver-Template", product["code"]):
		notes.append(f"{product['code']}: already exists, left unchanged")
		return None
	pattern = snapshot.get("ilL-Driver-Template", product["pattern"])
	spec_pattern = snapshot.get("ilL-Spec-Driver", product["spec_pattern"])
	specs, variants, options = [], [], []
	base = None
	for item, part, watts, _channels, channel_code in product["variants"]:
		if not snapshot.exists("Item", item):
			notes.append(f"{product['code']}: {item} skipped, Item not on the site")
			continue
		msrp = _price(prices, part)
		if msrp is None:
			notes.append(f"{product['code']}: {item} skipped, not on the price list")
			continue
		base = msrp if base is None else min(base, msrp)
		spec = _scalars(spec_pattern, drop={"item", "name", "cost"})
		usable = float(spec_pattern.get("usable_load_factor") or 0.8)
		spec.update(
			item=item,
			outputs_count=1,
			independent_outputs_count=1,
			max_wattage=round(watts * 0.96, 1),
			max_wattage_per_output=round(watts * 0.96, 1),
			usable_load_factor=usable,
			output_protocol="PWM",
			output_current_ma=round(watts / 24 * 1000, 0),
			sku_control_code="DMX",
			sku_wattage_output_code=f"{watts}W",
			sku_channel_code=channel_code,
			input_protocols=[{"protocol": product["protocol"], "is_default": 1}],
			certifications=_children(spec_pattern.get("certifications"), drop={"name"}),
		)
		specs.append(spec)
		variants.append(
			{
				"driver_spec": item,
				"is_active": 1,
				"variant_code": f"{watts}W-{channel_code}",
				"msrp": msrp,
				"wattage": float(watts),
				"voltage_output": spec.get("voltage_output") or "24VDC",
				"input_protocol": product["protocol"],
				"output_protocol": "PWM",
				"item": item,
				"outputs_count": 1,
				"input_voltage_min": spec.get("input_voltage_min"),
				"input_voltage_max": spec.get("input_voltage_max"),
				"input_voltage_type": spec.get("input_voltage_type"),
			}
		)
	if not variants:
		return None
	for variant in variants:
		watts = int(variant["wattage"])
		row = {
			"option_type": "Wattage",
			"option_value": str(watts),
			"option_label": variant["variant_code"].replace("-", " "),
			"option_code": variant["variant_code"],
			"is_active": 1,
		}
		if variant["msrp"] > base:
			row["msrp_adder"] = round(variant["msrp"] - base, 2)
		options.append(row)
	options += [
		{
			"option_type": "Voltage Output",
			"attribute_doctype": "ilL-Attribute-Output Voltage",
			"attribute_link": "24VDC",
			"is_active": 1,
		},
		{
			"option_type": "Input Protocol",
			"attribute_doctype": "ilL-Attribute-Dimming Protocol",
			"attribute_link": product["protocol"],
			"is_active": 1,
		},
		{
			"option_type": "Output Protocol",
			"attribute_doctype": "ilL-Attribute-Dimming Protocol",
			"attribute_link": "PWM",
			"is_active": 1,
		},
	]
	template = _scalars(
		pattern,
		drop={
			"template_code",
			"template_name",
			"webflow_product",
			"spec_sheet",
			"spec_submittal_template",
			"sku_series_code",
			"base_price_msrp",
		},
	)
	template.update(
		template_code=product["code"],
		template_name=product["name"],
		sku_series_code=product["code"],
		product_status="Active",
		is_active=1,
		base_price_msrp=base,
		variants=variants,
		allowed_options=options,
		certifications=_children(pattern.get("certifications"), drop={"name"}),
	)
	return {
		"slug": f"driver_{product['code'].lower()}",
		"kind": "Driver",
		"label": product["name"],
		"product_type": "driver",
		"series": pattern.get("series"),
		"records": {"ilL-Spec-Driver": specs, "ilL-Driver-Template": [template]},
		"templates": [product["code"]],
		"prices": {v["variant_code"]: v["msrp"] for v in variants},
	}


def build_controller(snapshot, prices, product, notes):
	item = product["item"]
	if snapshot.exists("ilL-Controller-Template", item) or snapshot.exists("ilL-Spec-Controller", item):
		notes.append(f"{item}: already exists, left unchanged")
		return None
	if not snapshot.exists("Item", item):
		notes.append(f"{item}: skipped, Item not on the site")
		return None
	msrp = _price(prices, item)
	pattern_spec = snapshot.get("ilL-Spec-Controller", product["pattern"])
	pattern_template = snapshot.get("ilL-Controller-Template", product["pattern"])
	spec = _scalars(pattern_spec, drop={"item", "name"})
	spec.update(item=item, controller_name=product["name"], is_active=1, **product.get("spec", {}))
	for table, key in (
		("input_protocols", "input_protocols"),
		("output_protocols", "output_protocols"),
		("wireless_protocols", "wireless"),
	):
		if key in product:
			spec[table] = [{"protocol": p} for p in product[key]]
		elif pattern_spec.get(table):
			spec[table] = _children(pattern_spec[table], drop={"name"})
	spec["ports"] = product.get("ports") or _children(pattern_spec.get("ports"), drop={"name"})
	variant = {
		k: v for k, v in clean_child((pattern_template.get("variants") or [{}])[0]).items() if k != "name"
	}
	variant.update(controller_spec=item, item=item, is_default=1, is_active=1)
	for key in ("channels", "zones", "input_voltage_min", "input_voltage_max", "input_voltage_type"):
		if key in spec:
			variant[key] = spec[key]
	if msrp:
		variant["msrp"] = msrp
	template = _scalars(
		pattern_template,
		drop={
			"template_code",
			"template_name",
			"webflow_product",
			"spec_sheet",
			"spec_submittal_template",
			"series",
		},
	)
	template.update(
		template_code=item,
		template_name=product["name"],
		series=product["series"],
		product_status="Active",
		is_active=1,
		variants=[variant],
	)
	if msrp:
		template["base_price_msrp"] = msrp
	return {
		"slug": f"controller_{item.lower()}",
		"kind": "Controller",
		"label": product["name"],
		"product_type": "controller",
		"series": product["series"],
		"records": {"ilL-Spec-Controller": [spec], "ilL-Controller-Template": [template]},
		"templates": [item],
		"prices": {"each": msrp} if msrp else {},
	}


def build_kit(snapshot, prices, product, notes):
	code, family = product["code"], product["family"]
	if snapshot.exists("ilL-Extrusion-Kit-Template", code):
		notes.append(f"{code}: already exists, left unchanged")
		return None
	pattern = snapshot.get("ilL-Extrusion-Kit-Template", product["pattern"])
	source = pattern["default_profile_family"]
	profiles = {
		p["variant_code"]: p for p in snapshot.where("ilL-Spec-Profile", family=family) if p.get("is_active")
	}
	finish_codes = {name: row.get("code") for name, row in snapshot.all("ilL-Attribute-Finish").items()}
	relation = snapshot.get("ilL-Rel-Profile Lens", next(iter(profiles.values()))["name"]) or {}
	lenses = {
		(snapshot.get("ilL-Spec-Lens", row["lens_spec"]) or {}).get("lens_appearance"): row["lens_spec"]
		for row in relation.get("compatible_lenses", [])
	}
	endcaps = [
		a for a in snapshot.where("ilL-Spec-Accessory", profile_family=family) if a.get("type") == "Endcap"
	]
	msrp = _price(prices, product["price"])

	def rename(value):
		return value.replace(source, family) if isinstance(value, str) else value

	template = _scalars(
		pattern,
		drop={
			"template_code",
			"template_name",
			"webflow_product",
			"spec_sheet",
			"spec_submittal_template",
			"notes",
			"default_profile_family",
			"default_profile_spec",
			"default_lens_spec",
			"base_price_msrp",
			"image",
			"hero_image",
			"dimensions_image",
		},
	)
	default_profile = profiles.get("SV") or next(iter(profiles.values()))
	components = []
	for row in pattern.get("kit_components", []):
		row = clean_child(
			row,
			{
				"component_type",
				"component_item",
				"component_spec_doctype",
				"component_spec_name",
				"quantity",
				"component_description",
			},
		)
		if row["component_type"] == "Lens":
			continue
		row["component_item"] = rename(row["component_item"])
		row["component_spec_name"] = rename(row["component_spec_name"])
		if snapshot.exists("Item", row["component_item"]):
			components.append(row)
	for appearance, spec in lenses.items():
		components.append(
			{
				"component_type": "Lens",
				"component_item": spec,
				"component_spec_doctype": "ilL-Spec-Lens",
				"component_spec_name": spec,
				"quantity": 1,
				"component_description": appearance,
			}
		)
	options = [
		clean_child(r)
		for r in pattern.get("allowed_options", [])
		if r.get("option_type") != "Lens Appearance"
	]
	options += [{"option_type": "Lens Appearance", "lens_appearance": a, "is_active": 1} for a in lenses]
	specs = []
	for row in pattern.get("specifications", []):
		row = clean_child(row)
		if row.get("spec_label") == "Lenses":
			row["spec_value"] = ", ".join(lenses)
		if row.get("spec_label") == "Dimensions" and default_profile.get("dimensions"):
			row["spec_value"] = default_profile["dimensions"]
		specs.append(row)
	template.update(
		template_code=code,
		template_name=product["name"],
		product_status="Active",
		is_active=1,
		default_profile_family=family,
		default_profile_spec=default_profile["name"],
		default_lens_spec=next(iter(lenses.values())),
		base_price_msrp=msrp or pattern.get("base_price_msrp"),
		allowed_options=options,
		kit_components=components,
		specifications=specs,
		part_no_configurator=_children(pattern.get("part_no_configurator"), drop={"name"}),
		notes="Built from the 10-2026 price list kit group by the Nov 2026 catalog expansion.",
	)
	for row in template["part_no_configurator"]:
		if row.get("option_type") == "Lens Appearance":
			import json

			codes = {name: r.get("code") for name, r in snapshot.all("ilL-Attribute-Lens Appearance").items()}
			row["allowed_values_json"] = json.dumps(
				[{"code": codes.get(a), "is_default": 0, "label": a} for a in lenses], indent=1
			)
	records = {
		"ilL-Extrusion-Kit-Template": [template],
		"ilL-Rel-Kit-Profile-Map": [
			{
				"kit_template": code,
				"finish": f,
				"profile_spec": p["name"],
				"profile_item": p.get("item") or p["name"],
				"is_active": 1,
			}
			for f, c in finish_codes.items()
			for vc, p in profiles.items()
			if vc == c
		],
		"ilL-Rel-Kit-Lens-Map": [
			{"kit_template": code, "lens_appearance": a, "lens_spec": s, "lens_item": s, "is_active": 1}
			for a, s in lenses.items()
		],
		"ilL-Rel-Kit-Endcap-Map": [
			{
				"kit_template": code,
				"endcap_style": a["endcap_style"],
				"endcap_color": a["item"].split("-")[2],
				"endcap_type": "Feed-Through" if a["endcap_style"] == "Feed Through" else "Solid",
				"endcap_spec": a["name"],
				"endcap_item": a["item"],
				"is_active": 1,
			}
			for a in endcaps
		],
	}
	return {
		"slug": f"kit_{family.lower()}",
		"kind": "Extrusion Kit",
		"label": product["name"],
		"product_type": "extrusion-kit",
		"series": pattern.get("series"),
		"records": records,
		"templates": [code],
		"prices": {"kit": msrp} if msrp else {},
	}


def build_all(snapshot, prices, notes):
	out = []
	for product in TAPES:
		result = build_tape(snapshot, prices, product, notes)
		if result:
			out.append(result)
	for product in KITS:
		result = build_kit(snapshot, prices, product, notes)
		if result:
			out.append(result)
	for product in DRIVERS:
		result = build_driver(snapshot, prices, product, notes)
		if result:
			out.append(result)
	for product in CONTROLLERS:
		result = build_controller(snapshot, prices, product, notes)
		if result:
			out.append(result)
	return out
