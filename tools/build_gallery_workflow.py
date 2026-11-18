"""Build the reviewable n8n gallery workflow; never contacts ERPNext or Webflow.

Modelled on tools/build_publication_workflow.py (docs/WEBFLOW_GALLERY_SYNC.md, section 7).

With no arguments it writes n8n_workflows/webflow_gallery_sync.json, which reads the ERPNext address and
brand from the n8n variables ILL_ERP_BASE_URL and ILL_WEBFLOW_BRAND and calls Webflow with a "Webflow API"
credential. n8n variables are shared by the whole n8n account, so a staging and a production copy cannot
both use them. Pass --erp-base-url and --brand to build a copy with those two values built in instead
(no variables), and --webflow-auth header to call Webflow with a header-token credential like the other
Webflow workflows in this account, for example:

    python3 -B tools/build_gallery_workflow.py --name "[STAGING] ilL Gallery Publication" \
        --erp-base-url https://stagingillumenate.v.frappe.cloud --brand illumenate \
        --webflow-auth header --out n8n_workflows/webflow_gallery_sync.staging.json
"""

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
parser.add_argument("--name", default="ilL Gallery Publication (one brand)", help="workflow name in n8n")
parser.add_argument("--erp-base-url", help="built-in ERPNext address, https://host with no path")
parser.add_argument("--brand", help="built-in ilL-Webflow-Brand code to claim jobs for")
parser.add_argument(
	"--webflow-auth",
	choices=("api", "header"),
	default="api",
	help="api: a 'Webflow API' credential; header: a header-token credential (Authorization header)",
)
parser.add_argument("--out", default="n8n_workflows/webflow_gallery_sync.json", help="file to write")
args = parser.parse_args()
if bool(args.erp_base_url) != bool(args.brand):
	parser.error("--erp-base-url and --brand go together")
if args.erp_base_url:
	args.erp_base_url = args.erp_base_url.rstrip("/")
	if not re.fullmatch(r"https://[A-Za-z0-9.-]+(?::\d+)?", args.erp_base_url):
		parser.error("--erp-base-url must look like https://host (no path)")
	if not re.fullmatch(r"[a-z0-9_]+", args.brand):
		parser.error("--brand must be lowercase letters, digits and underscores")

nodes, connections = [], {}
API = "illumenate_lighting.illumenate_lighting.api.gallery_publication."


