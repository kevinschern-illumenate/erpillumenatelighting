function projectWebflowGallery(payload, options) {
// ERP gallery payload (api/gallery_projection.build_payload) -> Webflow Galleries item body.
// Field slugs are those of the Galleries collection (docs/WEBFLOW_GALLERY_SYNC.md, section 5.1).
//
// Null-vs-omit rule (so a value cleared in ERP is cleared in Webflow, and nothing is blanked by accident):
// - Every text and rich-text field is always sent; an empty ERP value is sent as '' and clears the field.
// - `gallery` is always sent as an array (possibly empty); the joined text fields (`applications`,
//   `services-provided`, `series-used`, `videos`) as '' when the list is empty.
// - The hero image ({url, alt}, or null when there is none) and the SEO description go to the fields named by
//   options.heroField ('featured-image' by default) and options.seoField ('short-description' by default), because the
//   collections on the two Webflow sites use different slugs for them.
// - `products-used` stays a multi-reference field: the Webflow item IDs of the products (an array, possibly empty).
// - `product-notes` is ONE plain-text field holding a JSON array of the Products Used table, row by row (a script on
//   the Webflow page parses it): [{"product":"kit-ra01","name":"Rainier [SF] Extrusion Kit","slug":"kit-ra01",
//   "series":"Rainier","note":"White finish","webflow_item_id":"6aeb..."}, ...]. A series-only row has null product, name,
//   slug and webflow_item_id. No rows sends ''. When the payload has no `products` key (an ERP that does not send
//   it yet) the field is left out rather than cleared.
// - `credits` is ONE plain-text field holding a JSON array (a script on the Webflow page parses it), in this
//   order, only the credits that have a name: [{"type":"Integrator","name":"Acme","website":"https://..."}, ...].
//   `website` is null when there is none. No credits at all sends '' (not '[]'), so the field reads as empty
//   and a conditional "Credits is set" hides the section.
// - `completion-date` is midnight Pacific Time on the ERP date (an ISO instant: 07:00Z in daylight time, 08:00Z
//   otherwise), so the date reads the same on a site shown in Pacific Time. Omitted (not sent) when ERP has no date.
if (!options || typeof options.isDraft !== 'boolean') throw new Error('isDraft must be true or false');

const heroField = options.heroField || 'featured-image';
const seoField = options.seoField || 'short-description';
const CREDIT_TYPES = ['Integrator', 'Architect', 'Designer', 'Contractor', 'Owner', 'Photographer'];

const text = (value) => (typeof value === 'string' ? value : '');
const joined = (values) => (Array.isArray(values) ? values.filter(v => typeof v === 'string' && v).join(', ') : '');
const image = (row) => (row && row.url ? { url: row.url, alt: text(row.alt) } : null);

const fieldData = {
  'name': text(payload.name),
  'slug': text(payload.slug),
  'erp-sync-id': text(payload.erp_sync_id),
  'featured': payload.featured === true,
  [heroField]: image(payload.hero_image),
  'gallery': (payload.gallery_images || []).map(image).filter(Boolean),
  [seoField]: text(payload.seo_description),
  'about': text(payload.about),
  'case-study': text(payload.case_study_html),
  'project-type': text(payload.gallery_type),
  'applications': joined(payload.applications),
  'services-provided': joined(payload.services_provided),
  'products-used': (payload.product_item_ids || []).filter(id => /^[a-f0-9]{24}$/i.test(id)),
  'series-used': joined(payload.series_used),
  'quote': text(payload.quote),
  'quote-attribution': text(payload.quote_attribution),
  'location': text(payload.location),
  'videos': joined(payload.videos),
  'custom-items': text(payload.custom_items_html)
};
if (Array.isArray(payload.products)) {
  const rows = payload.products.map(row => ({
    product: text(row.product) || null, name: text(row.name) || null, slug: text(row.slug) || null,
    series: text(row.series) || null, note: text(row.note) || null, webflow_item_id: text(row.webflow_item_id) || null
  }));
  fieldData['product-notes'] = rows.length ? JSON.stringify(rows) : '';
}
if (!fieldData.name || !fieldData.slug || !fieldData['erp-sync-id']) throw new Error('Gallery name, slug and erp-sync-id are required');

if (payload.completion_date) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(payload.completion_date)) throw new Error('completion_date must be YYYY-MM-DD');
  const check = new Date(payload.completion_date + 'T00:00:00.000Z');
  if (isNaN(check.getTime()) || check.toISOString().slice(0, 10) !== payload.completion_date) throw new Error('completion_date is not a date');
  // Pacific midnight is 07:00Z (PDT) or 08:00Z (PST): take the one that reads 00:00 on that date in Los Angeles.
  const [year, month, day] = payload.completion_date.split('-').map(Number);
  const pacific = new Intl.DateTimeFormat('en-CA', {timeZone: 'America/Los_Angeles', year: 'numeric', month: '2-digit',
    day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23'});
  const midnight = [7, 8].map(hours => new Date(Date.UTC(year, month - 1, day, hours)))
    .find(instant => pacific.format(instant).replace(',', '') === payload.completion_date + ' 00:00');
  if (!midnight) throw new Error('completion_date has no Pacific midnight');
  fieldData['completion-date'] = midnight.toISOString();
}

const credits = payload.credits || {};
const creditList = CREDIT_TYPES
  .map(type => ({ type, name: text((credits[type] || {}).name), website: text((credits[type] || {}).website) }))
  .filter(credit => credit.name)
  .map(credit => ({ type: credit.type, name: credit.name, website: credit.website || null }));
fieldData['credits'] = creditList.length ? JSON.stringify(creditList) : '';

return { isArchived: false, isDraft: options.isDraft, fieldData };
}
if (typeof module !== "undefined") module.exports = { projectWebflowGallery };
