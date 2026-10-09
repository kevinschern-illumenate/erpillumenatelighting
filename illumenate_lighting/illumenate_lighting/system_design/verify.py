# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Python mirror of the gating engine checks (plan §18.2, H10, WP-3.6).

The designer's TypeScript engine owns the calculation; this module re-computes the subset that gates
an order so the server does not rely on the browser: supply and output loading against ratings and
the operating target, Class 2 output load, tape run length, voltage drop and wire selection on
single-channel Class 2 DC runs (NEC Chapter 9 Table 8 resistance), voltage match, dealer data and the
D4 triggers. :func:`subset` returns the same shape as ``verifySubset`` in ``packages/engine/src/verify.ts``;
``tests/portal_unit/test_system_design_parity.py`` holds both to the golden fixtures.

Everything here is pure: designs, catalog items and wire types are the JSON the designer uses.
"""

import json
import math
from functools import cache
from pathlib import Path

from illumenate_lighting.illumenate_lighting.system_design.design_schema import VD_LOOSENED, round_number
from illumenate_lighting.illumenate_lighting.system_design.protocols import DMX_PROTOCOLS, PHASE_PROTOCOLS

CODE_TABLES_DIR = Path(__file__).resolve().parent / "code_tables"

VERIFY_CODES = frozenset(
	{
		"PSU_OVERLOAD",
		"PSU_ABOVE_DERATE",
		"CLASS2_OVER_100VA",
		"TAPE_RUN_TOO_LONG",
		"VOLTAGE_MISMATCH",
		"VD_OVER_TARGET",
		"NO_VALID_WIRE",
		"TAPE_UNDERVOLTAGE",
		"DATA_BY_DEALER",
	}
)
VERIFIED_RUN_TYPE = "class2-dc"
WIRE_CODES = frozenset({"VD_OVER_TARGET", "NO_VALID_WIRE", "TAPE_UNDERVOLTAGE"})
AWG_SMALL_TO_LARGE = (
	"24",
	"22",
	"20",
	"18",
	"16",
	"14",
	"12",
	"10",
	"8",
	"6",
	"4",
	"3",
	"2",
	"1",
	"1/0",
	"2/0",
	"3/0",
	"4/0",
)
IN_WALL_LISTINGS = frozenset({"CL2", "CL2R", "CL2P", "CL3", "CL3R", "CL3P"})
EPSILON = 1e-9

# Project settings defaults, as in ``ProjectSettingsSchema``.
SETTING_DEFAULTS = {
	"necEdition": "2023",
	"terminationTempC": 75,
	"vdTargetLineVoltagePct": 3,
	"vdTargetLowVoltagePct": 3,
	"vdTargetLandscapePct": 5,
	"psuDeratePct": 80,
	"continuousLoadFactor": 1.25,
	"tapeLengthMarginPct": 0,
}
# Design VD target -> System Designer Settings field and default (D5).
VD_TARGETS = {
	"vdTargetLowVoltagePct": ("vd_target_class2_pct", 3),
	"vdTargetLineVoltagePct": ("vd_target_line_pct", 3),
	"vdTargetLandscapePct": ("vd_target_landscape_pct", 5),
}
DEFAULT_GATE = {"watts": 1500, "dmx": True, "phase_dimming": True}


@cache
def code_tables():
	"""The NEC tables copied from ``packages/data/src/nec`` by the designer build."""
	return tuple(
		json.loads(path.read_text(encoding="utf-8")) for path in sorted(CODE_TABLES_DIR.glob("*.json"))
	)


def awg_size(awg):
	return AWG_SMALL_TO_LARGE.index(awg)


def vd_limits(settings):
	"""Settings VD targets (D5); invalid or missing values fall back to the defaults."""
	limits = {}
	for key, (field, fallback) in VD_TARGETS.items():
		value = (settings or {}).get(field)
		ok = (
			isinstance(value, (int, float))
			and not isinstance(value, bool)
			and math.isfinite(value)
			and value > 0
		)
		limits[key] = value if ok else fallback
	return limits


def effective_targets(design, limits):
	"""The project's targets where tighter than Settings, unless staff loosened them (``effectiveTargets``)."""
	settings = design["project"]["settings"]
	loosened = any(
		item.get("code") == VD_LOOSENED and item.get("kind") == "staff-override"
		for item in design.get("overrides") or []
	)
	targets = {}
	for key in VD_TARGETS:
		value = settings.get(key, SETTING_DEFAULTS[key])
		targets[key] = value if loosened else min(value, limits[key])
	return targets


