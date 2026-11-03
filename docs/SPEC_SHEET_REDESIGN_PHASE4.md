# Spec Sheet Redesign: Phase 4 (stable link and file lifecycle)

Plan 4.7 (D6, D7, D19, D24). `spec_sheet_route.py`.

- **Stable link** per template: `https://<site>/spec-sheets/<record name, lowercase>.pdf`, for example
  `/spec-sheets/kit-ra01.pdf` (the `.pdf` is optional). A redirect, not a file: 302 with
  `Cache-Control: no-store` to the file the template's Spec Sheet field points at, so the previous PDF
  is served until the new one is registered. Unknown name, or a name two templates share in any case:
  404 (the second is logged). Served by a `page_renderer` hook, which Frappe asks before its own pages
  and static files.
- **On every successful generation** (`spec_sheet_job.register_spec_sheet`): Spec Sheet points at the
  new file, `spec_sheet_public_url` is set to the stable link, older files attached to the template's
  Spec Sheet field are deleted through their File documents keeping the newest 2 and never the current
  one, and the linked Webflow Product is saved so its Spec Sheet document row is the stable link. A
  failed run changes nothing.
- **File name** (D7): `<Template Name>_Spec Sheet.pdf`, record name when Template Name is empty, no
  brand prefix. Decided in ERPNext (`context.spec_sheet_file_name` in `get_spec_sheet_data`): spaces,
  brackets and dots kept; path separators, `: * ? " < > |` and control characters dropped. The
  per-brand regexes in the old Convert nodes are not used.
- **`webflow_export_v2.spec_sheet(product)`** (guest): read a product field that does not exist;
  now redirects through the product's template to its current spec sheet.

## Checks on staging (spikes S1, S2)

After deploying, generate a spec sheet for KIT-RA01, then from any terminal:

```bash
curl -sI https://stagingillumenate.v.frappe.cloud/spec-sheets/kit-ra01.pdf
```

Expect `302`, `Cache-Control: no-store` and a `Location` pointing at the current file. Also:

```bash
curl -sI https://stagingillumenate.v.frappe.cloud/spec-sheets/KIT-RA01
```

```bash
curl -sI https://stagingillumenate.v.frappe.cloud/spec-sheets/no-such-template.pdf
```

The first is the same redirect, the second a 404.

Not yet (migration, plan 4.7): repointing Webflow to the stable links and removing the old
`<Brand>_<Product>_Spec Sheet.pdf` files once Webflow shows the new links.
