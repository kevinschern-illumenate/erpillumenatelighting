"""Build the reviewable n8n gallery workflow; never contacts ERPNext or Webflow.

Modelled on tools/build_publication_workflow.py (docs/WEBFLOW_GALLERY_SYNC.md, section 7).
"""

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# By default the workflow reads the ERP address and brand from n8n variables. n8n variables are an
# account-wide paid feature, so a deployment can build them in instead:
#   python tools/build_gallery_workflow.py --erp-base-url https://erp.example.com --brand illumenate \
#       --webhook-path ill-gallery-sync --name "ilL Gallery Publication (production)" \
#       --out n8n_workflows/webflow_gallery_sync_production.json
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--erp-base-url", help="Build this https ERP address into the Configuration node")
parser.add_argument("--brand", help="Build this brand code into the Configuration node")
parser.add_argument("--webhook-path", default="ill-gallery-sync", help="Path of the Gallery Webhook node")
parser.add_argument("--name", default="ilL Gallery Publication (one brand)")
parser.add_argument("--out", default="n8n_workflows/webflow_gallery_sync.json")
args = parser.parse_args()
if bool(args.erp_base_url) != bool(args.brand):
	parser.error("--erp-base-url and --brand go together")
if args.erp_base_url and not re.fullmatch(r"https://[A-Za-z0-9.-]+(?::\d+)?", args.erp_base_url):
	parser.error("--erp-base-url must be an https origin without a path")
if args.brand and not re.fullmatch(r"[A-Za-z0-9_-]+", args.brand):
	parser.error("--brand may contain letters, digits, - and _ only")
if not re.fullmatch(r"[A-Za-z0-9_-]+", args.webhook_path):
	parser.error("--webhook-path may contain letters, digits, - and _ only")

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
	params = {
		"method": method,
		"url": url,
		"authentication": "predefinedCredentialType",
		"nodeCredentialType": "webflowApi" if remote else "erpNextApi",
		"options": {"timeout": 45000},
	}
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
# ERP is the trigger, not a timer: it POSTs {"brand": ...} here when a job is requested, retried or a
# retry falls due, and the workflow then claims the job. No polling, so no idle executions.
add(
	"Gallery Webhook",
	"webhook",
	{
		"httpMethod": "POST",
		"path": args.webhook_path,
		"authentication": "headerAuth",
		"responseMode": "onReceived",
		"options": {},
	},
	2,
	webhookId="3f1d6c1e-6f0b-4b52-9a6a-2b6d2f8f7a11",
)
if args.erp_base_url:
	code(
		"Configuration",
		"// Built in because n8n variables are not available on this plan.\n"
		"return {json: {erp_base_url: " + json.dumps(args.erp_base_url) + ", brand: " + json.dumps(args.brand) + "}};",
	)
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
// Without a known ID the item is looked up by its slug (Webflow filters by slug, not by erp-sync-id), so the
// size of the collection does not matter. ERP locks a slug once staged, and galleries are not edited in Webflow.
job.lookup_url = job.remote_item_id ? job.collection_url + '/' + job.remote_item_id : job.collection_url + '?limit=100&slug=' + encodeURIComponent(job.payload.slug);
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
  // If Webflow ignored the slug filter and the collection is bigger than one page, absence cannot be proven.
  if (Number(body.pagination?.total ?? body.items.length) > body.items.length && !(body.items.length > 0 && body.items.every(row => row.fieldData?.slug === slug))) return fail('lookup-incomplete');
  // Match by erp-sync-id (finds an item created before a lost acknowledgement) and by exact slug; a slug
  // match must carry this erp-sync-id. Any second candidate stops for reconciliation.
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
		"Set ILL_ERP_BASE_URL and ILL_WEBFLOW_BRAND. Bind ERP credentials for an ilL Integration System "
		"User and Webflow credentials for that exact brand to every HTTP node. Deploy one workflow per "
		"brand. No secrets in variables or exports. The Galleries collection needs a plain-text "
		"erp-sync-id field first.\n\n"
		"Started by ERP, not a timer: ERP calls the Gallery Webhook when a job is requested or a retry "
		"falls due (retries are 1, 5 and 15 minutes out). Bind a Header Auth credential to the webhook "
		"and set n8n_gallery_webhook_url (and the secret header) in the ERP site config. It claims one job at a time and drains at most 1000 jobs per run. "
		"Remote items are looked up by exact slug, so the size of the collection does not matter; a match "
		"must carry this erp-sync-id (or be a known imported item), and two candidates stop as "
		"identity-conflict. If Webflow ignored the slug filter on a collection over 100 items the job stops "
		"as lookup-incomplete. Failed calls record a safe error code only. Import inactive and test on "
		"staging2 before activation.\n\n"
		"STAGE saves a draft; PUBLISH publishes the staged item; RETIRE unpublishes then archives and "
		"never deletes. No site-wide publish. Primary locale only.",
		"width": 640,
		"height": 520,
	},
)

for source, target, branch in [
	("Manual Trigger", "Configuration", 0),
	("Gallery Webhook", "Configuration", 0),
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
(ROOT / args.out).write_text(
	json.dumps(workflow, indent=2) + "\n", encoding="utf8"
)
print(f"Built {len(nodes)} nodes; workflow remains inactive")
