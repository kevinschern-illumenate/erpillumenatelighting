function projectWebflowProduct(product, brandConfig) {
// Transform ERPNext product to Webflow format - FULL DATA SYNC

const isUpdate = product.webflow_item_id ? true : false;

// ============================================
// FEATURE FLAGS
// ============================================
// Set to true AFTER creating the corresponding fields in your Webflow
// Products collection (CMS Designer).  Until then, keep false to avoid
// "Field not described in schema" 400 errors from Webflow.
const INCLUDE_ATTRIBUTE_DISPLAY_FIELDS = false; // e.g. finishes-5, cct-options-5
const INCLUDE_ATTRIBUTE_FILTER_FIELDS  = false; // e.g. finish-filter, cri-filter
const INCLUDE_CATEGORY_REF_FIELD       = false; // category-filter (ItemRef)

// ============================================
// URL HELPERS
// ============================================
const ERPNEXT_BASE_URL = brandConfig.erpnext_base_url;

const makeAbsoluteUrl = (url) => {
  if (!url) return null;
  let fullUrl = url;
  if (!url.startsWith('http://') && !url.startsWith('https://')) {
    fullUrl = url.startsWith('/') ? `${ERPNEXT_BASE_URL}${url}` : `${ERPNEXT_BASE_URL}/${url}`;
  }
  // Encode spaces and brackets in the path portion so Webflow can fetch the file
  const qIdx = fullUrl.indexOf('?');
  const path = qIdx >= 0 ? fullUrl.substring(0, qIdx) : fullUrl;
  const qs   = qIdx >= 0 ? fullUrl.substring(qIdx) : '';
  const encoded = path.replace(/ /g, '%20').replace(/\[/g, '%5B').replace(/\]/g, '%5D');
  return encoded + qs;
};


const isValidImageUrl = (url) => {
  if (!url) return false;
  if (url.includes('/private/')) return false;
  if (!url.startsWith('http://') && !url.startsWith('https://')) return false;
  return true;
};

const isValidFileUrl = (url) => {
  if (!url) return false;
  if (url.includes('/private/')) return false;
  return true;
};

// ============================================
// ATTRIBUTE FILTER FIELDS
// ============================================
// ERPNext provides pre-built plain-text filter data via filter_field_data.
// Filter fields contain comma-separated attribute names for Webflow CMS filtering.
const filterFieldData = product.filter_field_data || {};

// Plain text display fields (name, code formatted with pipe separators)
const attributeTextByType = product.attribute_text_by_type || {};
const attributeLinksByType = product.attribute_links_by_type || {};
const attributeLinks = product.attribute_links || [];

// Helper: get pipe-separated display text for an attribute type
const getAttrText = (type) => attributeTextByType[type] || '';

// Feed Direction - combine Feed Direction and Power Feed Type
const formatAttrPair = (a) => {
  const label = a.display_label || a.attribute_name || '';
  const code = a.attribute_code || '';
  if (!label) return '';
  return code ? `${label}, ${code}` : label;
};
const feedDirectionPairs = (attributeLinksByType['Feed Direction'] || []).map(formatAttrPair).filter(v => v);
const powerFeedTypePairs = (attributeLinksByType['Power Feed Type'] || []).map(formatAttrPair).filter(v => v);
const allFeedDirectionText = [...new Set([...feedDirectionPairs, ...powerFeedTypePairs])].join(' | ');

// LED Package
const ledPackageAttrs = attributeLinksByType['LED Package'] || [];
const fixtureTypes = ledPackageAttrs.map(formatAttrPair).filter(v => v).join(' | ');

// ============================================
// GALLERY IMAGES (Multi-image field)
// ============================================
const rawGalleryImages = product.gallery_images || [];
const galleryImages = rawGalleryImages
  .map(img => {
    const imageUrl = makeAbsoluteUrl(img.image || img.url || img.file_url);
    return {
      url: imageUrl,
      alt: img.alt_text || img.caption || product.product_name
    };
  })
  .filter(img => isValidImageUrl(img.url));

// ============================================
// DOCUMENTS (JSON for file links)
// ============================================
const documents = (product.documents || []).map(doc => ({
  url: makeAbsoluteUrl(doc.document_file),
  type: doc.document_type,
  title: doc.document_title,
  order: doc.display_order
}));

// ============================================
// SPEC SHEET FILE (for Webflow file field)
// ============================================
const specSheetDoc = (product.documents || []).find(doc => doc.document_type === 'Spec Sheet');
const specSheetUrl = specSheetDoc ? makeAbsoluteUrl(specSheetDoc.document_file) : null;

// ============================================
// CERTIFICATIONS
// ============================================
const certifications = (product.certifications || []).map(c => ({
  name: c.certification,
  code: c.certification_details?.certification_code,
  body: c.certification_details?.certification_body,
  badge: makeAbsoluteUrl(c.certification_details?.badge_image)
}));

// ============================================
// COMPATIBLE PRODUCTS
// ============================================
const compatibleProducts = (product.compatible_products || []).map(cp => ({
  product: cp.related_product,
  type: cp.relationship_type,
  notes: cp.notes
}));

// ============================================
// CONFIGURATOR OPTIONS
// ============================================
const configuratorOptions = (product.configurator_options || []).map(opt => ({
  step: opt.option_step,
  type: opt.option_type,
  label: opt.option_label,
  description: opt.option_description,
  required: opt.is_required,
  dependsOn: opt.depends_on_step,
  allowedValues: opt.allowed_values_json
}));

// ============================================
// FEED LENGTHS (Webflow part-number configurator)
// ============================================
const feedLengths = (product.feed_lengths || []).map(fl => ({
  step: fl.step,
  label: fl.label,
  code: fl.code
}));

// ============================================
// KIT COMPONENTS
// ============================================
const kitComponents = (product.kit_components || []).map(k => ({
  type: k.component_type,
  item: k.component_item,
  specDoctype: k.component_spec_doctype,
  specName: k.component_spec_name,
  qty: k.quantity,
  notes: k.notes
}));

// ============================================
// LENGTH CONVERSIONS
// ============================================
const mmToInches = (mm) => mm ? Math.round((mm / 25.4) * 100) / 100 : 0;

// ============================================
// BUILD FIELD DATA
// ============================================
const fieldData = {
  // Basic Info
  "name": product.product_name,
  "product-type": product.product_type,
  "short-description": product.short_description || '',
  "subheading": product.sublabel || '',
  "erp-sync-id": product.product_slug,
  
  // Configurator Settings - NOTE: field is "is-configurable-3" in Webflow
  "is-configurable-3": product.is_configurable === 1 || product.is_configurable === true,
  "configurator-intro": product.configurator_intro_text || '',
  "min-length-mm": product.min_length_mm || 0,
  "max-length-mm": product.max_length_mm || 0,
  "min-length-inches": mmToInches(product.min_length_mm),
  "max-length-inches": mmToInches(product.max_length_mm),
  
  // Series Info (from linked series doctype)
  "series-display-name": product.series || product.series_display_name || '',
  
  // Sync timestamp

  
  // JSON data fields
  "specifications-json": JSON.stringify(product.specifications || []),
  "attribute-links-json": JSON.stringify(attributeLinks),
  "documents-json": JSON.stringify(documents),
  "certifications-json": JSON.stringify(certifications),
  "configurator-options-json": JSON.stringify(configuratorOptions),
  "feed-lengths-json": JSON.stringify(feedLengths),
  "kit-components-json": JSON.stringify(kitComponents),
  "compatible-products-json": JSON.stringify(compatibleProducts),
  // Features JSON
  "features-json": product.features_json || "[]",
  // Product Badge
  "product-badge": product.product_badge || "",
};

// ============================================
// CATEGORY REFERENCE (requires Webflow Item ID)
// ============================================
const categoryWebflowId = product.category_webflow_item_id || product.product_category_webflow_item_id || (product.category_details && product.category_details.webflow_item_id);
if (INCLUDE_CATEGORY_REF_FIELD && categoryWebflowId && /^[a-f0-9]{24}$/i.test(categoryWebflowId)) {
  fieldData["category-filter"] = categoryWebflowId;
}

// ============================================
// PLAIN TEXT ATTRIBUTE FIELDS (existing, unchanged)
// ============================================
// These plain text fields remain for display purposes.
if (INCLUDE_ATTRIBUTE_DISPLAY_FIELDS) {
fieldData['finishes-5'] = getAttrText('Finish');
fieldData['lens-options-5'] = getAttrText('Lens Appearance');
fieldData['mounting-methods-5'] = getAttrText('Mounting Method');
fieldData['cct-options-5'] = getAttrText('CCT');
fieldData['output-levels-5'] = getAttrText('Output Level');
fieldData['cris-5'] = getAttrText('CRI');
fieldData['feed-directions-5'] = allFeedDirectionText;
fieldData['environment-ratings-5'] = getAttrText('Environment Rating');
fieldData['fixture-types-5'] = fixtureTypes;
}

// ============================================
// PLAIN TEXT FILTER FIELDS (for Webflow CMS filtering)
// ============================================
// These fields (with '-filter' suffix) contain comma-separated attribute
// names for Webflow CMS filtering. They are plain text, not multi-reference.
if (INCLUDE_ATTRIBUTE_FILTER_FIELDS) {
for (const [slug, text] of Object.entries(filterFieldData)) {
  if (text) {
    fieldData[slug] = text;
  }
}
}

// Slug only on create
if (!isUpdate) {
  fieldData["slug"] = product.product_slug;
}

// ============================================
// BUILD WEBFLOW PAYLOAD
// ============================================
const webflowData = {
  isArchived: false,
  isDraft: true,
  fieldData: fieldData
};

// ============================================
// IMAGE FIELDS
// ============================================
const featuredImageUrl = makeAbsoluteUrl(product.featured_image);
if (isValidImageUrl(featuredImageUrl)) {
  webflowData.fieldData["featured-image"] = { url: featuredImageUrl };
}

const dimensionsImageUrl = makeAbsoluteUrl(product.dimensions_image);
if (isValidImageUrl(dimensionsImageUrl)) {
  webflowData.fieldData["dimensions"] = { url: dimensionsImageUrl };
}

const seriesFamilyImageUrl = makeAbsoluteUrl(product.series_family_image);
if (isValidImageUrl(seriesFamilyImageUrl)) {
  webflowData.fieldData["family-image"] = { url: seriesFamilyImageUrl };
}

if (galleryImages.length > 0) {
  webflowData.fieldData["gallery"] = galleryImages;
}

// ============================================
// SPEC SHEET FILE FIELD
// ============================================
if (specSheetUrl && isValidFileUrl(specSheetUrl)) {
  webflowData.fieldData["spec-sheet"] = { url: specSheetUrl };
}

// ============================================
// PER-BRAND CONFIGURATOR GUARD (defense in depth — server also strips)
// ============================================
try {

  if (brandConfig && brandConfig.include_configurator_payload === false) {
    delete webflowData.fieldData['is-configurable-3'];
    delete webflowData.fieldData['configurator-intro'];
    delete webflowData.fieldData['min-length-mm'];
    delete webflowData.fieldData['max-length-mm'];
    delete webflowData.fieldData['min-length-inches'];
    delete webflowData.fieldData['max-length-inches'];
    delete webflowData.fieldData['configurator-options-json'];
    delete webflowData.fieldData['feed-lengths-json'];
    delete webflowData.fieldData['kit-components-json'];
  }
} catch (e) { throw e; }

// ============================================
// RETURN FULL DATA
// ============================================
return {
  json: {
    webflowData,
    originalProduct: product,
    _debug: {
      featuredImageUrl,
      dimensionsImageUrl,
      galleryImagesCount: galleryImages.length,
      rawGalleryCount: rawGalleryImages.length,
      rawGalleryImages: rawGalleryImages.slice(0, 3),
      processedGalleryImages: galleryImages.slice(0, 3),
      fixtureTypes: fixtureTypes,
      ledPackageAttrs: ledPackageAttrs,
      categoryWebflowId: categoryWebflowId,
      productCategory: product.product_category,
      categoryDetails: product.category_details,
      specSheetUrl: specSheetUrl,
      filterFieldData: filterFieldData,
      filterSlugsUsed: Object.keys(filterFieldData).filter(s => filterFieldData[s])
    }
  }
};
}
if (typeof module !== "undefined") module.exports = { projectWebflowProduct };
