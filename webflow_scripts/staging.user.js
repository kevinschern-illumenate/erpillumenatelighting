// ==UserScript==
// @name         ilLumenate staging product page scripts
// @namespace    https://illumenate.lighting/
// @version      2026.11.06.2
// @description  Main-site product page custom code, for testing on the staging Webflow site
// @match        https://staging-illumenate.webflow.io/products/*
// @run-at       document-start
// @grant        none
// Loaded by the page: https://cdn.jsdelivr.net/npm/@finsweet/attributes-cmsfilter@1/cmsfilter.js
// Loaded by the page: https://cdn.jsdelivr.net/npm/@finsweet/attributes-cmsload@1/cmsload.js
// Loaded by the page: https://cdn.jsdelivr.net/npm/swiper@11/swiper-bundle.min.js
// ==/UserScript==
// Built by webflow_scripts/build_userscript.py; edit the .html files, not this file.
// CMS data holders the page needs (Designer text elements bound to the field, hidden):
//   #raw-specs-data <- specifications-json
//   #raw-badges-data <- certifications-json
//   #raw-feature-data <- features-json
//   #config-data <- configurator-options-json
//   #feed-lengths-data <- feed-lengths-json
//   #cms-product-name <- name
//   #cms-series-code <- erp-sync-id
// Also read by the scripts (their holders are set up in the Designer, not in these files):
//   #downloads-container
//   #download-template
//   #empty-docs-message
//   #raw-documents-json
//   #raw-components-data
//   #config-cards-container
//   #config-nav-container
//   #product-json-data
//   #dynamic-sliders-container
//   #compatible-products-json
//   #pdp-category-name
//   #fixture-length-note
//   #ill-download-spec-sheet

// ---- Ignore the old copies of these scripts in the page's Code Embeds ----
window.__illStaging = {own: true, signatures: ['raw-specs-data', 'raw-feature-data', 'raw-components-data', 'raw-documents-json', 'config-cards-container', 'product-json-data', 'compatible-products-json', 'pdp-star-dot', 'ill-download-spec-sheet', 'spec-modal-wrapper'], ignored: 0};
(function () {
  const state = window.__illStaging;
  const isOld = fn => !state.own && typeof fn === 'function'
    && state.signatures.some(name => Function.prototype.toString.call(fn).includes(name));
  const add = EventTarget.prototype.addEventListener;
  EventTarget.prototype.addEventListener = function (type, fn, options) {
    if ((this === document || this === window) && isOld(fn)) { state.ignored += 1; return; }
    return add.call(this, type, fn, options);
  };
  const queue = window.fsAttributes = window.fsAttributes || [];
  const push = queue.push;
  queue.push = function (...items) {
    const kept = items.filter(item => !(Array.isArray(item) && isOld(item[1])));
    state.ignored += items.length - kept.length;
    return push.apply(this, kept);
  };
})();

(function () {
  const addStyles = () => {
    const l0 = document.createElement('link'); l0.rel = 'stylesheet'; l0.href = 'https://cdn.jsdelivr.net/npm/swiper@11/swiper-bundle.min.css'; document.head.appendChild(l0);
    const style = document.createElement('style');
    style.textContent = `
  /* --- 1. SLIDER RESET & EQUAL HEIGHTS --- */
  .w-slider-mask {
    display: flex !important;
    align-items: stretch !important;
    overflow: visible !important;
  }

  .w-slide {
    height: auto !important;
    display: flex !important;
    flex: 0 0 100% !important;
    width: 100% !important;
    white-space: normal !important;
  }

  .Part-No-Card {
    flex: 1 0 auto !important;
    display: flex !important;
    flex-direction: column !important;
    width: 100%;
  }

  .options-container {
    flex-grow: 1;
  }

  /* --- 2. CARD STYLING (Updated Variables) --- */

  /* Layout */
  .radio-card-row {
    display: flex;
    align-items: flex-start; /* Aligns checkbox with top of text line */
    cursor: pointer;
    width: 100%;
    /* Updated Padding */
    padding: 0px 0 !important;
    /* Removed Border */
    border-bottom: none !important;
  }

  .real-radio-input {
    position: absolute;
    opacity: 0;
    cursor: pointer;
    height: 0;
    width: 0;
  }

 /* Square Styling (Redesigned & Color Updated) */
  .custom-square {
    height: 15px !important;
    width: 15px !important;
    background-color: transparent;
    border: 1px solid #FFFFFF; /* Default Unselected White */
    border-radius: 3px;
    margin-right: 15px !important;
    margin-top: 3px !important;
    flex-shrink: 0;
    transition: all 0.2s ease;
    position: relative;
    display: block;
  }

  /* Concentric Inner Square Design */
  .custom-square::before {
    content: '';
    display: block;
    position: absolute;
    height: 9px;
    width: 9px;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    border-radius: 2px;
    background-color: transparent;
    transition: all 0.2s ease;
  }

  /* Applies variable color when clicked natively OR forced by single option */
  .real-radio-input:checked ~ .custom-square,
  .custom-square.single-checked {
    border-color: var(--_colors---accent-20) !important;
  }

  /* Fills in the inner square when clicked natively OR forced by single option */
  .real-radio-input:checked ~ .custom-square::before,
  .custom-square.single-checked::before {
    background-color: var(--_colors---accent-20) !important;
  }

  /* Text Layout */
  .text-container { display: flex; flex-direction: column; width: 100%; }
  .top-row { display: flex; justify-content: space-between; align-items: center; width: 100%; }

  /* Name Font (Linked to Global Variables) */
  .radio-name {
    font-family: var(--_fonts---body-font) !important;
    font-weight: var(--body-weight) !important;
    font-size: var(--body) !important;
    line-height: var(--body-line-height) !important;
    color: #FFFFFF;
  }

  /* Price/Specs Font (Optional support for extra data) */
  .radio-price, .radio-specs {
    font-family: var(--_fonts---body-font) !important;
    font-size: 14px !important;
    color: #FFFFFF;
    opacity: 0.6;
  }
  .radio-specs:empty { display: none; }

  /* --- 3. LOGIC STATES --- */
  .Part-No-Card.is-locked {
    pointer-events: none !important;
    opacity: 0.4 !important;
    filter: grayscale(1) !important;
  }

  .output-embed { display: none !important; }
  .output-embed.is-active { display: block !important; }
  .lens-hint { display: flex; align-items: center; color: #ffcc00; font-size: 14px; padding: 10px 0; }

  /* --- 4. NAVIGATION --- */
  .category-link { cursor: pointer; transition: all 0.2s ease; opacity: 0.6; }
  .category-link.current { color: #ffffff !important; opacity: 1; }


  /* 1. Force the Sub Menu to Stick */
  .pdp-sub-menu-wrap {
      position: -webkit-sticky !important; /* Safari support */
      position: sticky !important;
      top: 0px !important;
      z-index: 9999 !important; /* Ensure it stays above other content */
  }

  /* 2. The Magic Bullet: Fix the global overflow bug */
  /* This targets the parents to ensure they don't 'clip' the sticky child */
  html, body {
      overflow: visible !important;
      overflow-x: clip !important;
  }


  /* --- CONFIGURATOR TOOLTIP & ARROWS --- */
/* 1. Hide the native scrollbar but keep it scrollable */
  .configure-slider::-webkit-scrollbar {
      display: none !important;
  }
  .configure-slider {
      -ms-overflow-style: none !important;  /* IE and Edge */
      scrollbar-width: none !important;  /* Firefox */
  }

  /* Hide the scrollbar but keep the physics */
.related-scroll-container {
    -ms-overflow-style: none !important;  /* IE and Edge */
    scrollbar-width: none !important;  /* Firefox */
}
.related-scroll-container::-webkit-scrollbar {
    display: none !important; /* Chrome, Safari and Opera */
}


  /* --- ANIMATION FOR COPY CODE BUTTON --- */
  @keyframes slideUpFade {
    0% { transform: translateY(10px); opacity: 0; }
    100% { transform: translateY(0); opacity: 1; }
  }


  @keyframes slideUpFade {
    0% { transform: translateY(10px); opacity: 0; }
    100% { transform: translateY(0); opacity: 1; }
  }


  .swiper-button-disabled {
      display: none !important;
  }
`;
    document.head.appendChild(style);
  };
  if (document.head) addStyles(); else document.addEventListener('DOMContentLoaded', addStyles);
})();