def review_triggers(design, gate=None):
	"""D4 triggers from the design (``reviewTriggers``): connected load and zone methods in use."""
	gate = {**DEFAULT_GATE, **(gate or {})}
	used = {run.get("zoneId") for run in design["runs"] if run.get("zoneId")}
	methods = {zone["method"] for zone in design.get("zones") or [] if zone["id"] in used}
	triggers = []
	if sum(run["watts"] for run in design["runs"]) > gate["watts"]:
		triggers.append("LOAD_OVER_THRESHOLD")
	if gate["dmx"] and methods & DMX_PROTOCOLS:
		triggers.append("DMX")
	if gate["phase_dimming"] and methods & PHASE_PROTOCOLS:
		triggers.append("PHASE_DIMMING")
	return triggers


# Loads ---------------------------------------------------------------------------------------------


def _load_profile(load, spec, settings):
	"""``loadProfile`` for tape and fixtures: ``(watts, channel amps, current)``."""
	if spec["kind"] == "tape":
		length = (load.get("lengthFt") or 0) * (1 + settings["tapeLengthMarginPct"] / 100)
		rated = spec["wPerFtMax"] * length
		pixel = spec.get("pixel")
		if pixel:
			watts = math.ceil(length * pixel["pixelsPerFt"]) * pixel["ampsPerPixelMax"] * spec["voltage"]
		else:
			share = (
				1
				if spec["powerBasis"] == "max-operating"
				else spec["maxSimultaneousPct"] / (spec["channels"] * 100)
			)
			watts = rated * share
		per_channel = (
			spec.get("channelWPerFtMax") or [spec["wPerFtMax"] / spec["channels"]] * spec["channels"]
		)
		channels = [] if pixel else [(w * length) / spec["voltage"] for w in per_channel]
		return watts, channels, watts / spec["voltage"]
	if spec["kind"] == "fixture":
		watts = spec["watts"] * (load.get("qty") or 0)
		voltage = spec["inputV"][0] if isinstance(spec["inputV"], list) else spec["inputV"]
		current = (spec.get("mA") or 0) / 1000 if spec.get("drive") == "CC" else watts / voltage
		return watts, [], current
	return 0, [], 0


def _demand(load, spec, voltage, settings):
	"""``demand`` for a load: ``(watts, amps, channel amps)``."""
	if spec is None:
		return 0, 0, []
	watts, channels, current = _load_profile(load, spec, settings)
	cc = spec["kind"] == "fixture" and spec.get("drive") == "CC"
	amps = current if cc else (watts / voltage if voltage > 0 else current)
	if spec["kind"] == "fixture" and not cc:
		if spec.get("maxInputA") is not None and spec.get("maxInputAAtV") == voltage:
			amps = spec["maxInputA"] * (load.get("qty") or 1)
		else:
			amps /= (spec.get("powerFactor") or 1) * (math.sqrt(3) if spec.get("inputPhase") == "3PH" else 1)
	return watts, amps, channels


def derive_loads(design):
	"""``deriveLoads``: one load per assigned run, keyed ``load:{run key}``."""
	loads = []
	for run in design["runs"]:
		assignment = run.get("assignment")
		if not assignment:
			continue
		load = {
			"id": f"load:{run['key']}",
			"catalogId": run["catalogId"],
			"fedFrom": {"ref": assignment["equipmentId"], "port": assignment.get("port")},
			"homeRunLengthFt": run["homeRunLengthFt"],
			"feedMethod": run["feedMethod"],
			"env": run["env"],
		}
		if run.get("lengthFt") is not None:
			load["lengthFt"] = run["lengthFt"]
		else:
			load["qty"] = 1
		if run["feedMethod"] == "multi-feed" and run.get("feeds") is not None:
			load["feeds"] = run["feeds"]
		loads.append(load)
	return loads


# Wires ---------------------------------------------------------------------------------------------


def _environment_matches(wire, env):
	if env == "plenum":
		return wire["plenum"]
	if env == "riser":
		return wire["riser"] or wire["plenum"]
	if env == "wet":
		return wire["wet"]
	if env == "direct-burial":
		return wire["directBurial"]
	if env == "outdoor-exposed":
		return wire["sunlightResistant"] and wire["wet"]
	if env == "raceway":
		return True
	if env == "dry-concealed":
		return wire["category"] not in ("building-wire", "flex-cord")
	return False


