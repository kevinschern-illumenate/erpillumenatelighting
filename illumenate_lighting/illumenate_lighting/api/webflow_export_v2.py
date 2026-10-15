import frappe
import requests
from illumenate_lighting.illumenate_lighting.api.publication import inspect, request, claim
from illumenate_lighting.illumenate_lighting.api.webflow_brand import get_default_brand

@frappe.whitelist()
def trigger_sync_v2(docname):
    # 1. Fetch the document and determine active target brands
    doc = frappe.get_doc("ilL-Webflow-Product", docname)
    rows = doc.get("target_brands") or []
    active_brands = [row.brand for row in rows if row.enabled] if rows else [get_default_brand()]
    
    dispatched_jobs = []
    
    for brand in active_brands:
        # 2. Inspect the product to get its readiness and current state hash
        inspection = inspect(docname, brand)
        
        if not inspection.get("readiness", {}).get("ready"):
            frappe.msgprint(f"Skipping {brand}: Product has readiness issues.")
            continue
            
        current_hash = inspection.get("current_hash")
        
        # 3. Request a STAGE operation, which queues the ilL-Publish-Job
        request(docname, brand, "STAGE", current_hash)
        
        # 4. Claim pending jobs for this brand. 
        # This locks the job, generates the secure lease token, and builds the payload.
        claimed = claim(brand, limit=5)
        
        # 5. Push the claimed job dictionary directly to the V2 n8n Webhook
        for job_data in claimed.get("jobs", []):
            webhook_url = "https://illumenatelighting.app.n8n.cloud/webhook/generate-spec-sheet-v2"
            try:
                # job_data contains: job, token, revision_hash, payload_hash, and payload
                requests.post(webhook_url, json=job_data, timeout=10)
                dispatched_jobs.append(job_data["job"])
            except Exception as e:
                frappe.log_error(f"Failed to push {job_data['job']} to n8n: {str(e)}", "Webflow V2 Sync")
                
    return {"status": "success", "jobs": dispatched_jobs}