// ---- specifications-json.html ----
document.addEventListener('DOMContentLoaded', function() {

  (function() {
    const rawSpecsEl = document.getElementById('raw-specs-data');
    const rawBadgesEl = document.getElementById('raw-badges-data');

    const specsContainer = document.querySelector('.specs-grid');
    const specTemplate = document.querySelector('.spec-item-template');

    if (specsContainer && specTemplate) {
        specTemplate.style.display = 'none';
    } else {
        return;
    }

    // ==========================================
    // PART A: GENERATE STANDARD TEXT SPECS
    // ==========================================
    if (rawSpecsEl) {
        const rawSpecsText = rawSpecsEl.innerText.trim();

        if (rawSpecsText && rawSpecsText !== "[]") {
            try {
                const specsData = JSON.parse(rawSpecsText);

                specsData.forEach((spec, index) => {
                    try {
                        // Added fallback keys (value, label) just in case the CMS structure changed
                        const rawValue = spec.spec_value || spec.value;
                        const rawLabel = spec.spec_label || spec.label || spec.name;

                        const cleanValue = (rawValue !== null && rawValue !== undefined) ? String(rawValue).trim() : '';

                        // Skip rendering if value is completely blank or "N/A"
                        if (cleanValue === '' || cleanValue.toUpperCase() === 'N/A') {
                            return;
                        }

                        const upperTitle = (rawLabel || '').toUpperCase();

                        // Ignore the old text-based certification rows so they don't duplicate
                        if (upperTitle.includes('CERTIFICATIONS') || upperTitle === 'STANDARDS') return;

                        // Clone the template
                        const newItem = specTemplate.cloneNode(true);
                        newItem.style.display = 'block';

                        const titleEl = newItem.querySelector('.spec-data-title');
                        const bodyEl = newItem.querySelector('.spec-value');

                        if (titleEl) titleEl.innerText = rawLabel || '';

                        if (bodyEl) {
                            const safeUnit = spec.spec_unit || spec.unit ? String(spec.spec_unit || spec.unit).trim() : '';
                            const unitString = safeUnit ? ` ${safeUnit}` : '';
                            bodyEl.innerText = cleanValue + unitString;
                        }

                        specsContainer.appendChild(newItem);

                    } catch (innerError) {
                        console.error("Error generating text spec item:", spec, innerError);
                    }
                });
            } catch (error) {
                console.error("Error parsing specifications JSON. Is it valid JSON?", error);
            }
        }
    }

    // ==========================================
    // PART B: GENERATE BADGES STRICTLY FROM BADGES JSON
    // ==========================================
    if (rawBadgesEl) {
        const rawBadgesText = rawBadgesEl.innerText.trim();
        if (rawBadgesText && rawBadgesText !== "[]") {
            try {
                const badgesData = JSON.parse(rawBadgesText);

                if (badgesData && badgesData.length > 0) {
                    const badgeCard = specTemplate.cloneNode(true);
                    badgeCard.style.display = 'block';

                    const titleEl = badgeCard.querySelector('.spec-data-title');
                    const bodyEl = badgeCard.querySelector('.spec-value');

                    if (titleEl) titleEl.innerText = 'Certifications & Ratings';

                    if (bodyEl) {
                        bodyEl.innerHTML = '';
                        bodyEl.style.display = 'flex';
                        bodyEl.style.flexWrap = 'wrap';
                        bodyEl.style.alignItems = 'center';
                        bodyEl.style.gap = 'var(--button-t-b-padding)';

                        // Since 2026-11-06: [{certification, certification_code, badge_image, order}];
                        // the old keys (badge, name, code) are still read.
                        badgesData.slice().sort((a, b) => (a.order || 0) - (b.order || 0)).forEach(badge => {
                            const badgeSrc = badge.badge_image || badge.badge;
                            const badgeName = badge.certification || badge.name || badge.certification_code || badge.code || 'Certification Badge';
                            if (badgeSrc) {
                                const imgEl = document.createElement('img');
                                imgEl.src = badgeSrc;
                                imgEl.alt = badgeName;
                                imgEl.title = badgeName;
                                imgEl.style.height = 'var(--small-icons)';
                                bodyEl.appendChild(imgEl);
                            }
                        });
                    }
                    specsContainer.appendChild(badgeCard);
                }
            } catch (error) {
                console.error("Error parsing Certifications JSON:", error);
            }
        }
    }

    // Finally, remove the original template
    specTemplate.remove();

  })();

});

// ---- features-json.html ----
document.addEventListener('DOMContentLoaded', function() {

  // --- FEATURES LIST GENERATOR ---
  (function() {
    const rawDataEl = document.getElementById('raw-feature-data');
    if (!rawDataEl) return;
    const rawText = rawDataEl.innerText.trim();
    if (!rawText) return;

    const gridContainer = document.querySelector('.features-grid');
    const templateCard = document.querySelector('.feature-card-template');
    if (!gridContainer || !templateCard) return;

    templateCard.style.display = 'none';

    try {
        const featuresData = JSON.parse(rawText);
        featuresData.forEach(feature => {
            // Skip if both title and description are empty
            if (!feature.title && !feature.description) return;

            const newCard = templateCard.cloneNode(true);
            newCard.style.display = 'flex';

            const titleEl = newCard.querySelector('.feature-card-title');
            const bodyEl = newCard.querySelector('.feature-card-body');

            // Inject the data
            if (titleEl) titleEl.innerText = feature.title || '';
            if (bodyEl) bodyEl.innerText = feature.description || '';

            gridContainer.appendChild(newCard);
        });

        // Clean up the original template
        templateCard.remove();

    } catch (error) {
        console.error("Error parsing Features JSON:", error);
    }
  })();

});

// ---- documents-json.html ----
(function() {
  const buildDownloadCards = () => {
    const container = document.getElementById('downloads-container');
    const template = document.getElementById('download-template');
    const emptyMessage = document.getElementById('empty-docs-message');

    if (template) template.style.display = 'none';

    const dataField = document.getElementById('raw-documents-json');

    if (!container || !template) {
      return;
    }

    if (!dataField) {
      if (emptyMessage) emptyMessage.style.setProperty('display', 'block', 'important');
      return;
    }

    let rawText = dataField.textContent || dataField.innerText || "";
    let jsonText = rawText.trim().replace(/[\u2018\u2019]/g, "'").replace(/[\u201C\u201D]/g, '"');

    if (jsonText.includes('(function')) {
        jsonText = jsonText.split('(function')[0].trim();
    }

    if (!jsonText || jsonText === "[]" || jsonText === "") {
      if (emptyMessage) emptyMessage.style.setProperty('display', 'block', 'important');
      return;
    }

    try {
      const documents = JSON.parse(jsonText);

      if (!Array.isArray(documents) || documents.length === 0) {
        if (emptyMessage) emptyMessage.style.setProperty('display', 'block', 'important');
        return;
      }

      const filteredDocuments = documents.filter(doc => {
          if (!doc.document_type) return true;
          return !String(doc.document_type).toLowerCase().includes('spec submittal');
      });

      if (filteredDocuments.length === 0) {
        if (emptyMessage) emptyMessage.style.setProperty('display', 'block', 'important');
        return;
      }

      if (emptyMessage) emptyMessage.style.setProperty('display', 'none', 'important');

      filteredDocuments.sort((a, b) => (a.display_order || 0) - (b.display_order || 0));

      filteredDocuments.forEach(doc => {
        const clone = template.cloneNode(true);
        clone.removeAttribute('id');
        clone.style.display = 'flex';

        const typeEl = clone.querySelector('.doc-type, #doc-type');
        const titleEl = clone.querySelector('.doc-title, #doc-title');

        if (typeEl && doc.document_type) {
          typeEl.innerText = String(doc.document_type).toUpperCase() + "(S)";
        }
        if (titleEl && doc.document_title) {
          titleEl.innerText = doc.document_title;
        }

        const actionButton = clone.querySelector('.reg-spec-download, #reg-spec-download');

        if (clone.tagName === 'A' && clone.classList.contains('reg-spec-download')) {
           clone.href = doc.document_file || '#';
           clone.target = '_blank';
        } else if (actionButton) {
           actionButton.href = doc.document_file || '#';
           actionButton.target = '_blank';
           actionButton.removeAttribute('id');
        }

        container.appendChild(clone);
      });

      template.remove();

    } catch (error) {
      if (emptyMessage) emptyMessage.style.setProperty('display', 'block', 'important');
    }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', buildDownloadCards);
  } else {
    buildDownloadCards();
  }
})();