def _count(wire, role):
	return sum(c["count"] for c in wire["conductors"] if c["role"] == role)


def _construction_matches(run, wire):
	if run["type"] not in wire["applications"] or not _environment_matches(wire, run["env"]):
		return False
	if wire["ratedV"] < run["voltageV"]:
		return False
	return _count(wire, "power") >= 2


def _groups(wire):
	return [c for c in wire["conductors"] if c["role"] in ("power", "channel")]


def _table(tables, kind, edition):
	return next((t for t in tables if t["kind"] == kind and t["source"]["edition"] == edition), None)


def _row(table, awg):
	return next((row for row in table["rows"] if row["awg"] == awg), None) if table else None


def _resistance(wire, tables, settings):
	values = []
	for conductor in _groups(wire):
		if conductor.get("resistanceOhmPerKft") is not None:
			values.append(conductor["resistanceOhmPerKft"])
		elif wire.get("resistanceOhmPerKft") is not None:
			values.append(wire["resistanceOhmPerKft"])
		else:
			row = (
				_row(_table(tables, "resistance", settings["necEdition"]), conductor["awg"])
				if conductor["material"] == "Cu"
				else None
			)
			values.append(
				(row or {}).get("solid" if conductor.get("stranding") == "solid" else "stranded")
				if row
				else None
			)
	return max(values) if values and all(v is not None for v in values) else None


def _ampacity(wire, tables, settings):
	values = []
	for conductor in _groups(wire):
		if conductor.get("ampacityA") is not None:
			values.append(conductor["ampacityA"])
			continue
		if wire["ampacityBasis"] != "310.16" and wire.get("ampacityA") is not None:
			values.append(wire["ampacityA"])
			continue
		if conductor["material"] != "Cu":
			values.append(None)
			continue
		row = _row(_table(tables, "ampacity", settings["necEdition"]), conductor["awg"])
		if wire["ampacityBasis"] == "310.16":
			temp = min(
				settings["terminationTempC"], wire["tempRatingC"], wire.get("ampacityTempLimitC") or 90
			)
			column = "at90C" if temp >= 90 else "at75C" if temp >= 75 else "at60C"
			values.append(row.get(column) if row else None)
		elif wire["category"] in ("class2-power", "landscape"):
			fixture = _row(_table(tables, "fixture-wire", settings["necEdition"]), conductor["awg"])
			values.append(fixture.get("ampacityA") if fixture else None)
		else:
			values.append(None)
	return min(values) if values and all(v is not None for v in values) else None


def _evaluate(run, wire, tables, settings, target, sets):
	"""``evaluateWire`` for a single-channel Class 2 DC run."""
	groups = _groups(wire)
	awg = min((c["awg"] for c in groups), key=awg_size, default=None)
	reasons = []
	if not _construction_matches(run, wire):
		reasons.append("Construction, voltage rating, application or environment does not match")
	ampacity = _ampacity(wire, tables, settings)
	demand = (max([run["currentA"], *run["channels"], 0]) / sets) * settings["continuousLoadFactor"]
	if ampacity is None:
		reasons.append("Ampacity data unavailable")
	elif ampacity + EPSILON < demand:
		reasons.append("Ampacity")
	resistance = _resistance(wire, tables, settings)
	vd = None if resistance is None else (2 * run["lengthFt"] * (run["currentA"] / sets) * resistance) / 1000
	vd_pct = (vd / run["voltageV"]) * 100 if vd is not None and run["voltageV"] > 0 else None
	if resistance is None:
		reasons.append("Resistance data unavailable")
	elif vd_pct is not None and vd_pct > target + EPSILON:
		reasons.append("Voltage drop")
	return {
		"wireTypeId": wire["id"],
		"awg": awg,
		"eligible": not reasons,
		"reasons": reasons,
		"vdPct": vd_pct,
		"endV": None if vd is None else run["voltageV"] - vd,
	}


