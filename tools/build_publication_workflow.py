"""Build the reviewable n8n workflow; never contacts ERPNext or Webflow."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
nodes, connections = [], {}
API = "illumenate_lighting.illumenate_lighting.api.publication."


def add(name, kind, params, version=1, **extra):
	nodes.append(
		{
			"name": name,
			"id": name.lower().replace(" ", "-"),
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


add("Manual Trigger", "manualTrigger", {})
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
const collection = job.payload.brand.collections.Products;
if (!/^[a-f0-9]{24}$/i.test(collection)) throw new Error('Invalid collection ID');
if (job.payload.projection_version !== 1) throw new Error('Update this workflow for the projection version');
job.collection_url = 'https://api.webflow.com/v2/collections/' + collection + '/items';
job.lookup_url = job.remote_item_id ? job.collection_url + '/' + job.remote_item_id : job.collection_url + '?slug=' + encodeURIComponent(job.payload.product_slug) + '&limit=100';
return {json: job};""",
)
http("Find Remote Item", "GET", "={{ $json.lookup_url }}", remote=True)
code(
	"Resolve Remote Item",
	"""const job = {...$('Prepare Claim').item.json};
const response = $json, status = Number(response.statusCode);
if (status === 404 && job.operation === 'RETIRE') return {json: {...job, absent: true}};
if (status < 200 || status >= 300) return {json: {...job, error_code: String(status), retry_after: response.headers?.['retry-after']}};
const body = response.body || {};
const items = Array.isArray(body.items) ? body.items : [body];
if (Number(body.pagination?.total || items.length) > 1 || items.length > 1) return {json: {...job, error_code: 'identity-conflict'}};
const item = items[0];
if (item && (item.fieldData?.['erp-sync-id'] !== job.payload.product_slug || (job.remote_item_id && item.id !== job.remote_item_id))) return {json: {...job, error_code: 'identity-conflict'}};
if (!item && job.operation === 'PUBLISH') return {json: {...job, error_code: 'missing-staged-item'}};
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
	"""const job = {...$('Resolve Remote Item').item.json};
const status = Number($json.statusCode);
if ((status < 200 || status >= 300) && status !== 404) job.error_code = String(status);
return {json: job};""",
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
	"""const job = {...$('Resolve Remote Item').item.json};
const status = Number($json.statusCode);
if (status < 200 || status >= 300 || !$json.body?.isArchived) job.error_code = String(status || 'archive-unverified');
return {json: job};""",
)
projection = (ROOT / "n8n_workflows/lib/product_projection.js").read_text(encoding="utf8")
code(
	"Prepare Write",
	projection
	+ """
const job = {...$json};
try {
  const product = {...job.payload.product, webflow_item_id: job.remote_item_id};
  job.write_body = projectWebflowProduct(product, job.payload.brand).json.webflowData;
  if (job.operation === 'PUBLISH') job.write_body.isDraft = false;
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
	"""const job = {...$('Prepare Write').item.json};
const status = Number($json.statusCode), body = $json.body || {};
if (status < 200 || status >= 300 || !/^[a-f0-9]{24}$/i.test(body.id || '')) {
  job.error_code = status >= 200 && status < 300 ? 'response-invalid' : String(status);
  job.retry_after = $json.headers?.['retry-after'];
} else { job.remote_item_id = body.id; }
return {json: job};""",
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
	"""const job = {...$('Check Write').item.json};
const status = Number($json.statusCode), body = $json.body || {};
if (status < 200 || status >= 300) job.error_code = String(status);
else if (body.errors?.length || !(body.publishedItemIds || []).includes(job.remote_item_id)) job.error_code = 'publication-unverified';
return {json: job};""",
)
condition("Remote Action Succeeded", "!$json.error_code")
code("Transport Failure", "return {json: {...$('Prepare Claim').item.json, error_code: 'transport'}};")
ack = "{job: $json.job, token: $json.token, revision_hash: $json.revision_hash, payload_hash: $json.payload_hash, remote_item_id: $json.remote_item_id || null, outcome: 'success'}"
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
		"content": "Revision-aware product publication\n\nSet ILL_ERP_BASE_URL and ILL_WEBFLOW_BRAND. Bind ERP credentials for an ilL Integration System User and Webflow credentials for that exact brand to every HTTP node. Deploy one workflow per brand. No secrets in variables or exports.\n\nStaff inspect and approve STAGE, then explicitly PUBLISH from ERP. The worker claims one immutable job at a time, recovers IDs by exact slug plus erp-sync-id, and drains at most 1000 jobs per run. Failed calls record a safe error code; ERP determines retry time. Schedule another execution for retries. Import disabled and test staging before activation.\n\nRETIRE unpublishes then archives; it never deletes a staged CMS record. No site-wide publish is used. Single primary locale only; multiple locale matches stop for reconciliation.",
		"width": 640,
		"height": 500,
	},
)

for source, target, branch in [
	("Manual Trigger", "Configuration", 0),
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
	"name": "ilL Product Publication v2 (one brand)",
	"nodes": nodes,
	"connections": connections,
	"active": False,
	"settings": {"executionOrder": "v1", "saveDataSuccessExecution": "none", "saveDataErrorExecution": "all"},
	"pinData": {},
}
(ROOT / "n8n_workflows/webflow_product_sync.json").write_text(
	json.dumps(workflow, indent=2) + "\n", encoding="utf8"
)
print(f"Built {len(nodes)} nodes; workflow remains inactive")