def add(name, kind, params, version=1, **extra):
	nodes.append(
		{
			"name": name,
			"id": "gallery-" + name.lower().replace(" ", "-"),
			"type": "n8n-nodes-base." + kind,
			"typeVersion": version,
			"position": [len(nodes) % 6 * 260, len(nodes) // 6 * 240],
			"parameters": params,
			**extra,
		}
	)


def code(name, source):
	add(name, "code", {"mode": "runOnceForEachItem", "jsCode": source}, 2)


def link(source, target, branch=0):
	rows = connections.setdefault(source, {"main": []})["main"]
	while len(rows) <= branch:
		rows.append([])
	rows[branch].append({"node": target, "type": "main", "index": 0})


def condition(name, expression):
	add(
		name,
		"if",
		{
			"conditions": {
				"options": {"caseSensitive": True, "typeValidation": "strict", "version": 2},
				"conditions": [
					{
						"id": name,
						"leftValue": "={{ " + expression + " }}",
						"rightValue": True,
						"operator": {"type": "boolean", "operation": "true", "singleValue": True},
					}
				],
				"combinator": "and",
			},
			"options": {},
		},
		2.2,
	)


def http(name, method, url, body=None, remote=False):
	params = {"method": method, "url": url}
	if remote and args.webflow_auth == "header":
		params.update({"authentication": "genericCredentialType", "genericAuthType": "httpHeaderAuth"})
	else:
		params.update(
			{
				"authentication": "predefinedCredentialType",
				"nodeCredentialType": "webflowApi" if remote else "erpNextApi",
			}
		)
	params["options"] = {"timeout": 45000}
	if body is not None:
		params.update(
			{"sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify(" + body + ") }}"}
		)
	if remote:
		params["options"]["response"] = {
			"response": {"fullResponse": True, "neverError": True, "responseFormat": "json"}
		}
	add(name, "httpRequest", params, 4.2, **({"onError": "continueErrorOutput"} if remote else {}))
	if remote:
		link(name, "Transport Failure", 1)


def erp(method):
	return "={{ $('Configuration').item.json.erp_base_url + '/api/method/" + API + method + "' }}"


def check(source, body):
	"""Code that copies the job from `source` and records a failed Webflow status (no response body)."""
	return (
		"const job = {...$('" + source + "').item.json};\n"
		"const status = Number($json.statusCode), body = $json.body || {};\n"
		"const failed = code => { job.error_code = code; "
		"job.retry_after = $json.headers?.['retry-after'] || null; return {json: job}; };\n" + body
	)


add("Manual Trigger", "manualTrigger", {})
# Every minute: ERP schedules retries 1, 5 and 15 minutes out and n8n claims them on its next poll.
add(
	"Every Minute",
	"scheduleTrigger",
	{"rule": {"interval": [{"field": "minutes", "minutesInterval": 1}]}},
	1.2,
)
if args.erp_base_url:
	# Built in: json.dumps gives a safe JavaScript string literal, and both values were validated above.
	configuration = {"erp_base_url": args.erp_base_url, "brand": args.brand}
	code("Configuration", f"return {{json: {json.dumps(configuration)}}};")
else:
	code(
		"Configuration",
		r"""const base = String($vars.ILL_ERP_BASE_URL || '').replace(/\/$/, '');
const brand = String($vars.ILL_WEBFLOW_BRAND || '');
if (!/^https:\/\/[A-Za-z0-9.-]+(?::\d+)?$/.test(base) || !brand) throw new Error('Set ILL_ERP_BASE_URL and ILL_WEBFLOW_BRAND in n8n variables');
return {json: {erp_base_url: base, brand}};""",
	)
http("Claim Job", "POST", erp("claim"), "{brand: $('Configuration').item.json.brand, limit: 1}")
condition("Job Available", "($json.message?.jobs || []).length > 0")
code(
	"Prepare Claim",
	"""const job = $json.message.jobs[0];
const collection = job.payload.brand.galleries_collection_id;
if (!/^[a-f0-9]{24}$/i.test(collection || '')) throw new Error('Invalid Galleries collection ID');
if (job.payload.schema_version !== 1) throw new Error('Update this workflow for the gallery schema version');
if (job.remote_item_id && !/^[a-f0-9]{24}$/i.test(job.remote_item_id)) throw new Error('Invalid remote item ID');
job.remote_item_id = job.remote_item_id || null;
job.collection_url = 'https://api.webflow.com/v2/collections/' + collection + '/items';
// Webflow cannot filter by erp-sync-id, so without a known ID the collection page is scanned for it.
job.lookup_url = job.remote_item_id ? job.collection_url + '/' + job.remote_item_id : job.collection_url + '?limit=100&offset=0';
return {json: job};""",
)
http("Find Remote Item", "GET", "={{ $json.lookup_url }}", remote=True)
code(
	"Resolve Remote Item",
	"""const job = {...$('Prepare Claim').item.json};
const response = $json, status = Number(response.statusCode), body = response.body || {};
const syncId = job.payload.erp_sync_id, slug = job.payload.slug;
const fail = (code, retryAfter) => ({json: {...job, error_code: code, retry_after: retryAfter || null}});
if (status === 404 && job.remote_item_id) {
  if (job.operation === 'RETIRE') return {json: {...job, absent: true}};
  if (job.operation === 'PUBLISH') return fail('missing-staged-item');
}
if (status < 200 || status >= 300) return fail(String(status), response.headers?.['retry-after']);
let item = null;
if (job.remote_item_id) {
  // Known ID: the item must carry this erp-sync-id, or none yet with the same slug (an imported item,
  // whose erp-sync-id this write backfills).
  const own = body.fieldData?.['erp-sync-id'];
  if (body.id !== job.remote_item_id || !(own === syncId || (!own && body.fieldData?.slug === slug))) return fail('identity-conflict');
  item = body;
} else {
  if (!Array.isArray(body.items)) return fail('response-invalid');
  if (Number(body.pagination?.total ?? body.items.length) > body.items.length) return fail('lookup-incomplete');
  // Match by erp-sync-id first (finds an item created before a lost acknowledgement), then by exact
  // slug; a slug match must carry this erp-sync-id. Any second candidate stops for reconciliation.
  const bySync = body.items.filter(row => row.fieldData?.['erp-sync-id'] === syncId);
  const bySlug = body.items.filter(row => row.fieldData?.slug === slug);
  if (bySync.length > 1 || bySlug.some(row => !bySync.includes(row))) return fail('identity-conflict');
  item = bySync[0] || null;
}
if (item && !/^[a-f0-9]{24}$/i.test(item.id || '')) return fail('response-invalid');
if (!item && job.operation === 'PUBLISH') return fail('missing-staged-item');
return {json: {...job, remote_item_id: item?.id || null, absent: !item}};""",
)
condition("Lookup Succeeded", "!$json.error_code")
condition("Retiring", "$json.operation === 'RETIRE'")
condition("Already Absent", "$json.absent === true")
http(
	"Unpublish Remote Item",
	"DELETE",
	"={{ $json.collection_url + '/' + $json.remote_item_id + '/live' }}",
	remote=True,
)
code(
	"Check Unpublish",
	check(
		"Resolve Remote Item",
		"if ((status < 200 || status >= 300) && status !== 404) return failed(String(status));\n"
		"return {json: job};",
	),
)
condition("Unpublish Succeeded", "!$json.error_code")
http(
	"Archive Remote Item",
	"PATCH",
	"={{ $json.collection_url + '/' + $json.remote_item_id }}",
	"{isArchived: true, isDraft: true}",
	remote=True,
)
code(
	"Check Archive",
	check(
		"Resolve Remote Item",
		"if (status < 200 || status >= 300) return failed(String(status));\n"
		"if (body.isArchived !== true) return failed('archive-unverified');\nreturn {json: job};",
	),
)
projection = (ROOT / "n8n_workflows/lib/gallery_projection.js").read_text(encoding="utf8")
code(
	"Prepare Write",
	projection
	+ """
const job = {...$json};
try {
  // STAGE saves a draft; PUBLISH marks the staged item ready, then publishes it (as for products).
  job.write_body = projectWebflowGallery(job.payload, {isDraft: job.operation !== 'PUBLISH'});
  job.write_method = job.remote_item_id ? 'PATCH' : 'POST';
  job.write_url = job.collection_url + (job.remote_item_id ? '/' + job.remote_item_id : '');
} catch (error) { job.error_code = 'projection-invalid'; }
return {json: job};""",
)
condition("Projection Valid", "!$json.error_code")
http(
	"Write Staged Item",
	"={{ $json.write_method }}",
	"={{ $json.write_url }}",
	"$json.write_body",
	remote=True,
)
code(
	"Check Write",
	check(
		"Prepare Write",
		"if (status < 200 || status >= 300) return failed(String(status));\n"
		"if (!/^[a-f0-9]{24}$/i.test(body.id || '') || (job.remote_item_id && body.id !== job.remote_item_id)) "
		"return failed('response-invalid');\n"
		"job.remote_item_id = body.id;\ndelete job.write_body;\nreturn {json: job};",
	),
)
condition("Write Succeeded", "!$json.error_code")
condition("Publishing", "$json.operation === 'PUBLISH'")
http(
	"Publish Remote Item",
	"POST",
	"={{ $json.collection_url + '/publish' }}",
	"{itemIds: [$json.remote_item_id]}",
	remote=True,
)
code(
	"Check Publish",
	check(
		"Check Write",
		"if (status < 200 || status >= 300) return failed(String(status));\n"
		"if (body.errors?.length || !(body.publishedItemIds || []).includes(job.remote_item_id)) "
		"return failed('publication-unverified');\nreturn {json: job};",
	),
)
condition("Remote Action Succeeded", "!$json.error_code")
code("Transport Failure", "return {json: {...$('Prepare Claim').item.json, error_code: 'transport'}};")
# Only these fields reach ERP: never a Webflow response body or a credential.
ack = (
	"{job: $json.job, token: $json.token, revision_hash: $json.revision_hash, "
	"payload_hash: $json.payload_hash, remote_item_id: $json.remote_item_id || null, outcome: 'success'}"
)
http("Record Success", "POST", erp("acknowledge"), ack)
http(
	"Record Failure",
	"POST",
	erp("acknowledge"),
	ack.replace(
		"outcome: 'success'",
		"outcome: 'error', error_code: $json.error_code, retry_after: $json.retry_after || null",
	),
)
condition("Continue Batch", "$runIndex < 999")
add(
	"Setup Instructions",
	"stickyNote",
	{
		"content": "Gallery publication (one brand)\n\n"
		+ (
			f"Built for brand {args.brand} at {args.erp_base_url}: both values are built in, so no n8n "
			"variables are used and a staging and a production copy can sit side by side. Bind the ERP "
			"credential (ilL Integration System User) and the Webflow credential for that brand's site "
			"to every HTTP node. "
			if args.erp_base_url
			else "Set ILL_ERP_BASE_URL and ILL_WEBFLOW_BRAND. Bind ERP credentials for an ilL Integration "
			"System User and Webflow credentials for that exact brand to every HTTP node. Deploy one "
			"workflow per brand. "
		)
		+ "No secrets in variables or exports. The Galleries collection needs a plain-text "
		"erp-sync-id field first.\n\n"
		"Runs every minute (and manually): ERP schedules retries 1, 5 and 15 minutes out and this worker "
		"claims them on its next poll. It claims one job at a time and drains at most 1000 jobs per run. "
		"Remote items are matched by erp-sync-id, then by exact slug with erp-sync-id verified; two "
		"candidates stop as identity-conflict, and a collection larger than one page (100) stops as "
		"lookup-incomplete. Failed calls record a safe error code only. Import inactive and test on "
		"staging2 before activation.\n\n"
		"STAGE saves a draft; PUBLISH publishes the staged item; RETIRE unpublishes then archives and "
		"never deletes. No site-wide publish. Primary locale only.",
		"width": 640,
		"height": 520,
	},
)

for source, target, branch in [
	("Manual Trigger", "Configuration", 0),
	("Every Minute", "Configuration", 0),
	("Configuration", "Claim Job", 0),
	("Claim Job", "Job Available", 0),
	("Job Available", "Prepare Claim", 0),
	("Prepare Claim", "Find Remote Item", 0),
	("Find Remote Item", "Resolve Remote Item", 0),
	("Resolve Remote Item", "Lookup Succeeded", 0),
	("Lookup Succeeded", "Retiring", 0),
	("Lookup Succeeded", "Record Failure", 1),
	("Retiring", "Already Absent", 0),
	("Retiring", "Prepare Write", 1),
	("Already Absent", "Record Success", 0),
	("Already Absent", "Unpublish Remote Item", 1),
	("Unpublish Remote Item", "Check Unpublish", 0),
	("Check Unpublish", "Unpublish Succeeded", 0),
	("Unpublish Succeeded", "Archive Remote Item", 0),
	("Unpublish Succeeded", "Record Failure", 1),
	("Archive Remote Item", "Check Archive", 0),
	("Check Archive", "Remote Action Succeeded", 0),
	("Prepare Write", "Projection Valid", 0),
	("Projection Valid", "Write Staged Item", 0),
	("Projection Valid", "Record Failure", 1),
	("Write Staged Item", "Check Write", 0),
	("Check Write", "Write Succeeded", 0),
	("Write Succeeded", "Publishing", 0),
	("Write Succeeded", "Record Failure", 1),
	("Publishing", "Publish Remote Item", 0),
	("Publishing", "Record Success", 1),
	("Publish Remote Item", "Check Publish", 0),
	("Check Publish", "Remote Action Succeeded", 0),
	("Remote Action Succeeded", "Record Success", 0),
	("Remote Action Succeeded", "Record Failure", 1),
	("Transport Failure", "Record Failure", 0),
	("Record Success", "Continue Batch", 0),
	("Record Failure", "Continue Batch", 0),
	("Continue Batch", "Claim Job", 0),
]:
	link(source, target, branch)

workflow = {
	"name": args.name,
	"nodes": nodes,
	"connections": connections,
	"active": False,
	"settings": {"executionOrder": "v1", "saveDataSuccessExecution": "none", "saveDataErrorExecution": "all"},
	"pinData": {},
}
(ROOT / args.out).write_text(json.dumps(workflow, indent=2) + "\n", encoding="utf8")
print(f"Built {len(nodes)} nodes into {args.out}; workflow remains inactive")