def _select(run, wires, tables, settings, target, override):
	"""``selectWire``: the pinned wire, else the lightest eligible one. Returns ``(result, messages)``."""
	sets = (override or {}).get("parallelSets") or 1
	candidates = [
		_evaluate(run, wire, tables, settings, target, sets)
		for wire in wires
		if _construction_matches(run, wire)
	]
	ranked = sorted(
		(c for c in candidates if c["eligible"]),
		key=lambda c: (awg_size(c["awg"]) if c["awg"] else 0, _cost(wires, c["wireTypeId"])),
	)
	by_id = {wire["id"]: wire for wire in wires}
	wire = (
		by_id.get(override["wireTypeId"])
		if override
		else (by_id.get(ranked[0]["wireTypeId"]) if ranked else None)
	)
	chosen = _evaluate(run, wire, tables, settings, target, sets) if wire else None
	messages = []
	ref = run["entityRef"]
	if not chosen:
		messages.append(("NO_VALID_WIRE", ref))
	else:
		for reason in chosen["reasons"]:
			messages.append(("VD_OVER_TARGET" if reason == "Voltage drop" else "NO_VALID_WIRE", ref))
		minimum = run.get("minOperatingV")
		if minimum is not None and chosen["endV"] is not None and chosen["endV"] + EPSILON < minimum:
			messages.append(("TAPE_UNDERVOLTAGE", ref))
	result = {
		"wireTypeId": chosen["wireTypeId"] if chosen else None,
		"vdPct": chosen["vdPct"] if chosen else None,
		"candidates": candidates,
	}
	return result, messages


def _cost(wires, wire_id):
	wire = next((w for w in wires if w["id"] == wire_id), None)
	cost = (wire or {}).get("costPerFt")
	return math.inf if cost is None else cost


# The calculation -----------------------------------------------------------------------------------


def _items_by_id(products):
	return {item["id"]: item for item in products}


def _calculate(design, products, wires, tables, targets, overrides):
	"""The subset of ``calculate``: loading rows, Class 2 DC run results and gating messages."""
	settings = {**SETTING_DEFAULTS, **design["project"]["settings"], **targets}
	items = _items_by_id(products)
	equipment = design["project"]["equipment"]
	sources = design["project"].get("sources") or []
	loads = derive_loads(design)
	aliases = {}
	for entity in [*sources, *equipment]:
		aliases[entity["id"]] = entity["id"]
		if entity.get("tag"):
			aliases[entity["tag"]] = entity["id"]
	for load in loads:
		aliases[load["id"]] = load["id"]
	spec_of = {e["id"]: (items.get(e["catalogId"]) or {}).get("specs") for e in equipment}
	load_specs = {load["id"]: (items.get(load["catalogId"]) or {}).get("specs") for load in loads}
	empty = {"loading": [], "runs": {}, "messages": []}
	# The engine stops when any product in the design is incomplete.
	if any(spec and spec["kind"] == "incomplete" for spec in [*spec_of.values(), *load_specs.values()]):
		return empty
	source_by_id = {s["id"]: s for s in sources}

	def output_voltage(node_id):
		if node_id in source_by_id:
			return source_by_id[node_id].get("voltage") or 0
		spec = spec_of.get(node_id)
		if spec and spec["kind"] in ("psu", "driver"):
			return (spec.get("outputV") if spec["outputType"] == "CV" else spec.get("outputVMax")) or 0
		return 0

	messages = []
	fed = []  # (load, parent id, port, watts, amps, channels)
	for load in loads:
		parent = aliases.get(load["fedFrom"]["ref"])
		if not parent:
			continue
		spec = load_specs[load["id"]]
		voltage = output_voltage(parent)
		watts, amps, channels = _demand(load, spec, voltage, settings)
		fed.append((load, parent, load["fedFrom"].get("port"), watts, amps, channels))
		if spec and spec["kind"] == "tape" and voltage != spec["voltage"]:
			messages.append(("VOLTAGE_MISMATCH", load["id"]))
		if spec and spec["kind"] == "fixture" and spec.get("drive") != "CC":
			low, high = (
				spec["inputV"] if isinstance(spec["inputV"], list) else (spec["inputV"], spec["inputV"])
			)
			if voltage < low or voltage > high:
				messages.append(("VOLTAGE_MISMATCH", load["id"]))

	loading = []
	for item in equipment:
		spec = spec_of.get(item["id"])
		if not spec or spec["kind"] not in ("psu", "driver"):
			continue
		children = [row for row in fed if row[1] == item["id"]]
		if sum(row[3] for row in children) > spec["ratedW"]:
			messages.append(("PSU_OVERLOAD", item["id"]))
		first = spec["outputs"][0] if spec["outputs"] else None
		for output in spec["outputs"]:
			watts = sum(
				row[3] for row in children if row[2] == output["name"] or (not row[2] and output is first)
			)
			loading.append({"entityId": item["id"], "port": output["name"], "wattsW": watts})
			percent = (watts / output["maxW"]) * 100
			if percent > 100:
				messages.append(("PSU_OVERLOAD", item["id"]))
			elif percent > settings["psuDeratePct"]:
				messages.append(("PSU_ABOVE_DERATE", item["id"]))
			if output.get("class2") and watts > 100:
				messages.append(("CLASS2_OVER_100VA", item["id"]))

	runs = {}
	for load, parent, _port, _watts, amps, channels in fed:
		spec = load_specs[load["id"]]
		if spec and spec["kind"] == "tape":
			method = load["feedMethod"]
			limit = (
				spec["maxRunFtSingleFeed"]
				if method == "end"
				else spec["maxRunFtSingleFeed"] * (load.get("feeds") or 1)
				if method == "multi-feed"
				else spec["maxRunFtDoubleFeed"]
			)
			if (load.get("lengthFt") or 0) > limit:
				messages.append(("TAPE_RUN_TOO_LONG", load["id"]))
		parent_spec = spec_of.get(parent)
		voltage = output_voltage(parent)
		low = bool(parent_spec and parent_spec["kind"] in ("psu", "driver")) or voltage <= 60
		# A supply's output is DC unless it says AC; panel circuits are AC.
		dc = bool(parent_spec) and parent_spec.get("outputCurrent", "DC") == "DC"
		if not (low and dc and len(channels) <= 1):
			continue  # Only single-channel Class 2 DC runs are mirrored.
		cc = bool(spec and spec["kind"] == "fixture" and spec.get("drive") == "CC")
		feeds = 1
		if not cc and load["feedMethod"] == "double-end":
			feeds = 2
		elif not cc and load["feedMethod"] == "multi-feed":
			feeds = load.get("feeds") or 1
		edge_id = f"power:{load['id']}"
		for index in range(feeds):
			run_id = f"{edge_id}:feed{index + 1}" if feeds > 1 else edge_id
			run = {
				"type": VERIFIED_RUN_TYPE,
				"entityRef": load["id"],
				"lengthFt": load["homeRunLengthFt"],
				"currentA": amps / feeds,
				"channels": [a / feeds for a in channels],
				"voltageV": voltage,
				"env": load["env"],
				"minOperatingV": spec.get("minOperatingV") if spec and spec["kind"] == "tape" else None,
			}
			result, wire_messages = _select(
				run, wires, tables, settings, settings["vdTargetLowVoltagePct"], overrides.get(run_id)
			)
			result["entityRef"] = load["id"]
			runs[run_id] = result
			messages += wire_messages
	return {"loading": loading, "runs": runs, "messages": messages}


