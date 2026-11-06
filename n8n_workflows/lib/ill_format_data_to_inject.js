// Code for the "(ilL) Format Data to Inject" node in the staging spec workflow (NW0NxiyqKyeVrkOJ).
// Kept here so changes are reviewed; paste into the node when it changes.
// 1. Safely extract the HTML string from 'Fetch Webflow Template'
const templateOutput = $('(ilL) Fetch Webflow Template').first().json;
let html = templateOutput.data || templateOutput.body || (typeof templateOutput === 'string' ? templateOutput : null);

if (!html) {
    throw new Error("HTML template string is missing from 'Fetch Webflow Template'.");
}

// 2. NUKE COOKIE CONSENT BANNERS & LAZY LOADING
html = html.replace(/<script[^>]*termly[^>]*><\/script>/gi, '');
html = html.replace(/<script[^>]*cookie[^>]*><\/script>/gi, '');
html = html.replace(/loading="lazy"/gi, ''); 

// 3. Extract fully enriched product
let erpData;
try {
    erpData = $('Get Product Info').first().json.message.products[0];
} catch (e) {
    erpData = $('Get Product Info').first().json.message.products[0];
}

// Pre-process Image URLs
if (erpData.featured_image && !erpData.featured_image.startsWith('http')) {
    erpData.featured_image = 'https://stagingillumenate.v.frappe.cloud' + (erpData.featured_image.startsWith('/') ? '' : '/') + erpData.featured_image;
}
if (erpData.dimensions_image_dark && !erpData.dimensions_image_dark.startsWith('http')) {
    erpData.dimensions_image_dark = 'https://stagingillumenate.v.frappe.cloud' + (erpData.dimensions_image_dark.startsWith('/') ? '' : '/') + erpData.dimensions_image_dark;
}

// 3b. Reconstruct template_doctype and template_name (Imported from 206 Script)
const templateMap = {
    tape_neon_template: 'ilL-Tape-Neon-Template',
    led_sheet_template: 'ilL-LED-Sheet-Template',
    kit_template: 'ilL-Extrusion-Kit-Template',
    fixture_template: 'ilL-Fixture-Template',
    driver_template: 'ilL-Driver-Template',
    controller_template: 'ilL-Controller-Template'
};

let resolved_template_doctype = null;
let resolved_template_name = null;

for (const [key, doctype] of Object.entries(templateMap)) {
    if (erpData[key]) {
        resolved_template_doctype = doctype;
        resolved_template_name = erpData[key];
        break;
    }
}

// 3c. Highlights for the configured spec sheet (plan 4.20, owner 2026-11-06). Per product
// category: which specification row shows which configurator step. A row's values are split on
// ", " and each value that is one of the step's option labels is tagged with "<step>:<code>";
// a "whole" row is tagged with every code of the step. The product page highlights the tags of
// the options the visitor picked. Categories without rules get no tags.
const HIGHLIGHT_RULES = {
    'Extrusion Kit': [
        { spec: 'Lenses', step_type: 'Lens Appearance' },
        { spec: 'Mounting', step_type: 'Mounting Method' },
        { spec: 'Finish', step_type: 'Finish' },
        { spec: 'Stock Length', step_type: 'Length', whole: true },
    ],
};
const parseValues = opt => {
    if (Array.isArray(opt.allowed_values)) return opt.allowed_values;
    try { const v = JSON.parse(opt.allowed_values_json || '[]'); return Array.isArray(v) ? v : []; } catch (e) { return []; }
};
erpData.spec_highlights = {};
(HIGHLIGHT_RULES[erpData.product_type] || []).forEach(rule => {
    const step = (erpData.configurator_options || []).find(o => o.option_type === rule.step_type);
    if (!step) return;
    const values = parseValues(step).filter(v => v.code || v.value);
    const token = v => step.option_step + ':' + String(v.code || v.value).trim();
    erpData.spec_highlights[rule.spec] = rule.whole
        ? { whole: values.map(token).join(' ') }
        : { byLabel: Object.fromEntries(values.filter(v => v.label).map(v => [String(v.label).trim().toLowerCase(), token(v)])) };
});

