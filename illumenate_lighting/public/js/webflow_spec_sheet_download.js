/**
 * ilLumenate Spec Sheet Download Button — Webflow Embed Snippet
 *
 * Drop this into the Webflow product page's custom code (before </body>)
 * or embed it in a Webflow HTML Embed element near the configurator.
 *
 * Prerequisites:
 *   - The ILL Webflow Configurator must already be on the page and working.
 *   - A button with id="ill-download-spec-sheet" must exist on the page.
 *   - Optionally, two input fields with ids "ill-project-name" and
 *     "ill-project-location" for the user to fill in.
 *
 * Webflow setup:
 *   1. Add a Button element, set its ID to "ill-download-spec-sheet"
 *   2. Set its initial text to "Download Spec Sheet"
 *   3. Optionally add text inputs with IDs "ill-project-name" and
 *      "ill-project-location" under a heading like "Customize Your Spec Sheet"
 *   4. Paste this script into Page Settings → Custom Code → Before </body> tag
 *
 * If your configurator stores selections in a custom location, set:
 *   window.illGetSelections = function() { return { ... }; };
 * before this script loads.
 */

(function () {
  'use strict';

  // ─── Configuration ──────────────────────────────────────────────
  // Change this to your ERPNext site URL (no trailing slash)
  var ERPNEXT_SITE = 'https://illumenatelighting.v.frappe.cloud';
  var API_ENDPOINT = ERPNEXT_SITE + '/api/method/illumenate_lighting.illumenate_lighting.api.webflow_configurator.download_spec_sheet';

  // ─── Helpers ────────────────────────────────────────────────────

  /**
   * Get the current product slug from the page URL.
   * Webflow product pages typically live at /products/{slug}
   */
  function getProductSlug() {
    // Check for a data-attribute first (allows explicit override)
    var el = document.querySelector('[data-ill-product-slug]');
    if (el) return el.getAttribute('data-ill-product-slug');

    // Check for data-product-slug on configurator container
    var cfgEl = document.querySelector('[data-configurator]');
    if (cfgEl && cfgEl.dataset.productSlug) return cfgEl.dataset.productSlug;

    // Fall back to last URL segment
    var parts = window.location.pathname.replace(/\/+$/, '').split('/');
    return parts[parts.length - 1] || '';
  }

  /**
   * Read the current configurator selections.
   *
   * Tries multiple strategies in priority order to find the selections
   * object from whatever configurator implementation is on the page.
   */
  function getSelections() {
    // Strategy 0: User-provided override function
    if (typeof window.illGetSelections === 'function') {
      var custom = window.illGetSelections();
      if (custom && typeof custom === 'object') return custom;
    }

    // Strategy 1: Global WebflowConfigurator object (portal JS pattern)
    if (window.WebflowConfigurator && window.WebflowConfigurator.selections &&
        Object.keys(window.WebflowConfigurator.selections).length > 0) {
      // Also gather feed lengths from DOM inputs, as portal JS does
      var sel = Object.assign({}, window.WebflowConfigurator.selections);
      _enrichFromDomInputs(sel);
      return sel;
    }

    // Strategy 2: FixtureConfigurator class instance (WEBFLOW_INTEGRATION_GUIDE pattern)
    if (window.IllumenateConfigurator && window.IllumenateConfigurator.selections &&
        Object.keys(window.IllumenateConfigurator.selections).length > 0) {
      return window.IllumenateConfigurator.selections;
    }

    // Strategy 3: Any global named "configurator" with a selections property
    if (window.configurator && window.configurator.selections &&
        Object.keys(window.configurator.selections).length > 0) {
      return window.configurator.selections;
    }

    // Strategy 4: Scan all window properties for any object that looks like
    //             a FixtureConfigurator instance (has .selections and .productSlug)
    var keys = Object.keys(window);
    for (var i = 0; i < keys.length; i++) {
      try {
        var obj = window[keys[i]];
        if (obj && typeof obj === 'object' && obj.selections &&
            typeof obj.selections === 'object' &&
            Object.keys(obj.selections).length > 0 &&
            (obj.productSlug || obj.product_slug || obj.API_BASE)) {
          return obj.selections;
        }
      } catch (e) { /* skip inaccessible properties */ }
    }

    // Strategy 5: DOM scraping fallback — read selections from active pills,
    //             selected options, and input values directly
    return _scrapeSelectionsFromDOM();
  }

  /**
   * Enrich a selections object with values from DOM inputs that may not
   * be stored in the JS selections object (e.g., feed lengths, length value).
   */
  function _enrichFromDomInputs(sel) {
    // Length
    if (!sel.length_inches) {
      var lengthEl = document.querySelector('input[name="length_value"], input[name="length_inches"], #length_inches, #lengthInput');
      if (lengthEl && lengthEl.value) {
        var unitEl = document.querySelector('select[name="length_unit"]');
        var val = parseFloat(lengthEl.value) || 0;
        if (unitEl && unitEl.value === 'ft') {
          sel.length_inches = val * 12;
        } else if (unitEl && unitEl.value === 'mm') {
          sel.length_inches = val / 25.4;
        } else {
          sel.length_inches = val;
        }
      }
    }

    // Start feed length
    if (!sel.start_feed_length_ft) {
      var startFeedEl = document.querySelector('input[name="start_feed_length_ft"], #start_feed_length_ft');
      if (startFeedEl && startFeedEl.value) {
        sel.start_feed_length_ft = startFeedEl.value;
      }
    }

    // End feed length
    if (!sel.end_feed_length_ft) {
      var endFeedEl = document.querySelector('input[name="end_feed_length_ft"], #end_feed_length_ft');
      if (endFeedEl && endFeedEl.value) {
        sel.end_feed_length_ft = endFeedEl.value;
      }
    }
  }

  /**
   * Last-resort: scrape configurator selections directly from DOM elements.
   * Looks for active pill buttons, selected <option>s, and input values.
   */
  function _scrapeSelectionsFromDOM() {
    var sel = {};

    // Read from active pills: <button class="pill active" data-value="...">
    // inside containers with data-field="..." or data-step="..."
    var activePills = document.querySelectorAll(
      '.pill.active[data-value], .pill-btn.active[data-value], ' +
      '.option-btn.selected[data-value], .option-btn.active[data-value], ' +
      '[data-selected="true"][data-value]'
    );
    activePills.forEach(function (pill) {
      var parent = pill.closest('[data-field], [data-step]');
      var field = parent
        ? (parent.getAttribute('data-field') || parent.getAttribute('data-step'))
        : (pill.getAttribute('data-step') || pill.getAttribute('data-field'));
      if (field) {
        sel[field] = pill.getAttribute('data-value');
      }
    });

    // Read from select elements with name matching known fields
    var knownFields = [
      'environment_rating', 'cct', 'output_level', 'lens_appearance',
      'mounting_method', 'finish', 'start_feed_direction', 'end_feed_direction'
    ];
    knownFields.forEach(function (field) {
      if (!sel[field]) {
        var selectEl = document.querySelector(
          'select[name="' + field + '"], #' + field
        );
        if (selectEl && selectEl.value) {
          sel[field] = selectEl.value;
        }
      }
    });

    // Read length, feed lengths from inputs
    _enrichFromDomInputs(sel);

    // Only return if we found at least some selections
    if (Object.keys(sel).length > 0) {
      return sel;
    }

    return null;
  }

  /**
   * Check if enough selections are made to generate a useful spec sheet.
   * We require at minimum: environment_rating, cct, lens_appearance,
   * finish, mounting_method, and length_inches.
   */
  function hasMinimumSelections(selections) {
    if (!selections) return false;
    var required = [
      'environment_rating', 'cct', 'lens_appearance',
      'finish', 'mounting_method', 'length_inches'
    ];
    var missing = [];
    required.forEach(function (key) {
      if (!selections[key]) missing.push(key);
    });

    if (missing.length > 0) {
      console.log('[ILL Spec Sheet] Missing selections:', missing);
      console.log('[ILL Spec Sheet] Current selections:', JSON.stringify(selections));
      return false;
    }
    return true;
  }

  // ─── Main ───────────────────────────────────────────────────────

  document.addEventListener('DOMContentLoaded', function () {
    var btn = document.getElementById('ill-download-spec-sheet');
    if (!btn) return; // Button not on this page

    btn.addEventListener('click', async function (e) {
      e.preventDefault();

      var selections = getSelections();

      // Debug: log what we found so we can troubleshoot
      console.log('[ILL Spec Sheet] Selections found:', JSON.stringify(selections));

      if (!hasMinimumSelections(selections)) {
        alert(
          'Please complete your fixture configuration before downloading a spec sheet.\n\n' +
          'Required: Environment, CCT, Lens, Mounting, Finish, and Length.'
        );
        return;
      }

      var productSlug = getProductSlug();
      if (!productSlug) {
        alert('Could not determine product. Please refresh and try again.');
        return;
      }

      // Read optional project fields
      var projectNameEl = document.getElementById('ill-project-name');
      var projectLocationEl = document.getElementById('ill-project-location');

      var payload = {
        product_slug: productSlug,
        selections: JSON.stringify(selections),
        project_name: projectNameEl ? projectNameEl.value : '',
        project_location: projectLocationEl ? projectLocationEl.value : ''
      };

      // Update button state
      var originalText = btn.textContent;
      btn.textContent = 'Generating…';
      btn.disabled = true;
      btn.style.opacity = '0.6';

      try {
        var response = await fetch(API_ENDPOINT, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
          },
          body: new URLSearchParams(payload).toString()
        });

        var data = await response.json();

        if (data.message && data.message.success && data.message.file_url) {
          // Trigger download
          var link = document.createElement('a');
          link.href = ERPNEXT_SITE + data.message.file_url;
          link.download = data.message.filename || 'Spec_Sheet.pdf';
          link.target = '_blank';
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
        } else {
          var errorMsg = (data.message && data.message.error)
            ? data.message.error
            : 'Could not generate spec sheet. Please try again.';
          alert(errorMsg);
        }
      } catch (err) {
        console.error('Spec sheet download failed:', err);
        alert('An error occurred while generating the spec sheet. Please try again.');
      } finally {
        btn.textContent = originalText;
        btn.disabled = false;
        btn.style.opacity = '1';
      }
    });
  });
})();