def check(design, products, wires, limits, tables=None):
	"""Mirror of ``checkDesign`` for the gating subset: ``{loading, runs, messages, targets}``."""
	tables = code_tables() if tables is None else tables
	targets = effective_targets(design, limits)
	overrides = dict(design["project"].get("wireOverrides") or {})
	result = _calculate(design, products, wires, tables, targets, overrides)

	# In-wall runs need CL2/CL3-listed cable: the lightest listed wire that passes.
	in_wall = {f"load:{run['key']}" for run in design["runs"] if run.get("envChoice") == "in-wall"}
	listing = {wire["id"]: wire.get("listing") for wire in wires}
	extra, chosen = [], {}
	for run_id, run in result["runs"].items():
		if run["entityRef"] not in in_wall:
			continue
		if run["wireTypeId"] and listing.get(run["wireTypeId"]) in IN_WALL_LISTINGS:
			continue
		if run_id in overrides:
			extra.append(("NO_VALID_WIRE", run["entityRef"]))
			continue
		listed = sorted(
			(
				c
				for c in run["candidates"]
				if c["eligible"] and listing.get(c["wireTypeId"]) in IN_WALL_LISTINGS
			),
			key=lambda c: awg_size(c["awg"]) if c["awg"] else 0,
		)
		if listed:
			chosen[run_id] = {
				"wireTypeId": listed[0]["wireTypeId"],
				"parallelSets": 1,
				"parallelCommonConductors": 1,
			}
		else:
			extra.append(("NO_VALID_WIRE", run["entityRef"]))
	if chosen:
		result = _calculate(design, products, wires, tables, targets, {**overrides, **chosen})

	for line_key in dict.fromkeys(
		run["lineKey"] for run in design["runs"] if (run.get("source") or {}).get("kind") == "third-party"
	):
		extra.append(("DATA_BY_DEALER", f"line:{line_key}"))
	return {**result, "messages": result["messages"] + extra, "targets": targets}


