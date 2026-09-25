# Product authoring and field register

Engineering and Catalog Publisher are named System User roles. They can edit the shipped product template/specification/attribute/compatibility/PDF-mapping families and approved Item literature. Item creation, purchasing costs, accounting, and publication credentials retain their separate ERP permissions. No migration assigns a role to a person. Incomplete drafts remain saveable; channel approval performs current dependency checks.

Use **Actions → Engineering preflight** on the five template forms. Resolve the record/field findings, follow the affected-product links, and use the product's **Channel preflight** for configure, PDF, portal and CMS. The affected-product scan is paginated; continue until no next-page button remains. Approval must use the current saved revision. A change to a referenced specification, option, Item, map, file or eligible driver requires another inspection.

| Source contract | Portal / configurator | CMS projection | Filled PDF source |
|---|---|---|---|
| Webflow Product `product_name`, `product_slug`, `short_description`, `product_type` | Active detail, search, category and family action | Shared `n8n_workflows/lib/product_projection.js`: `name`, `erp-sync-id`, create-time `slug`, description and family fields | `ilL-Webflow-Product` mapping fields; commercial fields are excluded |
| Product featured/dimensions/family/gallery images | Images and dimensions with missing-image state | `featured-image`, `dimensions`, `family-image`, `gallery` | Approved public literature; never use customer documents as CMS assets |
| Product document rows and template literature | Typed public document links; filled configuration action is distinct | `spec-sheet` plus projection document content | Family template `spec_submittal_template` and field mapping records |
| Specification and certification master links | Named attributes, units and certifications | Approved export projection; optional CMS display/filter fields stay disabled until CMS schema verification | Explicit source DocType/field mapping; empty required values fail |
| Linear template, profile/lens/endcap/mounting maps, tape offering and cable map | Allowed choices, dimensions, feeds, segments, exact cut/build manifest | Configurator option/feed JSON when enabled for that brand | Configured Fixture, owning line/project, template and approved mapping |
| Tape/Neon template and active tape specs | Custom segments or continuous-stock bulk reels; feed, power and override controls | Family options in shared projection | Configured Tape/Neon and Neon mapping; reel mode has no cut-assembly cables |
| Sheet allowed specs/options, panel dimensions, full panel wattage, required input protocol | Coverage per axis, active spec, power/dimming; TW uses full watts | Public choices API plus family metadata; no guest prices | Configured Sheet's sealed build and `sheet_engineering`; later spec edits cannot change pinned electrical values |
| Driver eligibility and spec capacities/protocols | Exact compatible supply/output allocation; excluded-power requirements remain visible | Approved engineering selection data only | Build allocation and instructions; color channels are not presumed independent outputs |
| Driver/Controller template variants or product `portal_item` | Approved enabled sales SKU plus quantity in its stock UOM | Standard product metadata | Approved Item Literature registry for static inclusion; mapped variant submittal where configured |
| Schedule line designation/location/notes/quantity | Editable presentation plus stable line identity | Never exported as product CMS content | Private project packet, schedule/index pages and group member labels |
| Group request independent members/shared spec/power | One sellable group line; quantity repeats the entire group | No public group toggle until rollout acceptance | Per-member filled pages, friendly labels plus canonical M keys, shared power/cut instructions |
| `ill_fixture_type`, `ill_section_label`, `additional_notes`, configured links/BOM/snapshot | Commercial row presentation | Never published | ERP prints designation above and notes below; DN/SI copy exact source-row build fields |

The JS projection and family mapping DocTypes are the executable field-level register. CMS optional fields are intentionally feature switches in that projection; enabling one requires confirming its actual Webflow field type. Do not enable them based on label similarity. Template mapping rows record the actual PDF form field name, source, transformation, required value, and any public override separately. Inspect a real sample PDF after changing mappings.

## Imports and engineering setup

Generate family imports with `python -m tools.fixture_builder` using the existing CLI. Sheet CSVs include CCT, required input protocol, full panel watts, optional explicit feed limit, driver eligibility and Required Value mapping columns. Linear/Tape/Neon mapping generators also retain cloned Required Value choices. The legacy Sheet PDF field named `jumper_cables_extra` now maps to the complete assembly quantity `jumper_cables_included`; relabel that form field in a new PDF master when convenient.

Run `python tools/validate_authoring_csv.py path/to/ilL-Spec-LED-Sheet.csv` before importing flat Spec or Submittal-Mapping files. It checks shipped headers, required/Select values, finite electrical quantities and supported pure engineering rules. Parent/child template imports, Link existence, Driver/Controller protocol tables, Items/UOMs and actual PDFs must also pass native Data Import and channel preflight. Import validation never replaces the publication gate.

Create/approve the component Items and UOMs with an ERP Item maintainer. Engineering then authors specs and active compatibility maps; Catalog adds copy, imagery and public literature. For driver specs, explicitly set independent outputs, total/per-output limits and usable load factor. For Sheet, leave the optional feed limit empty when eligible driver capacity supplies the limit. Excluded supplies still need a defensible feed limit or eligible engineering driver data.

References chosen by the owner: `ILL-SH01-SW`, `led-hd-sw`, `non-pnc-sw`, `Snowfield Static White LED Sheet`. Their installed records and numerical outputs still require engineering approval. Linear cable-price inclusion remains on the existing price basis until the owner supplies a different pricing policy.

## Public Sheet embed

Set approved CORS origins on the ERP site and deploy the existing `webflow_spec_sheet_download.js` after this markup. Replace the two example attributes with the approved brand/site values. The loader constructs accessible spec/options/coverage/power controls from active ERP choices; failed loading offers Retry without pretending a configuration exists.

```html
<section data-ill-product-type="LED Sheet"
         data-ill-product-slug="YOUR-PRODUCT-SLUG"
         data-ill-erp-origin="https://YOUR-ERP-HOST">
  <div data-ill-sheet-configurator></div>
  <button type="button" id="ill-download-spec-sheet">Download specification</button>
  <a href="https://YOUR-ERP-HOST/portal/configure" data-ill-portal-handoff>Continue in portal</a>
</section>
```

The portal handoff carries editable selections and preserves them through sign-in. Guest output contains product/engineering information only. Customer project metadata requires authenticated private generation; do not put customer names into public CMS fields or shared product-file caches.
