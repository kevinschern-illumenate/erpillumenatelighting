function projectWebflowGallery(payload, options) {
// ERP gallery payload (api/gallery_projection.build_payload) -> Webflow Galleries item body.
// Field slugs are those of the Galleries collection (docs/WEBFLOW_GALLERY_SYNC.md, section 5.1).
//
// Null-vs-omit rule (so a value cleared in ERP is cleared in Webflow, and nothing is blanked by accident):
// - Every text and rich-text field is always sent; an empty ERP value is sent as '' and clears the field.
// - List fields are always sent: `gallery` and `products-used` as arrays (possibly empty); the joined text
//   fields (`applications`, `services-provided`, `series-used`, `videos`) as '' when the list is empty.
// - `featured-image` is the hero image ({url, alt}) or null when there is none.
// - Credits: an unfilled name/website pair is never sent as empty strings. A credit type missing from
//   payload.credits sends null for both slugs, so a removed credit is cleared; a credit without a website
//   sends null for the website (a Link field rejects '').
// - `completion-date` is an ISO date-time string, and is omitted (not sent) when ERP has no date.
if (!options || typeof options.isDraft !== 'boolean') throw new Error('isDraft must be true or false');

const CREDIT_FIELDS = {
  Integrator: ['client-integrator', 'client-website'],
  Architect: ['architect', 'architect-website'],
  Designer: ['designer', 'designer-website'],
  Contractor: ['contractor', 'contractor-website'],
  Owner: ['owner', 'owner-website'],
  Photographer: ['photo-credit', 'photographer-website']
};

const text = (value) => (typeof value === 'string' ? value : '');
const joined = (values) => (Array.isArray(values) ? values.filter(v => typeof v === 'string' && v).join(', ') : '');
const image = (row) => (row && row.url ? { url: row.url, alt: text(row.alt) } : null);

const fieldData = {
  'name': text(payload.name),
  'slug': text(payload.slug),
  'erp-sync-id': text(payload.erp_sync_id),
  'featured': payload.featured === true,
  'featured-image': image(payload.hero_image),
  'gallery': (payload.gallery_images || []).map(image).filter(Boolean),
  'short-description': text(payload.seo_description),
  'about': text(payload.about),
  'case-study': text(payload.case_study_html),
  'project-type': text(payload.gallery_type),
  'applications': joined(payload.applications),
  'services-provided': joined(payload.services_provided),
  'products-used': (payload.product_item_ids || []).filter(id => /^[a-f0-9]{24}$/i.test(id)),
  'series-used': joined(payload.series_used),
  'product-notes': text(payload.product_notes_html),
  'quote': text(payload.quote),
  'quote-attribution': text(payload.quote_attribution),
  'location': text(payload.location),
  'videos': joined(payload.videos),
  'custom-items': text(payload.custom_items_html)
};
if (!fieldData.name || !fieldData.slug || !fieldData['erp-sync-id']) throw new Error('Gallery name, slug and erp-sync-id are required');

if (payload.completion_date) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(payload.completion_date)) throw new Error('completion_date must be YYYY-MM-DD');
  const date = new Date(payload.completion_date + 'T00:00:00.000Z');
  if (isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== payload.completion_date) throw new Error('completion_date is not a date');
  fieldData['completion-date'] = date.toISOString();
}

const credits = payload.credits || {};
for (const [type, [nameSlug, websiteSlug]] of Object.entries(CREDIT_FIELDS)) {
  const credit = credits[type] || {};
  fieldData[nameSlug] = text(credit.name) || null;
  fieldData[websiteSlug] = (fieldData[nameSlug] && text(credit.website)) || null;
}

return { isArchived: false, isDraft: options.isDraft, fieldData };
}
if (typeof module !== "undefined") module.exports = { projectWebflowGallery };