def subset(design, products, wires, limits, gate=None, tables=None):
	"""The ``verifySubset`` shape: rounded loading, Class 2 DC run wires and VD, codes and D4 triggers."""
	result = check(design, products, wires, limits, tables)
	loading = sorted(
		({**row, "wattsW": round_number(row["wattsW"])} for row in result["loading"]),
		key=lambda row: (row["entityId"], row["port"]),
	)
	runs = {
		run_id: {"wireTypeId": run["wireTypeId"], "vdPct": round_number(run["vdPct"])}
		for run_id, run in result["runs"].items()
	}
	verified_refs = {run["entityRef"] for run in result["runs"].values()}
	messages = sorted(
		{
			f"{code}|{ref}"
			for code, ref in result["messages"]
			if code in VERIFY_CODES and (code not in WIRE_CODES or ref in verified_refs)
		}
	)
	return {"loading": loading, "runs": runs, "messages": messages, "review": review_triggers(design, gate)}


def compare(client, server, tolerance=0.01):
	"""Mismatches ``[{code, entityRef, client, server}]`` between two subsets; numbers within ``tolerance``."""
	mismatches = []

	def differ(a, b):
		if isinstance(a, (int, float)) and isinstance(b, (int, float)):
			return abs(a - b) > tolerance
		return a != b

	client_loading = {(row["entityId"], row["port"]): row["wattsW"] for row in client.get("loading") or []}
	server_loading = {(row["entityId"], row["port"]): row["wattsW"] for row in server["loading"]}
	for key in sorted(set(client_loading) | set(server_loading)):
		if differ(client_loading.get(key), server_loading.get(key)):
			mismatches.append(
				{
					"code": "LOADING",
					"entityRef": f"{key[0]}/{key[1]}",
					"client": client_loading.get(key),
					"server": server_loading.get(key),
				}
			)
	client_runs = client.get("runs") or {}
	for run_id in sorted(set(client_runs) | set(server["runs"])):
		mine, theirs = server["runs"].get(run_id) or {}, client_runs.get(run_id) or {}
		for field, code in (("wireTypeId", "WIRE"), ("vdPct", "VOLTAGE_DROP")):
			if differ(theirs.get(field), mine.get(field)):
				mismatches.append(
					{
						"code": code,
						"entityRef": run_id,
						"client": theirs.get(field),
						"server": mine.get(field),
					}
				)
	client_messages, server_messages = set(client.get("messages") or []), set(server["messages"])
	for entry in sorted(client_messages ^ server_messages):
		code, _, ref = entry.partition("|")
		mismatches.append(
			{
				"code": code,
				"entityRef": ref,
				"client": entry in client_messages,
				"server": entry in server_messages,
			}
		)
	if sorted(client.get("review") or []) != sorted(server["review"]):
		mismatches.append(
			{
				"code": "REVIEW",
				"entityRef": "project",
				"client": client.get("review"),
				"server": server["review"],
			}
		)
	return mismatches


def dealer_items(lines):
	"""``dealerItems``: catalog items for third-party lines from the dealer's numbers (D8)."""
	items = []
	for line in lines:
		data = line.get("thirdParty")
		if line.get("kind") != "third-party" or not data:
			continue
		missing = [
			label
			for label, present in (
				("watts", data.get("wattsEach")),
				("input voltage", data.get("inputVoltageV")),
				("voltage class", data.get("voltageClass")),
			)
			if not present
		]
		if data.get("drive") == "CC" and not data.get("mA"):
			missing.append("drive current")
		item_id = f"tp:{line['key']}"
		if missing:
			items.append({"id": item_id, "specs": {"kind": "incomplete", "missingFields": missing}})
			continue
		specs = {
			"kind": "fixture",
			"voltageClass": "line" if data["voltageClass"] == "Line Voltage" else "low",
			"inputV": data["inputVoltageV"],
			"watts": data["wattsEach"],
		}
		if data.get("drive") in ("CV", "CC"):
			specs["drive"] = data["drive"]
		if data.get("mA"):
			specs["mA"] = data["mA"]
		specs["dimming"] = [data["dimming"]] if data.get("dimming") and data["dimming"] != "none" else []
		specs["integralDriver"] = (
			data.get("drive") == "Integral Driver" or data["voltageClass"] == "Line Voltage"
		)
		items.append({"id": item_id, "specs": specs})
	return items
