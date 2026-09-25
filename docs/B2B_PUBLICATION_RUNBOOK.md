# Product publication

Products are authored as editable drafts. `Readiness and Publication` on the product form inspects the saved record and linked dependencies for a selected brand. Correct the reported record/field issues. `Approve and Stage` creates an immutable job. Once that revision is staged, `Publish Live` creates a separate job. Deactivate a product before requesting retirement. Retirement unpublishes and archives the CMS item; it does not delete the staged record.

The publication record stores current, approved, staged and live hashes separately. A content/dependency change requires fresh approval. A successful stage does not prove that the content is live. Existing remote IDs can be adopted from the legacy brand mapping, but old staged/live hashes remain unknown. Legacy product callbacks without a job, lease token and hashes now fail with an upgrade instruction.

## Deployment

1. Back up existing workflow exports, brand mappings and observed staged/live CMS content. Disable the old product-sync trigger during cutover.
2. Migrate the app. Assign named System Users the `ilL Catalog Publisher` and `ilL Integration` roles as appropriate. Do not assign integration credentials to a dealer account.
3. Configure each `ilL-Webflow-Brand`, including its **Products** collection, HTTPS ERP base URL and sync-enabled flag. Stage referenced categories for that brand first. Existing optional CMS display/filter fields remain disabled in the projection until their schema is verified.
4. Import `n8n_workflows/webflow_product_sync.json`, initially inactive. Set n8n variables `ILL_ERP_BASE_URL` and `ILL_WEBFLOW_BRAND`. Bind an ERP credential for an integration System User and the matching brand's Webflow credential to every respective HTTP node. Deploy one workflow per brand; credential names in an ERP record do not dynamically bind n8n credentials.
5. Approve one staging product and execute manually. Verify CMS fields, generated literature URLs and embedded configurator bindings. Then test a second brand, local edit during a claim, failed create/update, timeout after remote create, 429, retry and retirement. Configure the workflow's schedule only after these checks.

The worker drains at most 1,000 jobs per execution, claiming one at a time. Claims last five minutes. Transient errors use 30-second exponential backoff, capped at one hour and eight attempts. A later execution picks up due retries. Permanent errors remain visible for staff correction and explicit retry. HTTP response bodies and secrets are not persisted in ERP error fields. Restrict n8n execution-history access; lease tokens appear in its operational payloads.

Remote identity recovery uses the exact slug and verifies `erp-sync-id`; duplicate/localized matches stop for reconciliation. If a remote item was manually renamed before its first acknowledgment, reconcile its identity before retrying. This workflow operates on the primary locale. Multi-locale publication requires an explicit extension and acceptance tests.

`publication.reconcile_local` compares current ERP content with stored approvals in bounded pages; pass its `next_cursor` as `after`. It does **not** claim to read or verify remote content. A stale callback retains the last recorded live hash and marks the discrepancy for reconciliation. Inspect the remote item before deciding what to republish.

## Local evidence

For remote inspection, run `node tools/reconcile_webflow.cjs` with `ILL_ERP_BASE_URL`, `ILL_WEBFLOW_BRAND`, `ILL_ERP_API_KEY`, `ILL_ERP_API_SECRET` and `ILL_WEBFLOW_TOKEN` in a private process environment. Use an HTTPS ERP origin and the matching brand token. The ERP account needs the Integration capability. Redirect output to a restricted report file; no secrets or remote response bodies are logged. This command performs GETs only and never publishes, changes ERP state or rewrites remote content.

The audit pages through immutable completed publication jobs and compares the expected projection against the actual staged item and [live item](https://developers.webflow.com/data/reference/cms/collection-items/live-items/get-item-live) separately. A newer staged revision does not overwrite the last recorded live expectation. It compares downloadable asset bytes by SHA-256 rather than assuming two URLs identify the same file. Missing immutable job evidence, inaccessible assets or unsupported asset origins remain `UNVERIFIED`; changed fields, unexpected/missing live items and incomplete retirement produce `DRIFT`. Exit status is 0 for verified matches, 2 for drift/unverified results, and 1 for transport/configuration failure. Correct drift through an inspected new approval/job, not by editing receipt hashes. Test the audit with actual CMS field types and the site's asset hosts before relying on it operationally.

Retain the report with release evidence and schedule read-only runs in the integration environment. Reconciliation was tested locally with simulated responses; no live remote audit has been performed in this workspace.

`node tests/portal_unit/publication_workflow.test.cjs` executes the checked-in code nodes and branches with a simulated HTTP boundary: 123 products, recovery after remote create, rate limiting, identity conflict, stage/publish separation, retirement and per-brand configurator stripping. `test_publication.py` exercises staff capability and callback revision rules. These are not installed n8n, Frappe transaction or live Webflow tests.

Regenerate the workflow with `python -B tools/build_publication_workflow.py` after editing its builder or `n8n_workflows/lib/product_projection.js`. Increment the projection contract version in both ERP and worker when changing mapping semantics for already queued jobs.

API behavior checked against Webflow's [item listing](https://developers.webflow.com/data/reference/cms/collection-items/staged-items/list-items), [publication](https://developers.webflow.com/data/reference/cms/collection-items/staged-items/publish-item), and [publishing lifecycle](https://developers.webflow.com/data/docs/working-with-the-cms/publishing) documentation on September 25, 2026.