// ---- kit-components-json.html ----
document.addEventListener('DOMContentLoaded', function() {

  (function() {
    const rawDataEl = document.getElementById('raw-components-data');
    if (!rawDataEl) return;

    const rawText = rawDataEl.innerText.trim();
    if (!rawText || rawText === "[]") return;

    const template = document.querySelector('.component-template');
    if (!template) return;

    const container = template.parentNode;
    container.style.display = 'flex';
    container.style.flexWrap = 'wrap';
    container.style.gap = '25px';

    template.style.display = 'none';

    try {
        const componentsData = JSON.parse(rawText);

        componentsData.forEach(comp => {
            const clone = template.cloneNode(true);
            clone.style.display = '';

            const titleEl = clone.querySelector('.component-title');
            const heroEl = clone.querySelector('.component-hero');
            const descEl = clone.querySelector('.component-desc');

            if (titleEl) {
                titleEl.innerText = comp.component_type || 'Component';
            }

            let parsedDetails = [];
            let heroImageStr = '';

            // component_description since the template-first sync (2026-11-06); the old key is
            // still read until the main site is moved over.
            const detailsJson = comp.component_description || comp.custom_webflow_description;
            if (detailsJson) {
                try {
                    parsedDetails = JSON.parse(detailsJson);
                } catch (e) {
                    console.error("Error parsing component_description", e);
                }
            }

            // NEW: Set up variables for Deduplication and Endcap checking
            const optionsData = [];
            const seenCodes = new Set();
            const isEndcap = comp.component_type && comp.component_type.toLowerCase().includes('endcap');

            parsedDetails.forEach(item => {
                if (item.hero_image) {
                    heroImageStr = item.hero_image;
                }

                if (item.code && item.label) {
                    let finalCode = item.code;

                    // 1. Strip -NO and -HO from the end of the code string if it's an Endcap
                    if (isEndcap) {
                        finalCode = finalCode.replace(/-NO$/i, '').replace(/-HO$/i, '');
                    }

                    // 2. Only push to the list if this exact code hasn't been added yet
                    if (!seenCodes.has(finalCode)) {
                        seenCodes.add(finalCode);
                        optionsData.push({
                            code: finalCode,
                            label: item.label
                        });
                    }
                }
            });

            if (descEl) {
                if (optionsData.length > 0) {
                    descEl.innerHTML = '';

                    optionsData.forEach(opt => {
                        const row = document.createElement('div');
                        row.style.marginBottom = '4px';
                        row.innerHTML = `<strong>${opt.code}</strong> &mdash; ${opt.label}`;
                        descEl.appendChild(row);
                    });

                    descEl.style.display = '';
                } else {
                    descEl.style.display = 'none';
                }
            }

            if (heroEl) {
                if (heroImageStr) {
                    if (heroEl.tagName === 'IMG') {
                        heroEl.src = heroImageStr;
                        heroEl.alt = comp.component_type || 'Component Image';
                    } else {
                        heroEl.style.backgroundImage = `url('${heroImageStr}')`;
                        heroEl.style.backgroundSize = 'cover';
                        heroEl.style.backgroundPosition = 'center';
                    }
                } else {
                    heroEl.style.display = 'none';
                }
            }

            container.appendChild(clone);
        });

        template.remove();

    } catch (error) {
        console.error("Error parsing Kit Components JSON:", error);
    }
  })();

});

