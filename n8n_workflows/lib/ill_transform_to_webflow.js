// Code for the "(ilL) Transform to Webflow Format" node in the staging sync workflow (W2).
// Field mapping signed off by the owner on 2026-11-04/05: docs/erpnext_spec_sheet_redesign_plan.md
// sections 4.16 and 4.19. The template's fields come from payload.template (ERPNext
// webflow_sync_payload.template_section); the product's from payload.product (the export).
// Fields not listed here are never sent, so Webflow keeps whatever they hold.
const data = $('Set Brand Config').first().json;
const payload = data.payload || {};
const product = data.enriched_product || {};
const tpl = payload.template || null;
const brand = data.brand;
const everPublished = Boolean(payload.webflow_state && payload.webflow_state.ever_published);

const baseUrl = String((payload.brand && payload.brand.erpnext_base_url) || 'https://stagingillumenate.v.frappe.cloud').replace(/\/$/, '');
// Spaces and other characters Webflow cannot fetch are percent-encoded; existing %XX escapes,
// slashes and brackets are kept, so an already encoded URL is not encoded twice.
const encodeUrl = url => String(url).replace(/[^A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]/g, ch => encodeURIComponent(ch));
const fullUrl = path => (!path ? null : encodeUrl(/^https?:\/\//.test(path) ? path : baseUrl + (path.startsWith('/') ? '' : '/') + path));
const json = list => (Array.isArray(list) && list.length ? JSON.stringify(list) : '');

// --- Status (plan 4.19 Q1): Published/Discontinued are published; a Webflow Draft is staged
// only, or published hidden once it was ever published; Archived is archived. Unknown values
// fail closed (never public).
let isDraft = false;
let isArchived = false;
let hiddenFromPublic = true;
switch (product.custom_webflow_status || '') {
  case 'Published':
  case 'Discontinued':
    hiddenFromPublic = false;
    break;
  case 'Archived':
    isArchived = true;
    break;
  default: // Webflow Draft, empty or unknown
    isDraft = !everPublished;
}

// --- Kit components: grouped by component type in template order, the same output as the
// spec sheet's Get Product Info: [{component_type, component_description: JSON of
// [{hero_image}, {code, label}, ...]}].
function kitGroups(rows) {
  const groups = new Map();
  for (const row of rows || []) {
    if (!row.component_type) continue;
    if (!groups.has(row.component_type)) groups.set(row.component_type, {image: null, items: []});
    const group = groups.get(row.component_type);
    if (!group.image && row.component_image) group.image = fullUrl(row.component_image);
    group.items.push({code: row.component_item || '', label: String(row.component_description || '').trim()});
  }
  return Array.from(groups, ([type, group]) => ({
    component_type: type,
    component_description: JSON.stringify([...(group.image ? [{hero_image: group.image}] : []), ...group.items], null, 1),
  }));
}

let galleryFormatted = (product.gallery_images || [])
  .map(img => fullUrl(img.image_url || img.file_url || img.image))
  .filter(Boolean)
  .map(url => ({url}));

const generatedSlug = product.product_slug || String(product.name || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)+/g, '');

// Pacific date at noon UTC.
const pt = new Date(new Date().toLocaleString('en-US', {timeZone: 'America/Los_Angeles'}));
const finalSyncDate = `${pt.getFullYear()}-${String(pt.getMonth() + 1).padStart(2, '0')}-${String(pt.getDate()).padStart(2, '0')}T12:00:00.000Z`;

const fieldData = {
  // 1, 2, 12, 14
  name: (tpl && tpl.display_name) || product.product_name || product.name,
  slug: generatedSlug,
  'last-synced': finalSyncDate,
  'erp-sync-id': product.name,
  // 3
  'hidden-from-public': hiddenFromPublic,
  // 7 to 10 (product)
  'short-description': product.short_description || '',
  'featured-image': fullUrl(product.featured_image),
  gallery: galleryFormatted.length ? galleryFormatted : null,
  'family-image': fullUrl(product.series_family_image),
  // 11, 26, 27 (template)
  'series-display-name': tpl ? (tpl.series_name || '') : (product.series_display_name || ''),
  subheading: tpl ? (tpl.sublabel || '') : (product.sublabel || ''),
  dimensions: fullUrl(tpl ? tpl.dimensions_image : product.dimensions_image_light),
  // 13, 15, 17, 19, 20, 28 (product)
  'is-configurable-3': product.is_configurable === 1 || product.is_configurable === true,
  'attribute-links-json': json(product.attribute_links),
  'compatible-products-json': json(product.compatible_products),
  // In display order, so the Spec Sheet (the stable spec_sheet_public_url link, order 1) is first.
  'documents-json': json((product.documents || []).slice().sort((a, b) => (a.display_order || 0) - (b.display_order || 0))),
  'features-json': product.features_json || json(product.features),
  'product-badge': product.product_badge || '',
  // Web Badge (owner, 2026-11-05): the product's webflow_badge into the new web-badge field.
  'web-badge': product.webflow_badge || '',
  // 16, 18, 22, 23 (template)
  'certifications-json': json(((tpl && tpl.certifications) || []).map(row => ({...row, badge_image: fullUrl(row.badge_image)}))),
  'configurator-options-json': json(tpl ? tpl.configurator : []),
  'kit-components-json': json(kitGroups(tpl ? tpl.kit_components : [])),
  'specifications-json': json(tpl ? tpl.specifications : []),
};
// 25: template Price per Foot (MSRP), else Base Price (MSRP)
if (tpl && tpl.price_per_foot_msrp != null) fieldData['price-per-foot-msrp'] = tpl.price_per_foot_msrp;
// 6: category reference (this brand's category item)
if (product.category_webflow_item_id) fieldData.category = product.category_webflow_item_id;

return {
  json: {
    originalProduct: {
      webflow_item_id: product.webflow_item_id || null,
      product_slug: generatedSlug,
      brand,
      job: data.job || '',
      token: data.token || '',
      revision_hash: data.revision_hash || '',
      payload_hash: data.payload_hash || '',
    },
    webflow_collection_id: data.webflow_collection_id,
    webflowData: {isArchived, isDraft, fieldData},
  },
};