// 4. Inject global window.ERP_DATA object into head + Spacing CSS
const dataScript = `
<style>
    /* Force hide any hardcoded cookie banners just in case */
    [id*="termly"], [class*="termly"], #cookie-banner, .cookie-consent { display: none !important; }
    /* Force spacing between pages for clean PDF rendering */
    .page-wrapper { margin-bottom: 40px !important; page-break-after: always; }

  .w-webflow-badge { display: none !important; visibility: hidden !important; }
</style>
<script>
new MutationObserver(() => document.querySelectorAll('.w-webflow-badge').forEach(el => el.remove()))
    .observe(document.documentElement, {childList: true, subtree: true});
    window.ERP_DATA = ${JSON.stringify(erpData).replace(/</g, '\\u003c')};
<\/script>`;

// 5. Client-side mapping & pagination script
const mappingScript = `<script>
  (function populateSpecSheet() {
      const data = window.ERP_DATA;
      if (!data) return;

      function setText(id, value) {
          const el = document.getElementById(id);
          if (el && value != null && value !== '') el.innerText = value;
      }
      
      function setImg(id, url) {
          const el = document.getElementById(id);
          if (el && url) el.src = url;
      }

      // --- A. CORE HEADERS & INFO ---
      setText('product-name', data.product_name);
      setText('sublabel', data.sublabel);

      // --- B. IMAGES ---
      setImg('feat-img', data.featured_image);
      setImg('spec-dims-img', data.dimensions_image_dark);

      // --- C. DYNAMIC SPECIFICATIONS GRID ---
      const specSection = document.getElementById('specifications');
      if (specSection && Array.isArray(data.specifications)) {
          const masterSpecItem = specSection.querySelector('#spec-data-item');
          if (masterSpecItem) {
              masterSpecItem.style.display = 'none';
              
              const filteredSpecs = data.specifications
                  .filter(spec => spec.spec_label !== "Output Options" && spec.spec_label !== "Certifications & Ratings")
                  .sort((a, b) => (a.display_order || 0) - (b.display_order || 0));

              Array.from(specSection.children).forEach(child => {
                  if (child.id === 'spec-data-item' && child !== masterSpecItem) child.remove();
              });

              filteredSpecs.forEach(spec => {
                  if (spec.spec_value) {
                      const itemClone = masterSpecItem.cloneNode(true);
                      itemClone.style.display = '';
                      itemClone.removeAttribute('id');

                      const titleEl = itemClone.querySelector('#spec-data-title');
                      const valueEl = itemClone.querySelector('#spec-data-value');

                      if (titleEl) titleEl.innerText = spec.spec_label;
                      if (valueEl) {
                          let finalValue = spec.spec_value;
                          if (spec.spec_unit) finalValue += " " + spec.spec_unit;
                          valueEl.innerText = finalValue;
                          // Configured spec sheet highlights (plan 4.20): tag the values tied to
                          // configurator options; the PDF generator stores their positions.
                          const rule = (data.spec_highlights || {})[spec.spec_label];
                          const tagged = (text, tokens) => {
                              const span = document.createElement('span');
                              span.style.display = 'inline-block';
                              span.textContent = text;
                              if (tokens) span.setAttribute('data-highlight', tokens);
                              return span;
                          };
                          if (rule && rule.whole) {
                              valueEl.textContent = '';
                              valueEl.appendChild(tagged(finalValue, rule.whole));
                          } else if (rule && rule.byLabel) {
                              valueEl.textContent = '';
                              String(finalValue).split(', ').forEach((part, i) => {
                                  if (i) valueEl.appendChild(document.createTextNode(', '));
                                  valueEl.appendChild(tagged(part, rule.byLabel[part.trim().toLowerCase()]));
                              });
                          }
                      }
                      
                      specSection.appendChild(itemClone);
                  }
              });
              
              const activeRows = specSection.querySelectorAll('.spec-data-item:not([style*="display: none"])');
              if (activeRows.length > 0) activeRows[activeRows.length - 1].classList.add('last-row');
          }
      }
      
      // --- D. PART NUMBER BUILDER ---
      const builderSection = document.getElementById('part-no-builder');
      if (builderSection && Array.isArray(data.configurator_options) && data.configurator_options.length > 0) {
          
          // 1. Setup Fixed Series Block
          const seriesSlug = (data.product_slug || "").toUpperCase();
          const seriesCodes = builderSection.querySelectorAll('#series-code');
          seriesCodes.forEach(el => el.innerText = seriesSlug);
          setText('series-desc', "ilLumenate " + (data.product_name || ""));
          
          // TAG THE SERIES BUTTON FOR VERCEL
          const seriesBtn = builderSection.querySelector('#series-btn');
          if (seriesBtn) {
              seriesBtn.setAttribute('data-step', '0');
              seriesBtn.setAttribute('data-code', seriesSlug);
          }
          
          // 2. Setup Dynamic Option Blocks
          const wrapper = builderSection.querySelector('.part-no-wrapper');
          if (wrapper) {
              const dashTemplate = wrapper.querySelector('.part-no-dash');
              const sectionTemplate = wrapper.querySelector('.part-no-section');
              
              if (dashTemplate && sectionTemplate) {
                  dashTemplate.style.display = 'none';
                  sectionTemplate.style.display = 'none';
                  
                  // Clear placeholder dynamic sections
                  Array.from(wrapper.children).forEach(child => {
                      if (!child.classList.contains('part-1-wrapper') && child !== dashTemplate && child !== sectionTemplate) {
                          child.remove();
                      }
                  });

                  const sortedConfig = data.configurator_options.sort((a, b) => a.option_step - b.option_step);

                  sortedConfig.forEach(opt => {
                      let currentValues = [];
                      try {
                          currentValues = JSON.parse(opt.allowed_values_json || "[]");
                      } catch(e) {}
                      
                      if (currentValues.length > 0) {
                          // Inject Dash separator
                          const dashClone = dashTemplate.cloneNode(true);
                          dashClone.style.display = '';
                          wrapper.appendChild(dashClone);
                          
                          // Inject Option Section
                          const sectionClone = sectionTemplate.cloneNode(true);
                          sectionClone.style.display = '';
                          
                          const titleEl = sectionClone.querySelector('#part-no-title');
                          if (titleEl) titleEl.innerText = (opt.option_label || opt.option_type).toUpperCase();
                          
                          const inputEl = sectionClone.querySelector('#part-no-code-input');
                          if (inputEl) inputEl.innerHTML = ''; // Empty out placeholder
                          
                          const optionsWrapper = sectionClone.querySelector('.part-no-options-wrapper');
                          const optTemplate = sectionClone.querySelector('#part-no-options');
                          
                          if (optionsWrapper && optTemplate) {
                              optTemplate.style.display = 'none';
                              
                              Array.from(optionsWrapper.children).forEach(child => {
                                  if (child !== optTemplate) child.remove();
                              });
                              
                              currentValues.forEach(valObj => {
                                  if (valObj.code || valObj.label || valObj.value) {
                                      const optClone = optTemplate.cloneNode(true);
                                      optClone.style.display = '';
                                      optClone.removeAttribute('id');
                                      
                                      // TAG THE DYNAMIC BUTTONS FOR VERCEL
                                      optClone.setAttribute('data-step', opt.option_step);
                                      optClone.setAttribute('data-code', valObj.code || valObj.value);
                                      
                                      const codeEl = optClone.querySelector('#part-no-code');
                                      const descEl = optClone.querySelector('#part-no-desc');
                                      
                                      if (codeEl) codeEl.innerText = valObj.code || '';
                                      if (descEl) descEl.innerText = valObj.label || valObj.value || '';
                                      
                                      optionsWrapper.appendChild(optClone);
                                  }
                              });
                          }
                          wrapper.appendChild(sectionClone);
                      }
                  });
              }
          }
      } else if (builderSection) {
          builderSection.style.display = 'none';
      }

      // --- E. EXTRUSION KIT COMPONENTS ---
      const compSection = document.getElementById('components');
      if (compSection && Array.isArray(data.kit_components) && data.kit_components.length > 0) {
          
          let listWrapper = compSection.querySelector('.component-list-wrapper') || compSection.querySelector('.div-12') || compSection;
          const masterGroup = compSection.querySelector('#component-wrapper');
          
          if (masterGroup) {
              masterGroup.style.display = 'none';
              
              Array.from(listWrapper.children).forEach(child => {
                  if (child.id === 'component-wrapper' && child !== masterGroup) child.remove();
              });

              data.kit_components.forEach(group => {
                  let parsedRows = [];
                  try {
                      parsedRows = JSON.parse(group.component_description || "[]");
                  } catch(e) {}
                  
                  if (parsedRows.length > 0) {
                      const groupClone = masterGroup.cloneNode(true);
                      groupClone.style.display = '';
                      groupClone.removeAttribute('id');
                      
                      const titleEl = groupClone.querySelector('#component-title');
                      if (titleEl) titleEl.innerText = group.component_type;
                      
                      let heroUrl = null;
                      if (parsedRows[0] && parsedRows[0].hero_image) {
                          heroUrl = parsedRows.shift().hero_image;
                      }
                      
                      const imgEl = groupClone.querySelector('#component-img');
                      if (imgEl && heroUrl) {
                          imgEl.src = heroUrl;
                      } else if (imgEl) {
                          imgEl.style.display = 'none';
                      }

                      // Deduplicate and reformat Endcap Sets
                      if (group.component_type === 'Endcap Set' || group.component_type === 'Endcaps') {
                          const uniqueEndcaps = new Map();
                          parsedRows.forEach(row => {
                              if (row.code || row.label) {
                                  const cleanCode = (row.code || '').replace(/-NO$/i, '').replace(/-HO$/i, '');
                                  if (!uniqueEndcaps.has(cleanCode)) {
                                      uniqueEndcaps.set(cleanCode, { code: cleanCode, label: row.label });
                                  }
                              }
                          });
                          parsedRows = Array.from(uniqueEndcaps.values());
                      }

                      const rowsContainer = groupClone.querySelector('#comp-partno-wrap');
                      if (rowsContainer) {
                          const masterRow = rowsContainer.querySelector('#component-option');
                          if (masterRow) {
                              masterRow.style.display = 'none';
                              
                              Array.from(rowsContainer.children).forEach(child => {
                                  if (child !== masterRow) child.remove();
                              });

                              parsedRows.forEach(row => {
                                  if(row.code || row.label) {
                                      const rowClone = masterRow.cloneNode(true);
                                      rowClone.style.display = '';
                                      rowClone.removeAttribute('id');
                                      
                                      const codeEl = rowClone.querySelector('#comp-code');
                                      const descEl = rowClone.querySelector('#comp-desc');
                                      
                                      if (codeEl) codeEl.innerText = row.code;
                                      if (descEl) descEl.innerText = row.label;
                                      
                                      rowsContainer.appendChild(rowClone);
                                  }
                              });
                              
                              const activeOptions = rowsContainer.querySelectorAll('.component-option:not([style*="display: none"])');
                              if (activeOptions.length > 0) activeOptions[activeOptions.length - 1].classList.add('last-row');
                          }
                      }
                      
                      listWrapper.appendChild(groupClone);
                  }
              });
          }
      } else if (compSection) {
          compSection.style.display = 'none';
      }

      // --- E2. CERTIFICATION BADGES (one .cert-icon per template certification) ---
      // The first .cert-icon is the pattern: it is copied once per certification that has a
      // badge (the template's Badge Image), then hidden. No badges: it stays hidden.
      const certTemplate = document.querySelector('.cert-icon');
      if (certTemplate) {
          const badges = (Array.isArray(data.certifications) ? data.certifications : [])
              .map(c => c.certification_details && c.certification_details.badge_image)
              .filter(Boolean);
          document.querySelectorAll('.cert-icon').forEach(el => { if (el !== certTemplate) el.remove(); });
          let anchor = certTemplate;
          badges.forEach(url => {
              const icon = certTemplate.cloneNode(true);
              icon.style.display = '';
              icon.removeAttribute('id');
              const img = icon.tagName === 'IMG' ? icon : icon.querySelector('img');
              if (img) { img.src = url; img.removeAttribute('srcset'); img.removeAttribute('loading'); }
              anchor.parentNode.insertBefore(icon, anchor.nextSibling);
              anchor = icon;
          });
          certTemplate.style.display = 'none';
      }

      // --- E3. EXTRA DIMENSION IMAGES (Spec Gallery, section "Dimensions") ---
      // The first .dimension-item keeps dimensions_image (#spec-dims-img). #dimension-item is the
      // pattern for the extra ones: copied once per Dimensions row (title in #dimension-title,
      // hidden when empty; image in #spec-dims-img-other), then hidden. No rows: stays hidden.
      const dimTemplate = document.getElementById('dimension-item');
      if (dimTemplate) {
          const rows = (Array.isArray(data.spec_gallery) ? data.spec_gallery : [])
              .filter(row => row.section === 'Dimensions' && row.image);
          let anchor = dimTemplate;
          rows.forEach(row => {
              const item = dimTemplate.cloneNode(true);
              item.style.display = '';
              item.removeAttribute('id');
              const titleEl = item.querySelector('#dimension-title');
              if (titleEl) {
                  titleEl.removeAttribute('id');
                  if (row.title) { titleEl.innerText = row.title; } else { titleEl.style.display = 'none'; }
              }
              const imgEl = item.querySelector('#spec-dims-img-other');
              if (imgEl) {
                  imgEl.removeAttribute('id');
                  imgEl.src = row.image;
                  imgEl.removeAttribute('srcset');
                  imgEl.removeAttribute('loading');
              }
              anchor.parentNode.insertBefore(item, anchor.nextSibling);
              anchor = item;
          });
          dimTemplate.style.display = 'none';
      }

      // --- F. GENERATED DATE (Strictly MMDDYY) ---
      const now = new Date();
      const mm = String(now.getMonth() + 1).padStart(2, '0');
      const dd = String(now.getDate()).padStart(2, '0');
      const yy = String(now.getFullYear()).slice(-2);
      
      // <TAG>.<MMDDYY> from ERPNext (tag of the stored file, Pacific date); the date alone if missing.
      setText('generated-date', data.spec_sheet_stamp || (mm + dd + yy));

      // --- G. PAGINATION LOGIC (1056px Max Height) ---
      const PAGE_HEIGHT = 1056; 
      const container = document.querySelector('.pdf-spec-container');
      let currentPage = document.querySelector('.page-wrapper');
      
      if (container && currentPage) {
          currentPage.style.height = 'auto';
          currentPage.style.minHeight = PAGE_HEIGHT + 'px';
          
          let currentMain = currentPage.querySelector('.spec-main-wrapper');
          const sections = Array.from(currentMain.children);
          
          currentMain.innerHTML = '';
          
          function addPage() {
              const newPage = currentPage.cloneNode(true);
              const newMain = newPage.querySelector('.spec-main-wrapper');
              newMain.innerHTML = ''; 
              container.appendChild(newPage);
              currentPage = newPage;
              currentMain = newMain;
          }

          sections.forEach(section => {
              if (section.id === 'components' && section.style.display !== 'none') {
                  addPage();
                  currentMain.appendChild(section);
                  return;
              }

              currentMain.appendChild(section);
              
              if (currentPage.scrollHeight > PAGE_HEIGHT) {
                  currentMain.removeChild(section); 
                  
                  let activeSection = section.cloneNode(false); 
                  currentMain.appendChild(activeSection);
                  
                  const items = Array.from(section.children);
                  items.forEach(item => {
                      activeSection.appendChild(item);
                      
                      if (currentPage.scrollHeight > PAGE_HEIGHT) {
                          activeSection.removeChild(item); 
                          addPage(); 
                          activeSection = section.cloneNode(false); 
                          currentMain.appendChild(activeSection);
                          activeSection.appendChild(item); 
                      }
                  });
              }
          });
          
          const allPages = document.querySelectorAll('.page-wrapper');
          allPages.forEach((page, idx) => {
              page.style.height = PAGE_HEIGHT + 'px';
              page.style.overflow = 'hidden';
              
              const curEl = page.querySelector('#current-page-no');
              const totEl = page.querySelector('#total-page-no');
              if (curEl) curEl.innerText = (idx + 1).toString();
              if (totEl) totEl.innerText = allPages.length.toString();
          });
      }

  })();
<\/script>`;

// 6. Build final HTML string
let finalHtml = html;
const headCloseIndex = finalHtml.indexOf('</head>');
if (headCloseIndex !== -1) {
    finalHtml = finalHtml.substring(0, headCloseIndex) + dataScript + finalHtml.substring(headCloseIndex);
}

const bodyCloseIndex = finalHtml.lastIndexOf('</body>');
if (bodyCloseIndex !== -1) {
    finalHtml = finalHtml.substring(0, bodyCloseIndex) + mappingScript + finalHtml.substring(bodyCloseIndex);
}

// 7. Output matching data structure!
return {
    json: {
        injected_html: finalHtml,
        product_slug: erpData.product_slug,
        // The generator reads allowed_values (parsed) for the default selections.
        configurator_options: (erpData.configurator_options || []).map(opt => ({ ...opt, allowed_values: parseValues(opt) })),
        template_doctype: resolved_template_doctype,
        template_name: resolved_template_name
    }
};
