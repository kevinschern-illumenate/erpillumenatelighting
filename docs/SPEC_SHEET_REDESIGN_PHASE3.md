# Spec Sheet Redesign: Phase 3 (generate a spec sheet from the template)

## ERPNext

- **Generate Spec** button on the six templates (`public/js/template_spec_sheet.js`). The template
  must be saved first. An opaque dialog with no close button stays open while the job runs and polls
  its status; the job keeps running if the page is closed. Phase 5 changes the label to "Generate Spec
  & Sync to Webflow" when a sync follows.
- `spec_sheet_job.generate_spec_sheet(template_doctype, template_id, brand=None)`: permission as for
  linking (D28), checks the n8n site config, queues a background job (queue `long`) and returns a job
  id. `spec_sheet_job_status(job_id)`: Queued, Running, Done or Failed, with a message.
- The job posts `{template_doctype, template_id, brand}` to `n8n_spec_webhook_url` with the shared
  secret header, waits for `{success, file_url}` (5 minutes), then `register_spec_sheet` checks the
  template's Spec Sheet points at that file (and sets it if n8n did not). Phase 4 adds the stable URL
  and removes older files. Nothing here calls Webflow.
- n8n keeps uploading through `upload_spec_pdf` and then setting the template's `spec_sheet` (owner:
  that is what fills the File's attached-to fields).

### Data for templates without a Webflow Product

`get_spec_sheet_data` now always has a `legacy` record. With a linked product it is the real export
record. Without one it is built by the same export code (`webflow_export_v2.export_template_record`)
on a temporary, unsaved product that points at the template and has run the product calculations
(spec rows, attribute links, compatible power supplies, certification badges, configurator steps,
hero image). The export's per-product code was moved into `_finish_products` so both paths share it.

Keys only a real product fills come out empty in a template-only record
(`spec_sheet_data.PRODUCT_ONLY_KEYS`): name and slug, Webflow Status, badge, Is Discontinued, short
description, features, featured and series images, gallery, documents, compatible products,
configurator intro text, sync fields, Is Configurable, and the spec links.

Staging check: for linked templates, the template-only record compared with the real export, product-
only keys left out. `differences` should be empty:

```python
import json
from illumenate_lighting.illumenate_lighting.spec_sheet_data import check_template_records
print(json.dumps(check_template_records(), default=str, indent=1))
```
