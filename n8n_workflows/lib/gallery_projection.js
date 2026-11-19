function projectWebflowGallery(payload, options) {
// ERP gallery payload (api/gallery_projection.build_payload) -> Webflow Galleries item body.
// Field slugs are those of the Galleries collection (docs/WEBFLOW_GALLERY_SYNC.md, section 5.1).
//
// Null-vs-omit rule (so a value cleared in ERP is cleared in Webflow, and nothing is blanked by accident):
// - Every text and rich-text field is always sent; an empty ERP value is sent as '' and clears the field.
// - List fields are always sent: `gallery` and `products-used` as arrays (possibly empty); the joined text
//   fields (`applications`, `services-provided`, `series-used`, `videos`) as '' when the list is empty.
// - `featured-image` is the hero image ({url, alt}) or null when there is none.
// - `credits` is ONE plain-text field holding a JSON array (a script on the Webflow page parses it), in this
//   order, only the credits that have a name: [{"type":"Integrator","name":"Acme","website":"https://..."}, ...].
//   `website` is null when there is none. No credits at all sends '' (not '[]'), so the field reads as empty
//   and a conditional "Credits is set" hides the section.
// - `completion-date` is midnight Pacific Time on the ERP date (an ISO instant: 07:00Z in daylight time, 08:00Z
//   otherwise), so the date reads the same on a site shown in Pacific Time. Omitted (not sent) when ERP has no date.
if (!options || typeof options.isDraft !== 'boolean') throw new Error('isDraft must be true or false');

const CREDIT_TYPES = ['Integrator', 'Architect', 'Designer', 'Contractor', 'Owner', 'Photographer'];

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