// ---- configurator-options-json.html ----
document.addEventListener("DOMContentLoaded", () => {

  // ==========================================
  // --- 1. DATA EXTRACTION & PARSING ---
  // ==========================================
  const configDataEl = document.getElementById('config-data');
  if (!configDataEl) {
      return;
  }

  let rawData = configDataEl.innerHTML;
  const decodeEl = document.createElement("textarea");
  decodeEl.innerHTML = rawData;
  rawData = decodeEl.value
      .replace(/(<([^>]+)>)/gi, "")
      .replace(/[\u2018\u2019]/g, "'")
      .replace(/[\u201C\u201D]/g, '"')
      .replace(/[\u200B-\u200D\uFEFF]/g, '')
      .trim();

  let configuratorData = [];
  try {
    const parsedRaw = JSON.parse(rawData);

    // THE FIX: Map the new JSON keys to the old keys the script expects
    configuratorData = parsedRaw.map(item => {
      let step = {
          step: item.option_step !== undefined ? item.option_step : item.step,
          label: item.option_label !== undefined ? item.option_label : item.label,
          type: item.option_type !== undefined ? item.option_type : item.type,
          required: item.is_required !== undefined ? item.is_required : item.required,
          dependsOn: item.depends_on_step !== undefined ? item.depends_on_step : item.dependsOn,
          allowedValues: item.allowed_values_json !== undefined ? item.allowed_values_json : item.allowedValues
      };

      let vals = step.allowedValues;
      let parseAttempts = 0;
      while (typeof vals === 'string' && parseAttempts < 3) {
          try { vals = JSON.parse(vals); } catch(e) { break; }
          parseAttempts++;
      }
      step.allowedValues = vals;
      return step;
    });
  } catch (error) {
    console.error("Configurator JSON Parsing Error:", error);
    return;
  }

  const feedDataEl = document.getElementById('feed-lengths-data');
  if (feedDataEl) {
      let rawFeedData = feedDataEl.innerHTML;
      const feedDecodeEl = document.createElement("textarea");
      feedDecodeEl.innerHTML = rawFeedData;
      rawFeedData = feedDecodeEl.value.replace(/(<([^>]+)>)/gi, "").replace(/[\u2018\u2019]/g, "'").replace(/[\u201C\u201D]/g, '"').trim();

      if (rawFeedData) {
          try {
              const parsedFeedData = JSON.parse(rawFeedData);
              const feedSteps = {};

              parsedFeedData.forEach(item => {
                  if (!feedSteps[item.step]) {
                      feedSteps[item.step] = {
                          step: item.step,
                          type: item.stepType,
                          label: item.stepLabel,
                          description: item.stepDescription,
                          required: item.stepRequired ? 1 : 0,
                          dependsOn: item.stepDependsOn,
                          allowedValues: []
                      };
                  }
                  feedSteps[item.step].allowedValues.push({ code: item.code, label: item.label, value: item.label });
              });

              Object.values(feedSteps).forEach(newStepObj => {
                  const existingIndex = configuratorData.findIndex(c => c.step === newStepObj.step);
                  if (existingIndex > -1) { configuratorData[existingIndex] = newStepObj; }
                  else { configuratorData.push(newStepObj); }
              });

              configuratorData.sort((a, b) => a.step - b.step);
          } catch (error) {
              console.error("Feed Length JSON Error:", error);
          }
      }
  }

  // ==========================================
  // --- 2. UI SETUP & BUILDING ---
  // ==========================================
  const requiredTemplate = document.querySelector('#config-cards-container .cp-card-template:not(.optional)');
  const optionalTemplate = document.querySelector('#config-cards-container .cp-card-template.optional');
  const cardsContainer = document.getElementById('config-cards-container');
  const navContainer = document.getElementById('config-nav-container');

  if (!cardsContainer || !requiredTemplate) return;

  if (navContainer) navContainer.innerHTML = '';
  requiredTemplate.style.display = 'none';
  if (optionalTemplate) optionalTemplate.style.display = 'none';

  const productName = document.getElementById('cms-product-name').textContent.trim() || "Unknown Product";
  const seriesCode = (document.getElementById('cms-series-code').textContent.trim() || "XX").toUpperCase();

  const hasDynamicSeries = configuratorData.some(c => c.step === 0 && c.label && c.label.toLowerCase() === 'series');
  const hasLensStep = configuratorData.some(c => c.label && (c.label.toLowerCase() === 'lens' || c.label.toLowerCase() === 'lens appearance'));

  function buildSeriesCard() {
      if (hasDynamicSeries) return;

      const seriesCard = requiredTemplate.cloneNode(true);
      seriesCard.style.display = 'block';
      seriesCard.classList.add('config-card', 'active');
      seriesCard.classList.remove('optional');

      const titleEl = seriesCard.querySelector('.options-title');
      if (titleEl) titleEl.textContent = "Series";

      const codeEl = seriesCard.querySelector('.options-title.part-no');
      if (codeEl) codeEl.textContent = seriesCode;

      const nameEl = seriesCard.querySelector('.radio-name');
      if (nameEl) nameEl.textContent = productName;

      const inputEl = seriesCard.querySelector('.real-radio-input');
      if (inputEl) {
          inputEl.name = `step-0`;
          inputEl.value = seriesCode;
          inputEl.checked = true;
          const embedWrapper = inputEl.closest('.w-embed');
          if (embedWrapper) {
              embedWrapper.parentNode.insertBefore(inputEl, embedWrapper);
              embedWrapper.remove();
          }
      }

      seriesCard.setAttribute('data-step', '0');
      seriesCard.setAttribute('data-selected-code', seriesCode);
      cardsContainer.appendChild(seriesCard);

      if (navContainer) {
          const navItem = document.createElement('div');
          navItem.className = 'card-title selected';
          navItem.textContent = "Series";
          navItem.setAttribute('data-target-step', '0');
          navItem.style.cursor = 'pointer';
          navContainer.appendChild(navItem);
      }
  }

  function buildCategoryCards() {
    configuratorData.forEach(category => {
        if (category.step >= 98) return;

        const isOptional = (category.required == 0 || category.required === "0" || category.required === false);
        const template = (isOptional && optionalTemplate) ? optionalTemplate : requiredTemplate;
        if (!template) return;

        const cardClone = template.cloneNode(true);
        cardClone.style.display = 'block';
        cardClone.classList.add('config-card');
        if (isOptional) cardClone.classList.add('optional');
        else cardClone.classList.remove('optional');

        cardClone.setAttribute('data-step', category.step);
        cardClone.setAttribute('data-depends-on', category.dependsOn);

        const titleEl = cardClone.querySelector('.options-title');
        if (titleEl) titleEl.textContent = category.label;

        if (navContainer) {
            const navItem = document.createElement('div');
            navItem.className = isOptional ? 'card-title optional' : 'card-title';
            navItem.textContent = category.label;
            navItem.setAttribute('data-target-step', category.step);
            navItem.style.cursor = 'pointer';
            navContainer.appendChild(navItem);
        }

        const optionsContainer = cardClone.querySelector('.options-container');
        if (optionsContainer) {
            const radioTemplate = optionsContainer.querySelector('.radio-card-row');
            if (radioTemplate) {
                let safeValues = category.allowedValues;
                optionsContainer.innerHTML = '';

                const lowerLabel = category.label ? category.label.toLowerCase() : '';
                const lowerType = category.type ? category.type.toLowerCase() : '';

                let isDynamicLength = false;
                if (lowerLabel === 'length' || lowerType === 'length') {
                    isDynamicLength = true;
                    if (Array.isArray(safeValues) && safeValues.length > 0) {
                        if (safeValues[0].code && safeValues[0].code.trim() !== '') {
                            isDynamicLength = false;
                        }
                    }
                }

                if (isDynamicLength) {
                    const lengthData = (safeValues && safeValues[0]) ? safeValues[0] : { min_inches: 1, max_inches: 999, increment_inches: 1, default_inches: 100 };
                    optionsContainer.innerHTML = `
                        <div style="padding: 10px 0;">
                            <input type="number" class="custom-length-input" min="${lengthData.min_inches}" max="${lengthData.max_inches}" step="${lengthData.increment_inches}" placeholder="Ex: ${lengthData.default_inches}" style="width: 100%; padding: 10px; background: transparent; border: 1px solid rgba(255,255,255,0.3); color: #fff; border-radius: 15px; font-family: inherit;">
                            <div class="card-hint-text" style="margin-top: 8px; font-size: 12px; opacity: 0.7;">Min: ${lengthData.min_inches}" | Max: ${lengthData.max_inches}"</div>
                        </div>
                    `;
                }
                // option_type is no longer sent (2026-11-06), so the label decides too.
                else if (lowerLabel === 'output' || lowerLabel === 'output level' || lowerType === 'output level') {
                    if (safeValues && !Array.isArray(safeValues) && safeValues.lensMap) {
                        if (hasLensStep) {
                            optionsContainer.innerHTML = '<div class="card-hint-text">Select a lens option first.</div>';
                        } else {
                            const firstLensKey = Object.keys(safeValues.lensMap)[0];
                            const optionsToRender = safeValues.lensMap[firstLensKey];
                            if (optionsToRender && Array.isArray(optionsToRender)) {
                                optionsToRender.forEach(option => {
                                    const radioClone = radioTemplate.cloneNode(true);
                                    const nameEl = radioClone.querySelector('.radio-name');
                                    if (nameEl) nameEl.textContent = option.label;

                                    const inputEl = radioClone.querySelector('.real-radio-input');
                                    if (inputEl) {
                                        inputEl.name = `step-${category.step}`;
                                        inputEl.value = option.code;
                                        inputEl.setAttribute('data-label', option.label);
                                        const embedWrapper = inputEl.closest('.w-embed');
                                        if (embedWrapper) {
                                            embedWrapper.parentNode.insertBefore(inputEl, embedWrapper);
                                            embedWrapper.remove();
                                        }
                                    }
                                    optionsContainer.appendChild(radioClone);
                                });
                            }
                        }
                    }
                    else if (Array.isArray(safeValues)) {
                        safeValues.forEach(option => {
                            const radioClone = radioTemplate.cloneNode(true);
                            const nameEl = radioClone.querySelector('.radio-name');
                            if (nameEl) nameEl.textContent = option.label;

                            const inputEl = radioClone.querySelector('.real-radio-input');
                            if (inputEl) {
                                inputEl.name = `step-${category.step}`;
                                inputEl.value = option.code;
                                inputEl.setAttribute('data-label', option.label);
                                const embedWrapper = inputEl.closest('.w-embed');
                                if (embedWrapper) {
                                    embedWrapper.parentNode.insertBefore(inputEl, embedWrapper);
                                    embedWrapper.remove();
                                }
                            }
                            optionsContainer.appendChild(radioClone);
                        });
                    }
                }
                else if (Array.isArray(safeValues)) {
                    safeValues.forEach(option => {
                        const radioClone = radioTemplate.cloneNode(true);
                        const nameEl = radioClone.querySelector('.radio-name');
                        if (nameEl) nameEl.textContent = option.label;

                        const inputEl = radioClone.querySelector('.real-radio-input');
                        if (inputEl) {
                            inputEl.name = `step-${category.step}`;
                            inputEl.value = option.code;
                            inputEl.setAttribute('data-label', option.label);
                            const embedWrapper = inputEl.closest('.w-embed');
                            if (embedWrapper) {
                                embedWrapper.parentNode.insertBefore(inputEl, embedWrapper);
                                embedWrapper.remove();
                            }
                        }
                        optionsContainer.appendChild(radioClone);
                    });
                }
            }
        }
        cardsContainer.appendChild(cardClone);
    });
  }

  // ==========================================
  // --- 3. MASTER CODE UPDATER ---
  // ==========================================
  function updateMasterCode() {
      for (let i = 0; i <= 11; i++) {
          const card = document.querySelector(`.config-card[data-step="${i}"]`);
          const span = document.getElementById(`step-${i}-master-code`);

          if (span) {
              let isOptional = false;
              let isLengthStep = false;
              let stepExists = false;
              let omitDash = (i === 0);

              if (i === 0 && !hasDynamicSeries) {
                  stepExists = true;
              }

              const stepData = configuratorData.find(c => c.step === i);
              if (stepData) {
                  stepExists = true;
                  if (stepData.required == 0 || stepData.required === "0" || stepData.required === false) {
                      isOptional = true;
                  }
                  if ((stepData.label && stepData.label.toLowerCase() === 'length') ||
                      (stepData.type && stepData.type.toLowerCase() === 'length')) {
                      isLengthStep = true;
                  }

                  if (stepData.label) {
                      const lowerLabel = stepData.label.toLowerCase();
                      if (lowerLabel === 'start feed length' || lowerLabel === 'end feed length' || lowerLabel === 'series') {
                          omitDash = true;
                      }
                  }
              }

              if (!stepExists) {
                  span.style.display = 'none';
                  continue;
              } else {
                  span.style.display = 'inline-block';
              }

              if (isOptional) {
                  span.classList.add('optional-code');
                  span.classList.remove('required-code');
              } else {
                  span.classList.add('required-code');
                  span.classList.remove('optional-code');
              }

              let val = card ? card.getAttribute('data-selected-code') : null;

              if (i === 0 && !hasDynamicSeries) {
                  val = seriesCode;
              }

              if (!val) val = isLengthStep ? "XXX.XX" : "XX";

              if (omitDash) {
                  span.textContent = val;
              } else {
                  span.textContent = "-" + val;
              }
          }
      }
  }

  // ==========================================
  // --- 4. EVENT HANDLERS ---
  // ==========================================
  cardsContainer.addEventListener('click', (event) => {
    const row = event.target.closest('.radio-card-row');
    if (!row) return;

    const inputEl = row.querySelector('.real-radio-input');
    if (!inputEl) return;

    inputEl.checked = true;

    const card = row.closest('.config-card');
    const step = card.getAttribute('data-step');
    const selectedCode = inputEl.value;

    const cardCodeDisplay = card.querySelector('.options-title.part-no');
    if (cardCodeDisplay) cardCodeDisplay.textContent = selectedCode;

    card.setAttribute('data-selected-code', selectedCode);

    const cardStepData = configuratorData.find(c => c.step === parseInt(step));
    if (cardStepData && (cardStepData.label && (cardStepData.label.toLowerCase() === 'lens' || cardStepData.label.toLowerCase() === 'lens appearance'))) {
        const outputStepData = configuratorData.find(c => c.label && (c.label.toLowerCase() === 'output level' || c.label.toLowerCase() === 'output'));
        if (outputStepData && outputStepData.allowedValues) {
            let safeOutputVals = outputStepData.allowedValues;
            if (safeOutputVals && !Array.isArray(safeOutputVals) && safeOutputVals.lensMap) {
                const mappedOptions = safeOutputVals.lensMap[selectedCode];
                if (mappedOptions) {
                    const outputCard = document.querySelector(`.config-card[data-step="${outputStepData.step}"]`);
                    if(outputCard) {
                        const outputContainer = outputCard.querySelector('.options-container');
                        outputCard.removeAttribute('data-selected-code');
                        const outDisplay = outputCard.querySelector('.options-title.part-no');
                        if (outDisplay) outDisplay.textContent = "XX";

                        outputContainer.innerHTML = '';
                        const dummyRow = requiredTemplate.querySelector('.radio-card-row');
                        mappedOptions.forEach(option => {
                            const clone = dummyRow.cloneNode(true);
                            const nameEl = clone.querySelector('.radio-name');
                            if (nameEl) nameEl.textContent = option.label;

                            const newInput = clone.querySelector('.real-radio-input');
                            if (newInput) {
                                newInput.name = `step-${outputStepData.step}`;
                                newInput.value = option.code;
                                newInput.setAttribute('data-label', option.label);
                                const embedWrapper = newInput.closest('.w-embed');
                                if (embedWrapper) {
                                    embedWrapper.parentNode.insertBefore(newInput, embedWrapper);
                                    embedWrapper.remove();
                                }
                            }
                            outputContainer.appendChild(clone);
                        });
                    }
                }
            }
        }
    }
    updateMasterCode();
  });

  cardsContainer.addEventListener('input', (event) => {
    if (event.target.classList.contains('custom-length-input') && event.target.type !== 'hidden') {
        const inputEl = event.target;
        const card = inputEl.closest('.config-card');
        const val = inputEl.value;
        const cardCodeDisplay = card.querySelector('.options-title.part-no');
        if (cardCodeDisplay) cardCodeDisplay.textContent = val ? val : "XXX.XX";
        card.setAttribute('data-selected-code', val);
        updateMasterCode();
    }
  });

  function autoSelectSingleOptions() {
      for (let i = 0; i <= 11; i++) {
          const card = document.querySelector(`.config-card[data-step="${i}"]`);
          if (card) {
              const rows = card.querySelectorAll('.radio-card-row');
              if (rows.length === 1) {
                  rows[0].click();
              }
          }
      }
  }

  // ==========================================
  // --- 5. EXECUTION & NAVIGATION ---
  // ==========================================
  buildSeriesCard();
  buildCategoryCards();
  updateMasterCode();
  autoSelectSingleOptions();

  if (navContainer) {
      navContainer.addEventListener('click', (e) => {
          if (e.target.classList.contains('card-title')) {
              const step = e.target.getAttribute('data-target-step');
              const targetCard = document.querySelector(`.config-card[data-step="${step}"]`);
              if (targetCard && cardsContainer) {
                  const cardLeft = targetCard.getBoundingClientRect().left;
                  const containerLeft = cardsContainer.getBoundingClientRect().left;
                  const currentScroll = cardsContainer.scrollLeft;
                  cardsContainer.scrollTo({ left: currentScroll + (cardLeft - containerLeft), behavior: 'smooth' });
              }
          }
      });
  }

  if (navContainer && cardsContainer) {
      cardsContainer.addEventListener('scroll', () => {
          let closestCard = null;
          let minDistance = Infinity;
          const containerLeft = cardsContainer.getBoundingClientRect().left;

          cardsContainer.querySelectorAll('.config-card').forEach(card => {
              const distance = Math.abs(card.getBoundingClientRect().left - containerLeft);
              if (distance < minDistance) {
                  minDistance = distance;
                  closestCard = card;
              }
          });

          if (closestCard) {
              const step = closestCard.getAttribute('data-step');
              navContainer.querySelectorAll('.card-title').forEach(el => el.classList.remove('selected'));
              const activeNav = navContainer.querySelector(`.card-title[data-target-step="${step}"]`);
              if (activeNav) activeNav.classList.add('selected');
          }
      });
  }

  const prevArrow = document.querySelector('.prev-arrow.config-2');
  const nextArrow = document.querySelector('.next-arrow.config-2');

  const scrollCardsByTwo = (direction) => {
      if (!cardsContainer) return;
      const card = cardsContainer.querySelector('.config-card');
      if (!card) return;
      const containerStyle = window.getComputedStyle(cardsContainer);
      const gap = parseFloat(containerStyle.gap) || parseFloat(containerStyle.columnGap) || 0;
      const scrollAmount = (card.offsetWidth + gap) * 2 * direction;
      cardsContainer.scrollBy({ left: scrollAmount, behavior: 'smooth' });
  };

  if (prevArrow) prevArrow.addEventListener('click', (e) => { e.preventDefault(); scrollCardsByTwo(-1); });
  if (nextArrow) nextArrow.addEventListener('click', (e) => { e.preventDefault(); scrollCardsByTwo(1); });

  // ==========================================
  // --- 6. VALIDATION & RESET LOGIC ---
  // ==========================================
  const configBtns = document.querySelectorAll('#config-spec-btn, .config-spec-btn');
  const resetBtns = document.querySelectorAll('#reset-code-button, .reset-code-btn');
  const copyBtns = document.querySelectorAll('.copy-code');
  const specModal = document.querySelector('.spec-modal-wrapper');

  function validateConfiguration() {
      if (configBtns.length === 0 && copyBtns.length === 0 && resetBtns.length === 0) return;

      let isValid = true;
      const allCards = Array.from(cardsContainer.querySelectorAll('.config-card'));

      allCards.forEach(card => {
          const stepNum = parseInt(card.getAttribute('data-step'));
          let isRequired = false;

          if (stepNum === 0) {
              isRequired = true;
          } else {
              const stepData = configuratorData.find(c => c.step === stepNum);
              if (stepData && (stepData.required == 1 || stepData.required === "1" || stepData.required === true)) {
                  isRequired = true;
              }
          }

          if (isRequired) {
              const selected = card.getAttribute('data-selected-code');
              if (!selected || selected.trim() === "") isValid = false;
          }
      });

      configBtns.forEach(btn => {
          if (isValid) {
              btn.style.pointerEvents = "auto"; btn.style.opacity = "1"; btn.classList.remove('inactive');
          } else {
              btn.style.pointerEvents = "none"; btn.style.opacity = "0.5"; btn.classList.add('inactive');
          }
      });

      copyBtns.forEach(btn => {
          if (isValid) {
              btn.style.pointerEvents = "auto"; btn.style.opacity = "1"; btn.classList.remove('inactive');
          } else {
              btn.style.pointerEvents = "none"; btn.style.opacity = "0.5"; btn.classList.add('inactive');
          }
      });

      resetBtns.forEach(btn => {
          if (isValid) {
              btn.style.pointerEvents = "auto"; btn.style.opacity = "1"; btn.classList.remove('inactive');
          } else {
              btn.style.pointerEvents = "none"; btn.style.opacity = "0.25"; btn.classList.add('inactive');
          }
      });
  }

  validateConfiguration();
  cardsContainer.addEventListener('click', validateConfiguration);
  cardsContainer.addEventListener('input', validateConfiguration);

  configBtns.forEach(btn => {
      btn.setAttribute('type', 'button');
      btn.addEventListener('click', (e) => {
          e.preventDefault();
          if (specModal) specModal.style.setProperty('display', 'flex', 'important');
      });
  });

  copyBtns.forEach(btn => {
      const originalContent = btn.innerHTML;
      btn.addEventListener('click', async (e) => {
          e.preventDefault();
          const masterCodeContainer = document.querySelector('.master-code-display');
          if (!masterCodeContainer) return;

          let cleanText = '';
          const codeSpans = masterCodeContainer.querySelectorAll('span[id$="-master-code"]');
          if (codeSpans.length > 0) {
              codeSpans.forEach(span => {
                  if (window.getComputedStyle(span).display !== 'none') cleanText += span.textContent.trim();
              });
          } else {
              cleanText = (masterCodeContainer.innerText || masterCodeContainer.textContent).replace(/\s+/g, '');
          }

          try {
              await navigator.clipboard.writeText(cleanText);
              btn.innerHTML = `<span style="display: inline-block; animation: slideUpFade 0.3s ease-out forwards;">Product Code Copied!</span>`;
              setTimeout(() => { btn.innerHTML = originalContent; }, 2500);
          } catch (err) {
          }
      });
  });

  resetBtns.forEach(btn => {
      btn.addEventListener('click', (e) => {
          e.preventDefault();
          cardsContainer.querySelectorAll('.config-card').forEach(card => {
              const step = card.getAttribute('data-step');

              if (step === '0' && !hasDynamicSeries) return;

              card.querySelectorAll('.real-radio-input').forEach(radio => radio.checked = false);
              card.querySelectorAll('.custom-length-input').forEach(input => { if (input.type !== 'hidden') input.value = ""; });

              const hiddenLen = card.querySelector('input[type="hidden"].custom-length-input');
              if (!hiddenLen) card.removeAttribute('data-selected-code');

              const hasTextInput = card.querySelector('input[type="number"].custom-length-input') !== null;
              const cardCodeDisplay = card.querySelector('.options-title.part-no');
              if (cardCodeDisplay && !hiddenLen) cardCodeDisplay.textContent = hasTextInput ? "XXX.XX" : "XX";

              const cardStepData = configuratorData.find(c => c.step === parseInt(step));
              if (cardStepData && (cardStepData.label && (cardStepData.label.toLowerCase() === 'output level' || cardStepData.label.toLowerCase() === 'output'))) {
                  let safeResetVals = cardStepData.allowedValues;
                  if (typeof safeResetVals === 'string') {
                      try { safeResetVals = JSON.parse(safeResetVals); } catch(e) {}
                  }
                  if (safeResetVals && !Array.isArray(safeResetVals) && safeResetVals.lensMap && hasLensStep) {
                      const outputContainer = card.querySelector('.options-container');
                      if (outputContainer) outputContainer.innerHTML = '<div class="card-hint-text">Select a lens option first.</div>';
                  }
              }
          });
          updateMasterCode();
          autoSelectSingleOptions();
          validateConfiguration();
          cardsContainer.scrollTo({ left: 0, behavior: 'smooth' });
      });
  });

  document.addEventListener('copy', (e) => {
      const selection = window.getSelection();
      if (!selection.rangeCount) return;
      const masterCodeContainer = document.querySelector('.master-code-display');
      if (masterCodeContainer && masterCodeContainer.contains(selection.anchorNode)) {
          e.preventDefault();
          let cleanText = selection.toString().replace(/\s+/g, '');
          e.clipboardData.setData('text/plain', cleanText);
      }
  });
});

