import frappe
import requests
from illumenate_lighting.illumenate_lighting.api.publication import inspect, request, claim
from illumenate_lighting.illumenate_lighting.api.webflow_brand import get_default_brand, resolve_brand

@frappe.whitelist()
def trigger_sync_v2(docname):
    # 1. Fetch the document and determine active target brands
    doc = frappe.get_doc("ilL-Webflow-Product", docname)
    rows = doc.get("target_brands") or []
    active_brands = [row.brand for row in rows if row.enabled] if rows else [get_default_brand()]
    
    dispatched_jobs = []
    
    for brand in active_brands:
        # Resolve brand config to get the proper webhook URL (fallback to hardcoded if needed)
        try:
            brand_config = resolve_brand(brand, allow_inactive=True)
            # Assuming you append '-v2' to your standard webhook for this testing phase
            base_url = brand_config.get("n8n_webhook_url") or "https://illumenatelighting.app.n8n.cloud/webhook/generate-spec-sheet"
            webhook_url = base_url if base_url.endswith("-v2") else f"{base_url}-v2"
        except frappe.ValidationError:
            webhook_url = "https://illumenatelighting.app.n8n.cloud/webhook/generate-spec-sheet-v2"

        # 2. Inspect the product to get its readiness and current state hash
        inspection = inspect(docname, brand)
        
        if not inspection.get("readiness", {}).get("ready"):
            # Extract the exact reasons for failure
            issues = inspection.get("readiness", {}).get("issues", [])
            issue_msgs = "<br>".join([f"- {i.get('message', 'Unknown issue')} ({i.get('field', 'unknown field')})" for i in issues])
            
            frappe.msgprint(
                msg=f"<b>Skipping {brand} due to readiness issues:</b><br>{issue_msgs}",
                title="Product Not Ready",
                indicator="orange"
            )
            continue
            
        current_hash = inspection.get("current_hash")
        
        # 3. Request a STAGE operation, which queues the ilL-Publish-Job
        request(docname, brand, "STAGE", current_hash)
        
        # 4. Claim pending jobs for this brand
        claimed = claim(brand, limit=5)
        
        # 5. Push the claimed job dictionary directly to the V2 n8n Webhook
        for job_data in claimed.get("jobs", []):
            try:
                # Increased timeout to 300s to match V1's threshold and prevent premature UI crashes
                requests.post(webhook_url, json=job_data, timeout=300)
                dispatched_jobs.append(job_data["job"])
            except Exception as e:
                frappe.log_error(f"Failed to push {job_data['job']} to n8n: {str(e)}", "Webflow V2 Sync")
                frappe.msgprint(f"Network error dispatching {brand} job to n8n.")
                
    return {"status": "success", "jobs": dispatched_jobs}
