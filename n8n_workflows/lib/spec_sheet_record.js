// Code for the "Get Product Info" node in the staging spec workflow (owner mapping 2026-11-02,
// docs/erpnext_spec_sheet_redesign_plan.md). Builds the record the Format nodes read
// (window.ERP_DATA) from get_spec_sheet_data: from the TEMPLATE where the owner mapped it,
// from legacy only for photometrics and colorimetry.
const data = $input.first().json.message;
if (!data || !data.template) {
  throw new Error('get_spec_sheet_data returned no template for ' + JSON.stringify(data && data.context));
}
const t = data.template;
const ctx = data.context || {};
const legacy = data.legacy || {};
const base = (ctx.base_url || '').replace(/\/$/, '');
const absolute = url => (!url ? null : /^https?:\/\//.test(url) ? url : base + (url.startsWith('/') ? '' : '/') + url);

const record = {
  // Template identity
  product_name: t.display_name || t.template_name || t.name,
  sublabel: t.sublabel || '',
  product_slug: String(t.template_code || t.name || '').toLowerCase(),
  product_type: ctx.product_type || legacy.product_type,
  // Template images (relative paths; the Format nodes make featured/dimension images absolute)
  featured_image: t.hero_image || null,
  dimensions_image_dark: t.dimensions_image || null,
  custom_dimensions_image_2: t.dimensions_image || null,
  // <TAG>.<MMDDYY> for #generated-date: the tag in the stored file name and the Pacific date
  // (owner, 2026-11-04). Made by ERPNext before the PDF is drawn.
  spec_sheet_stamp: ctx.spec_sheet_stamp || null,
  // Template link, so the Format nodes still find the template doctype and name
  [{
    'ilL-Tape-Neon-Template': 'tape_neon_template',
    'ilL-LED-Sheet-Template': 'led_sheet_template',
    'ilL-Extrusion-Kit-Template': 'kit_template',
    'ilL-Fixture-Template': 'fixture_template',
    'ilL-Driver-Template': 'driver_template',
    'ilL-Controller-Template': 'controller_template',
  }[ctx.template_doctype] || 'template']: ctx.template_id,
};

// Specifications: label, value and order only.
record.specifications = (t.specifications || []).map(row => ({
  spec_label: row.spec_label,
  spec_value: row.spec_value,
  display_order: row.display_order || 0,
}));

// Part number builder: the template's Part No. Configurator, unless the brand gets none.
const STEP_FIELDS = ['option_step', 'option_type', 'option_label', 'option_description', 'is_required', 'depends_on_step', 'allowed_values_json'];
record.configurator_options = ctx.include_configurator === false ? [] :
  (t.part_no_configurator || []).map(row => Object.fromEntries(STEP_FIELDS.map(f => [f, row[f] ?? null])));

// Kit components: the template's rows, grouped here by component type in template order
// (owner, 2026-11-03). Each group's component_description is a JSON string:
// [{hero_image}, {code, label}, ...]. hero_image is the group's Component Image (the first
// item's Variant Of image, set on template save); labels are each row's Description, trimmed.
const groups = new Map();
for (const row of t.kit_components || []) {
  if (!row.component_type) continue;
  if (!groups.has(row.component_type)) groups.set(row.component_type, {image: null, items: []});
  const group = groups.get(row.component_type);
  if (!group.image && row.component_image) group.image = absolute(row.component_image);
  group.items.push({code: row.component_item || '', label: String(row.component_description || '').trim()});
}
record.kit_components = Array.from(groups, ([type, group]) => ({
  component_type: type,
  component_description: JSON.stringify([...(group.image ? [{hero_image: group.image}] : []), ...group.items], null, 1),
}));

// Certifications: the template's rows; the badge is the brand's dark badge (Badge Image).
const legacyCodes = Object.fromEntries((legacy.certifications || []).map(c => [c.certification, c.certification_details?.certification_code]));
record.certifications = (t.certifications || []).filter(row => row.certification).map(row => ({
  certification: row.certification,
  certification_details: {
    certification_code: legacyCodes[row.certification] || row.certification,
    badge_image: absolute(row.badge_image),
    '206_badge_dark': absolute(row.badge_image),
  },
}));

// Spec Gallery (owner, 2026-11-04): extra images per spec sheet section, in table order.
record.spec_gallery = (t.spec_gallery || [])
  .filter(row => row.gallery_section && row.gallery_img)
  .map(row => ({
    section: row.gallery_section,
    title: String(row.gallery_title || '').trim(),
    image: absolute(row.gallery_img),
  }));

// Compatible power supplies: the template's table (owner, 2026-11-05), sorted by max wattage
// on save. The Format nodes still read the old key custom_compatible_power_supplies.
const SUPPLY_FIELDS = ['part_number', 'input_protocol', 'voltagefrequency', 'output_voltage', 'max_wattage', 'location_rating', 'output_count'];
record.custom_compatible_power_supplies = (t.compatible_power_supplies || [])
  .map(row => Object.fromEntries(SUPPLY_FIELDS.map(f => [f, row[f] ?? ''])));

// Still from legacy (owner, 2026-11-02).
record.photometric_image = legacy.photometric_image;
record.photometric_data = legacy.photometric_data;
record.colorimetry = legacy.colorimetry;

return [{json: {message: {products: [record], brand: ctx.brand, context: ctx}}}];