// ---- configured-spec-sheet.html ----
//=== CONFIGURED SPEC SHEET (plan 4.20, owner 2026-11-06) ===//
// The Configure Spec Sheet popup: the Download button gets the product's CURRENT spec sheet
// (read through its stable link, so it never differs from the latest one), filled in and
// highlighted:
//   - Project Name, Fixture Type and Location (#ill-project-name, #ill-fixture-type,
//     #ill-project-location) go into the footer fields (project_name, fixture_type,
//     project_location);
//   - each configurator selection (.config-card[data-step][data-selected-code]) selects the
//     step_N option in the Part Number Builder and fills its display_step_N box;
//   - the spec values tied to those selections are highlighted (yellow, 30%). The spec sheet
//     carries their boxes in its Subject, tagged "<step>:<code>" by n8n per product category.
// Also closes the popup: the close icon (.close-config-modal), Esc and a click on the backdrop.
//
// The popup has two Download buttons (Code Embeds shown by condition): #ill-download-spec-sheet
// and, on kits, #extrusions-dwnld-submittal. Both are handled. The listeners are delegated from
// the document in the capture phase and registered when the script runs, so they work whichever
// button is shown and run before any older handler on the buttons.
(function () {
  const DOWNLOAD = '#ill-download-spec-sheet, #extrusions-dwnld-submittal';
  const modalEl = () => document.querySelector('.spec-modal-wrapper');
  const closeModal = () => { const m = modalEl(); if (m) m.style.setProperty('display', 'none', 'important'); };
  const isOpen = () => { const m = modalEl(); return !!m && window.getComputedStyle(m).display !== 'none'; };
  let busy = false;
  window.__illConfiguredSpec = '2026-11-06.2';

  document.addEventListener('click', (e) => {
    const target = e.target instanceof Element ? e.target : null;
    if (!target) return;
    if (target.closest('.close-config-modal')) { e.preventDefault(); closeModal(); return; }
    if (target === modalEl()) { closeModal(); return; }
    const button = target.closest(DOWNLOAD);
    if (!button) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    if (!busy) generate(button.querySelector('button') || button);
  }, true);
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && isOpen()) closeModal(); }, true);
  document.addEventListener('submit', (e) => {
    if (e.target instanceof Element && e.target.closest('.spec-modal-wrapper')) e.preventDefault();
  }, true);

  // --- 2. THE SPEC SHEET'S STABLE LINK (the Spec Sheet row of the documents JSON) ---
  function stableLink() {
    const el = document.getElementById('raw-documents-json');
    if (!el) return null;
    let docs = [];
    try {
      docs = JSON.parse((el.textContent || '').trim().replace(/[‘’]/g, "'").replace(/[“”]/g, '"'));
    } catch (e) { return null; }
    for (const doc of Array.isArray(docs) ? docs : []) {
      const link = Object.values(doc || {}).find(v => typeof v === 'string' && v.includes('/spec-sheets/'));
      if (link) return link;
    }
    return null;
  }

  function loadPdfLib() {
    if (window.PDFLib) return Promise.resolve(window.PDFLib);
    return new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = 'https://unpkg.com/pdf-lib@1.17.1/dist/pdf-lib.min.js';
      s.onload = () => resolve(window.PDFLib);
      s.onerror = () => reject(new Error('pdf-lib did not load'));
      document.head.appendChild(s);
    });
  }

  // --- 3. THE VISITOR'S SELECTIONS: {step: code} ---
  function selections() {
    const picked = {};
    document.querySelectorAll('.config-card[data-step]').forEach(card => {
      const code = (card.getAttribute('data-selected-code') || '').trim();
      if (code) picked[card.getAttribute('data-step')] = code;
    });
    return picked;
  }

  // The input itself (an id can also sit on its wrapper in the Designer).
  const value = id => ((document.querySelector(`input#${id}, textarea#${id}`) || {}).value || '').trim();
  const field = (form, name) => { try { return form.getField(name); } catch (e) { return null; } };

  async function generate(generateBtn) {
    const link = stableLink();
    if (!link) { alert('No spec sheet is available for this product yet.'); return; }

    const originalText = generateBtn.textContent;
    generateBtn.textContent = 'Generating PDF...';
    generateBtn.style.pointerEvents = 'none';
    busy = true;
    try {
      const PDFLib = await loadPdfLib();
      // The stable link redirects to /files (no CORS); this ERPNext call returns the same file.
      const api = new URL(link).origin
        + '/api/method/illumenate_lighting.illumenate_lighting.spec_sheet_route.current_pdf?link='
        + encodeURIComponent(link);
      const response = await fetch(api, { cache: 'no-store' });
      if (!response.ok) throw new Error('Spec sheet request failed: ' + response.status);
      const pdfDoc = await PDFLib.PDFDocument.load(await response.arrayBuffer());
      const form = pdfDoc.getForm();

      // A. Project details (left editable when empty)
      [['project_name', value('ill-project-name')],
       ['fixture_type', value('ill-fixture-type')],
       ['project_location', value('ill-project-location')]].forEach(([name, text]) => {
        const f = field(form, name);
        if (f && text && typeof f.setText === 'function') f.setText(text);
      });

      // B. Part Number Builder: select each step's option and fill its code box
      const picked = selections();
      Object.entries(picked).forEach(([step, code]) => {
        const f = field(form, 'step_' + step);
        if (f && typeof f.select === 'function') {
          const match = f.getOptions().find(opt => String(opt).toLowerCase() === code.toLowerCase());
          if (match) f.select(match);
        } else if (f && typeof f.setText === 'function') {
          f.setText(code);
        }
        const box = field(form, 'display_step_' + step);
        if (box && typeof box.setText === 'function') box.setText(code.toUpperCase());
      });

      // C. Highlights over the spec values tied to the selections
      let boxes = [];
      try { boxes = JSON.parse(pdfDoc.getSubject() || '[]'); } catch (err) {}
      const tokens = new Set(Object.entries(picked).map(([step, code]) => (step + ':' + code).toLowerCase()));
      const pages = pdfDoc.getPages();
      (Array.isArray(boxes) ? boxes : []).forEach(hl => {
        const hit = String(hl.code || '').toLowerCase().split(/\s+/).some(t => tokens.has(t));
        if (!hit) return;
        const page = pages[hl.pageIndex] || pages[0];
        const padX = hl.isRow ? 0 : 2;
        const padY = hl.isRow ? 0.5 : 1.5;
        page.drawRectangle({
          x: hl.x - padX, y: hl.y - padY,
          width: hl.width + padX * 2, height: hl.height + padY * 2,
          color: PDFLib.rgb(1, 0.92, 0.25), opacity: 0.3,
        });
      });

      // D. Download
      const productName = ((document.getElementById('cms-product-name') || {}).textContent || 'Product').trim();
      const blob = new Blob([await pdfDoc.save()], { type: 'application/pdf' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `ilLumenate Lighting_${productName}_Spec Sheet_Configured.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      closeModal();
    } catch (error) {
      console.error('Configured spec sheet:', error);
      alert('The spec sheet could not be generated. Please try again.');
    } finally {
      generateBtn.textContent = originalText;
      generateBtn.style.pointerEvents = '';
      busy = false;
    }
  }
})();

// ---- compatible-products-json.html ----
// WAIT FOR FINSWEET CMS LOAD TO FETCH ALL PAGINATED ITEMS
window.fsAttributes = window.fsAttributes || [];
window.fsAttributes.push([
  'cmsload',
  (listInstances) => {


    // 1. BUILD THE DICTIONARY FROM THE LIVE DOM
    const productDictionary = {};
    const lookupItems = document.querySelectorAll('.lookup-item');

    lookupItems.forEach(item => {
        const sku = item.querySelector('.lookup-sku')?.textContent.trim();
        const name = item.querySelector('.lookup-name')?.textContent.trim();
        const imgEl = item.querySelector('.lookup-img');
        const imgSrc = imgEl ? imgEl.src : '';

        const category = item.querySelector('.lookup-category')?.textContent.trim();
        const subheading = item.querySelector('.lookup-subheading')?.textContent.trim();
        const linkEl = item.querySelector('.lookup-link');
        const url = linkEl ? linkEl.href : '#';

        if (sku) {
            productDictionary[sku] = {
                name: name,
                image: imgSrc,
                category: category,
                subheading: subheading,
                url: url
            };
        }
    });

    // 2. GRAB THE JSON & HANDLE EMPTY STATE
    const emptyState = document.querySelector('.swiper-empty-comp');
    const jsonString = document.getElementById('product-json-data')?.textContent;
    let products = [];

    if (jsonString) {
        try {
            products = JSON.parse(jsonString);
        } catch (e) {
        }
    }

    if (products.length === 0) {
        if (emptyState) emptyState.style.display = 'block';
        return;
    } else {
        if (emptyState) emptyState.style.display = 'none';
    }

    // 3. SORTING LOGIC
    const categoriesOrder = ["Replaces", "Required", "Recommended With", "Works With", "Alternative To"];
    const groupedProducts = {};

    // Only products the site shows: the lookup list holds published items only, so a product
    // that is not published (or not on this site yet) has no entry and gets no card (2026-11-06).
    products = products.filter(prod => productDictionary[prod.related_product]);
    if (products.length === 0) {
        if (emptyState) emptyState.style.display = 'block';
        return;
    }

    products.forEach(prod => {
        const rawType = prod.relationship_type;

        if (rawType) {
            const cleanType = String(rawType).trim().toLowerCase();
            const matchedCategory = categoriesOrder.find(cat => cat.toLowerCase() === cleanType);

            if (matchedCategory) {
                if (!groupedProducts[matchedCategory]) groupedProducts[matchedCategory] = [];
                groupedProducts[matchedCategory].push(prod);
            }
        }
    });

    // 4. FIND CONTAINERS
    const container = document.getElementById('dynamic-sliders-container');
    const blueprintSection = document.querySelector('.swiper-section-blueprint');
    const blueprintSlide = blueprintSection.querySelector('.swiper-slide-comp');

    if (!container || !blueprintSection || !blueprintSlide) {
        return;
    }

    // 5. BUILD THE SWIPERS
    categoriesOrder.forEach(category => {
        if (groupedProducts[category] && groupedProducts[category].length > 0) {

            const newSection = blueprintSection.cloneNode(true);
            newSection.style.display = 'block';
            newSection.style.position = 'relative';
            newSection.classList.remove('swiper-section-blueprint');

            const titleElement = newSection.querySelector('.swiper-section-title');
            if (titleElement) titleElement.textContent = category;

            const swiperWrapper = newSection.querySelector('.swiper-wrapper-comp');

            while (swiperWrapper.firstChild) {
                swiperWrapper.removeChild(swiperWrapper.firstChild);
            }

            groupedProducts[category].forEach(prod => {
                const newSlide = blueprintSlide.cloneNode(true);

                const rawProductSKU = prod.related_product;
                const realData = productDictionary[rawProductSKU];

                if (realData && realData.url) {
                    newSlide.href = realData.url;
                }

                const nameEl = newSlide.querySelector('.comp-prod-name');
                if (nameEl) nameEl.textContent = realData ? realData.name : rawProductSKU;

                const catEl = newSlide.querySelector('.comp-prod-category');
                if (catEl) catEl.textContent = realData && realData.category ? realData.category : '';

                const subEl = newSlide.querySelector('.comp-prod-subheading');
                if (subEl) subEl.textContent = realData && realData.subheading ? realData.subheading : '';

                const imgEl = newSlide.querySelector('.comp-prod-image');
                if (imgEl && realData && realData.image) {
                    imgEl.src = realData.image;
                    imgEl.removeAttribute('srcset');
                    imgEl.removeAttribute('sizes');
                }

                swiperWrapper.appendChild(newSlide);
            });

            container.appendChild(newSection);

            // 6. INITIALIZE SWIPER
      const swiperElement = newSection.querySelector('.swiper-comp');
      const nextArrow = newSection.querySelector('.comp-next-arrow');
      const prevArrow = newSection.querySelector('.comp-prev-arrow');

      new Swiper(swiperElement, {
          wrapperClass: 'swiper-wrapper-comp',
          slideClass: 'swiper-slide-comp',
          slidesPerView: 'auto',
          spaceBetween: 16,
          slidesPerGroup: 2,
          freeMode: false,
          watchOverflow: true,
          navigation: {
              nextEl: nextArrow,
              prevEl: prevArrow,
          },
      });
    }
  });

  window.Webflow && window.Webflow.require('ix2').init();

  }
]);

// ---- products-collection-before-body.html ----
// --- UPDATES THE COMPATIBLE PRODUCTS SECTION ---
document.addEventListener("DOMContentLoaded", () => {
  // Select our main layout elements
  const wrapperSection = document.querySelector('.related-products-coll-list-wrapper');
  const parentList = document.querySelector('.related-coll-list');
  const emptyMsg = document.querySelector('.empty-cmpatible-prods');

  // Helper function to show the empty message and hide the list
  function triggerEmptyState() {
      if (parentList) parentList.style.display = 'none';
      if (emptyMsg) emptyMsg.style.display = 'flex';
      if (wrapperSection) wrapperSection.style.display = 'block';
  }

  // 1. Get the current page's compatible products JSON
  const jsonEl = document.getElementById('compatible-products-json');
  if (!jsonEl) {
      console.warn("STOPPING: Could not find the <div id='compatible-products-json'> element on the page.");
      return;
  }

  let compatibleProducts = [];
  try {
    let rawJson = jsonEl.innerHTML.replace(/[\u2018\u2019]/g, "'").replace(/[\u201C\u201D]/g, '"').trim();

    // SAFETY CHECK 1: If JSON is totally empty
    if (!rawJson || rawJson === "") {
        triggerEmptyState();
        return;
    }

    compatibleProducts = JSON.parse(rawJson);
  } catch (e) {
    console.error("STOPPING: Error parsing compatible products JSON.", e);
    return;
  }

  // 2. Find all product cards
  const allCards = Array.from(document.querySelectorAll('.related-coll-item'));

  // SAFETY CHECK 2: If Webflow's list is completely empty
  if (allCards.length === 0) {
      triggerEmptyState();
      return;
  }

  const matchedCards = [];

  // 3. Loop through cards and match
  allCards.forEach(card => {
    const erpEl = card.querySelector('.card-erp-id');
    if (!erpEl) {
        card.remove();
        return;
    }

    const cardErpId = erpEl.textContent.trim();

    // Find the full matching object in the JSON array
    // The sync sends related_product / relationship_type; product / type are the old keys.
    const matchingData = compatibleProducts.find(item => (item.related_product || item.product) === cardErpId);

    if (matchingData) {
      // Inject the relationship type
      const typeEl = card.querySelector('.relationship-type');
      if (typeEl) {
          const relationship = matchingData.relationship_type || matchingData.type;
          if (relationship) {
              typeEl.textContent = relationship;
              typeEl.style.display = '';
          } else {
              typeEl.style.display = 'none';
          }
      }

      matchedCards.push({
        element: card,
        sortIndex: compatibleProducts.indexOf(matchingData)
      });
    } else {
      card.remove();
    }
  });

  // 4. Cleanup & Reordering
  // SAFETY CHECK 3: Checking if any cards actually survived the matching process
  if (matchedCards.length > 0 && parentList) {

    if (emptyMsg) emptyMsg.style.display = 'none';
    if (parentList) parentList.style.display = '';

    matchedCards.sort((a, b) => a.sortIndex - b.sortIndex);
    matchedCards.forEach(match => {
      match.element.style.display = 'block';
      parentList.appendChild(match.element);
    });

  } else {
    triggerEmptyState();
  }
});

// ---- products-collection-before-body.html ----
document.addEventListener('DOMContentLoaded', function() {

  // --- 1. HERO SLIDER NAVIGATION (STARS & ARROWS) ---
  const starSelector = '.pdp-star-dot, .custom-star-dot';
  $(document).off('click', starSelector).on('click', starSelector, function(e) {
    e.preventDefault();
    e.stopPropagation();
    const index = $(starSelector).index(this);
    let $heroDots = $('.hero-slider-nav .w-slider-dot');
    if ($heroDots.length === 0) $heroDots = $('.w-slider-nav').first().find('.w-slider-dot');
    if ($heroDots.length > index) $heroDots.eq(index).trigger('tap');
  });

  $('.pdp-prev-arrow').on('click', function(e) { e.preventDefault(); $('.w-slider-arrow-left').first().trigger('tap'); });
  $('.pdp-next-arrow').on('click', function(e) { e.preventDefault(); $('.w-slider-arrow-right').first().trigger('tap'); });

  const heroObserver = new MutationObserver(function() {
      let $heroNav = $('.hero-slider-nav');
      if ($heroNav.length === 0) $heroNav = $('.w-slider-nav').first();
      const activeIndex = $heroNav.find('.w-slider-dot.w-active').index();
      if (activeIndex > -1) {
          $(starSelector).removeClass('active').eq(activeIndex).addClass('active');
      }
  });
  let $heroNavTarget = $('.hero-slider-nav');
  if ($heroNavTarget.length === 0) $heroNavTarget = $('.w-slider-nav').first();
  $heroNavTarget.each(function() { heroObserver.observe(this, { attributes: true, subtree: true, childList: true }); });

  // --- 2. DYNAMIC HERO SLIDER POPULATOR ---
  const sliderMask = document.querySelector('.w-slider-mask');
  const slideTemplate = document.querySelector('.hero-slide-template');
  const ghostImages = document.querySelectorAll('.ghost-img-source');
  const $starTemplate = $('.pdp-star-dot').first();
  const $nextArrow = $('.pdp-next-arrow');

  if (sliderMask && slideTemplate) {
    if (ghostImages.length > 0) {
      ghostImages.forEach((img, idx) => {
        const newSlide = slideTemplate.cloneNode(true);
        newSlide.classList.remove('hero-slide-template');
        newSlide.classList.add('w-slide');
        const targetImg = newSlide.querySelector('.hero-slide-img');
        if (targetImg) {
          targetImg.src = img.src; targetImg.srcset = img.srcset; targetImg.sizes = img.sizes; targetImg.removeAttribute('id');
        }
        sliderMask.appendChild(newSlide);
        if (idx >= 0 && $starTemplate.length > 0 && $nextArrow.length > 0) {
            const $newStar = $starTemplate.clone(); $newStar.removeClass('active'); $nextArrow.before($newStar);
        }
      });
    }
    slideTemplate.remove();
    if (window.Webflow && window.Webflow.require('slider')) {
        window.Webflow.require('slider').redraw();
        window.Webflow.require('slider').ready();
    }
  }

  // --- 3. SPECIFICATIONS CLEANER ---
  const specElements = document.querySelectorAll('[data-clean-spec]');
  specElements.forEach(el => {
    const raw = el.getAttribute('data-clean-spec');
    if (!raw) return;
    const cleanNames = raw.split('|').map(g => g.split(',')[0].trim());
    el.innerText = cleanNames.join(', ');
  });

  // --- 7. DYNAMIC LENGTH DISCLAIMER ---
  (function() {
    const categoryEl = document.getElementById('pdp-category-name');
    const categoryText = categoryEl ? categoryEl.innerText.toLowerCase().trim() : '';
    const noteWrapper = document.querySelector('.length-note');
    const noteTextEl = document.getElementById('fixture-length-note');

    if (!noteWrapper || !categoryText.includes('linear fixtures')) {
      if (noteWrapper) noteWrapper.style.display = 'none';
      return;
    }

    let formattedInterval = '1.31in (33.3mm)';
    const rawSpecsEl = document.getElementById('raw-specs-data');
    if (rawSpecsEl) {
      try {
        const specsData = JSON.parse(rawSpecsEl.innerText.trim());
        const intervalSpec = specsData.find(s => s.spec_label && s.spec_label.toUpperCase() === 'PRODUCTION INTERVAL');
        if (intervalSpec && intervalSpec.spec_value) {
          const rawValue = intervalSpec.spec_value;
          const numberMatch = rawValue.match(/([\d.]+)/);
          if (numberMatch) {
            const inches = parseFloat(numberMatch[1]);
            const mm = (inches * 25.4).toFixed(1);
            formattedInterval = `${inches}in (${mm}mm)`;
          } else {
            formattedInterval = rawValue;
          }
        }
      } catch (e) {
        console.error("Failed to parse specifications for Length Disclaimer.", e);
      }
    }

    if (noteTextEl) {
      noteTextEl.innerText = `Fixtures will be built as close to the requested length without going over based on a ${formattedInterval} production interval. Lengths longer than 78in will consist of multiple pieces of channel and lens to be assembled in the field to create the complete fixture length.`;
      noteWrapper.style.display = 'flex';
    }
  })();

  // --- 8. RELATED PRODUCTS ARROWS ---
  (function() {
    const prevArrow = document.querySelector('.prev-arrow.related');
    const nextArrow = document.querySelector('.next-arrow.related');

    const scrollRelatedCards = (direction) => {
        let scrollContainer = document.querySelector('.related-coll-list');
        if (!scrollContainer) return;

        const cards = Array.from(scrollContainer.querySelectorAll('.related-coll-item'));
        const visibleCard = cards.find(card => card.style.display !== 'none');
        if (!visibleCard) return;

        const containerStyle = window.getComputedStyle(scrollContainer);
        const gap = parseFloat(containerStyle.gap) || parseFloat(containerStyle.columnGap) || 0;
        const cardStyle = window.getComputedStyle(visibleCard);
        const margin = parseFloat(cardStyle.marginRight) || parseFloat(cardStyle.marginLeft) || 0;

        const scrollAmount = (visibleCard.offsetWidth + gap + margin) * direction;

        scrollContainer.scrollBy({
            left: scrollAmount,
            behavior: 'smooth'
        });
    };

    if (prevArrow) {
        prevArrow.addEventListener('click', (e) => {
            e.preventDefault();
            scrollRelatedCards(-1);
        });
    }
    if (nextArrow) {
        nextArrow.addEventListener('click', (e) => {
            e.preventDefault();
            scrollRelatedCards(1);
        });
    }
  })();

  // --- 9. PRODUCT BADGES ---
  (function() {
    const pdpBadges = document.querySelectorAll('.pdp-product-badge');
    pdpBadges.forEach(badge => {
        const rawText = badge.textContent || badge.innerText;
        const badgeText = rawText.trim().toLowerCase();

        if (!badgeText || badgeText === '' || badgeText === 'none') {
            badge.style.display = 'none';
            return;
        }

        badge.style.display = 'flex';

        if (badgeText.includes('new')) {
            badge.classList.add('badge-new');
        } else if (badgeText.includes('sale')) {
            badge.classList.add('badge-sale');
        } else if (badgeText.includes('quick ship')) {
            badge.classList.add('badge-quick-ship');
        }
    });
  })();

});

// ---- products-collection-before-body.html ----
//=== ILL-DOWNLOAD-SPEC-BTN ===//
document.addEventListener('DOMContentLoaded', () => {
    // 1. Prevent the "Enter" key from submitting Webflow's form, and trigger the download instead!
    const specModal = document.querySelector('.spec-modal-wrapper');

    if (specModal) {
        specModal.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();

                const dlBtn = document.getElementById('ill-download-spec-sheet');
                if (dlBtn) dlBtn.click();
            }
        });
    }
});

// 2. Fix the "Back Button" cache glitch
window.addEventListener('pageshow', (event) => {
    if (event.persisted) {
        const modal = document.querySelector('.spec-modal-wrapper');
        if (modal) modal.style.setProperty('display', 'none', 'important');

        const dlBtn = document.getElementById('ill-download-spec-sheet');
        if (dlBtn) {
            dlBtn.disabled = false;
            dlBtn.style.opacity = '1';
            dlBtn.textContent = 'Download Spec Sheet';
        }
    }
});

window.__illStaging.own = false;
