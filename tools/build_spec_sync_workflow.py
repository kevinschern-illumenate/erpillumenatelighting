"""Build an environment's spec generator & Webflow sync workflow from the staging export.

Never contacts n8n, ERPNext or Webflow. The source is n8n_workflows/spec_sync_staging.json (the
live staging workflow, exported); the values per environment are in
n8n_workflows/spec_sync_environments.json. See n8n_workflows/SPEC_SYNC.md and
docs/superpowers/plans/2026-11-23-spec-sync-production-linear-fixtures.md.

	python tools/build_spec_sync_workflow.py --env production

What changes, and nothing else:
  1. The staging ERPNext origin becomes the environment's, in every string (Code nodes too).
  2. Each webhook node gets the environment's path and a new webhookId derived from it.
  3. Credentials are remapped by '<type>:<staging name>'; a null target leaves the node unbound.
  4. Without staging guards, the Staging Guard nodes are removed and their inputs connected to
     what they led to.
  5. A brand the environment does not sync loses its nodes; the brand switches send it to a
     "Brand not enabled" answer (409). Expressions that read one of its nodes, always as the
     fallback of an "(ilL) X or (206) X" choice, read the "(ilL) X" twin instead (n8n's $if
     evaluates both branches, so a missing node would fail every run).
  6. Inactive, the environment's name, and no saved data for successful or manual runs (n8n
     stores webhook headers, the shared secret included, in execution data).
"""

import argparse
import copy
import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "n8n_workflows/spec_sync_staging.json"
ENVIRONMENTS = "n8n_workflows/spec_sync_environments.json"
# The node-name prefix of each brand's own nodes, and the brand whose twin nodes replace them.
BRAND_PREFIX = {"lighting_206": "(206)"}
TWIN_PREFIX = "(ilL)"
GUARD_PREFIXES = ("Staging Guard", "(206) Staging Guard")
REFUSAL = "Brand not enabled"


def replace_strings(value, old, new):
	if isinstance(value, str):
		return value.replace(old, new)
	if isinstance(value, list):
		return [replace_strings(item, old, new) for item in value]
	if isinstance(value, dict):
		return {key: replace_strings(item, old, new) for key, item in value.items()}
	return value


def remap_credentials(node, mapping):
	credentials = node.get("credentials")
	if not credentials:
		return
	for kind, current in list(credentials.items()):
		key = f"{kind}:{current['name']}"
		if key not in mapping:
			continue
		if mapping[key] is None:
			del credentials[kind]
		else:
			credentials[kind] = dict(mapping[key])
	if not credentials:
		del node["credentials"]


def repoint(value, old, new):
	"""Point n8n node references ``$('old')`` / ``$("old")`` at ``new``."""
	for quote in ("'", '"'):
		value = replace_strings(value, f"$({quote}{old}{quote})", f"$({quote}{new}{quote})")
	return value


def outputs(connections, name):
	return connections.get(name, {}).get("main", [])


def bypass(connections, name):
	"""Connect every input of ``name`` to the targets of its first output, then drop ``name``."""
	first = (outputs(connections, name) or [[]])[0] or []
	for value in connections.values():
		for index, outs in enumerate(value.get("main", [])):
			if outs and any(out["node"] == name for out in outs):
				kept = [out for out in outs if out["node"] != name]
				value["main"][index] = kept + [dict(out) for out in first if out not in kept]
	connections.pop(name, None)


def switch_output(node, brand):
	"""The output index of a brand switch whose rule matches ``brand``, or None."""
	for index, rule in enumerate(node["parameters"].get("rules", {}).get("values", [])):
		for condition in rule.get("conditions", {}).get("conditions", []):
			if condition.get("rightValue") == brand:
				return index
	return None


def build(source, env_name, env, staging):
	flow = copy.deepcopy(source)
	flow["nodes"] = replace_strings(flow["nodes"], staging["erp_origin"], env["erp_origin"])
	nodes = {node["name"]: node for node in flow["nodes"]}
	connections = flow["connections"]

	for name, path in env["webhooks"].items():
		node = nodes[name]
		node["parameters"]["path"] = path
		node["webhookId"] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{env_name}/{path}"))
	for node in flow["nodes"]:
		remap_credentials(node, env.get("credentials", {}))

	if not env["staging_guards"]:
		for name in [name for name in nodes if name.startswith(GUARD_PREFIXES)]:
			bypass(connections, name)
			del nodes[name]

	refused = [brand for brand in staging["brands"] if brand not in env["brands"]]
	if refused:
		for node in list(nodes.values()):
			if not node["type"].endswith(".switch"):
				continue
			for brand in refused:
				index = switch_output(node, brand)
				if index is not None:
					outs = connections.setdefault(node["name"], {"main": []})["main"]
					outs.extend([] for _ in range(index + 1 - len(outs)))
					outs[index] = [{"node": REFUSAL, "type": "main", "index": 0}]
		for brand in refused:
			prefix = BRAND_PREFIX[brand]
			for name in [name for name in nodes if name.startswith(prefix)]:
				connections.pop(name, None)
				del nodes[name]
				twin = TWIN_PREFIX + name[len(prefix) :]
				if twin not in nodes:
					raise SystemExit(f"{name} is removed and has no {twin} twin for expressions to read")
				for node in nodes.values():
					node["parameters"] = repoint(node["parameters"], name, twin)
		nodes[REFUSAL] = {
			"parameters": {
				"respondWith": "json",
				"responseBody": json.dumps(
					{"success": False, "error": "brand not enabled in this environment"}
				),
				"options": {"responseCode": 409},
			},
			"type": "n8n-nodes-base.respondToWebhook",
			"typeVersion": 1.1,
			"position": [2400, 1200],
			"id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"{env_name}/{REFUSAL}")),
			"name": REFUSAL,
		}

	# Nothing may point at a removed node.
	for source_name, value in connections.items():
		for outs in value.get("main", []):
			for out in outs or []:
				if out["node"] not in nodes:
					raise SystemExit(f"{source_name} still connects to removed node {out['node']}")

	flow["nodes"] = sorted(nodes.values(), key=lambda node: node["name"])
	flow["connections"] = {name: connections[name] for name in sorted(connections)}
	flow["name"] = env["name"]
	flow["active"] = False
	flow["settings"] = {
		**flow.get("settings", {}),
		"saveDataSuccessExecution": "none",
		"saveManualExecutions": False,
	}
	return flow


def main():
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument(
		"--env", required=True, help="An entry of spec_sync_environments.json, e.g. production"
	)
	parser.add_argument("--source", default=SOURCE)
	parser.add_argument("--out", help="Default: n8n_workflows/spec_sync_<env>.json")
	args = parser.parse_args()
	environments = json.loads((ROOT / ENVIRONMENTS).read_text())
	if args.env == "staging" or args.env not in environments:
		parser.error(
			"--env must be an environment other than staging: "
			+ ", ".join(name for name in environments if not name.startswith("_") and name != "staging")
		)
	source = json.loads((ROOT / args.source).read_text())
	flow = build(source, args.env, environments[args.env], environments["staging"])
	out = ROOT / (args.out or f"n8n_workflows/spec_sync_{args.env}.json")
	out.write_text(json.dumps(flow, indent=2, ensure_ascii=False) + "\n")
	print(f"wrote {out.relative_to(ROOT)} ({len(flow['nodes'])} nodes)")


if __name__ == "__main__":
	main()
