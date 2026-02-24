/**
 * ilLumenate Spec Sheet Download Button — Webflow Embed Snippet
 *
 * Works with the Webflow product page configurator that uses radio buttons
 * with names: Series, Environment, CCT, Output, Lens, Mounting, Finish
 * and inputs: length-input, start-feed-length, end-feed-length
 *
 * Webflow setup:
 *   1. Button with id="ill-download-spec-sheet"
 *   2. Optional inputs with ids "ill-project-name" and "ill-project-location"
 *   3. Paste this script AFTER the configurator script in Before </body>
 */

(function () {
  'use strict';

  // ─── Configuration ──────────────────────────────────────────────
  var ERPNEXT_SITE = 'https://illumenatelighting.v.frappe.cloud';
  var API_ENDPOINT = ERPNEXT_SITE + '/api/method/illumenate_lighting.illumenate_lighting.api.webflow_configurator.download_spec_sheet';

  // Map Webflow radio group names → ERPNext API field names
  var RADIO_MAP = {
    'Series':               'series',
    'Environment':          'environment_rating',
    'CCT':                  'cct',
    'Output':               'output_level',
    'Lens':                 'lens_appearance',
    'Mounting':             'mounting_method',
    'Finish':               'finish',
    'Start Feed Direction': 'start_feed_direction',
    'End Feed Direction':   'end_feed_direction'
  };

  // ─── Helpers ────────────────────────────────────────────────────

  function getProductSlug() {
    var el = document.querySelector('[data-ill-product-slug]');
    if (el) return el.getAttribute('data-ill-product-slug');

    var cfgEl = document.querySelector('[data-configurator]');
    if (cfgEl && cfgEl.dataset.productSlug) return cfgEl.dataset.productSlug;

    var parts = window.location.pathname.replace(/\/+$/, '').split('/');
    return parts[parts.length - 1] || '';
  }

  /**
   * Read configurator selections from the page's radio buttons and inputs.
   */
  function getSelections() {
    // Allow explicit override
    if (typeof window.illGetSelections === 'function') {
      var custom = window.illGetSelections();
      if (custom && typeof custom === 'object') return custom;
    }

    var sel = {};

    // 1. Read checked radio buttons
    for (var groupName in RADIO_MAP) {
      var checked = document.querySelector('input[name="' + groupName + '"]:checked');
      if (checked) {
        var apiField = RADIO_MAP[groupName];
        sel[apiField] = checked.value;
        // Also store the code — backend can use either
        var code = checked.getAttribute('data-code');
        if (code) sel[apiField + '_code'] = code;
      }
    }

    // 2. Read length from the card display (shows raw inches typed by user)
    //    Webflow auto-formats with a decimal, so the user types e.g. 5000
    //    to represent 50.00 inches.  Divide by 100 to get real inches.
    var lengthCard = document.getElementById('length-card-display');
    if (lengthCard && lengthCard.innerText && lengthCard.innerText !== 'XX') {
      sel.length_inches = (parseFloat(lengthCard.innerText) || 0) / 100;
    } else {
      // Fallback: read from input directly
      var lengthInput = document.getElementById('length-input');
      if (lengthInput && lengthInput.value) {
        var raw = lengthInput.value.replace(/[^0-9.]/g, '');
        sel.length_inches = (parseFloat(raw) || 0) / 100;
      }
    }

    // 3. Read feed lengths from inputs
    var startFeedLen = document.getElementById('start-feed-length');
    if (startFeedLen && startFeedLen.value) {
      sel.start_feed_length_ft = parseFloat(startFeedLen.value.replace(/[^0-9]/g, '')) || 0;
    }

    var endFeedLen = document.getElementById('end-feed-length');
    if (endFeedLen && endFeedLen.value) {
      sel.end_feed_length_ft = parseFloat(endFeedLen.value.replace(/[^0-9]/g, '')) || 0;
    }

    console.log('[ILL Spec Sheet] Selections from DOM:', JSON.stringify(sel, null, 2));
    return Object.keys(sel).length > 0 ? sel : null;
  }

  /**
   * Check minimum selections for a useful spec sheet.
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
      return false;
    }
    return true;
  }

  // ─── Main ───────────────────────────────────────────────────────

  document.addEventListener('DOMContentLoaded', function () {
    var btn = document.getElementById('ill-download-spec-sheet');
    if (!btn) return;

    btn.addEventListener('click', async function (e) {
      e.preventDefault();

      var selections = getSelections();

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
      btn.textContent = 'Generating\u2026';
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
        console.error('[ILL Spec Sheet] Download failed:', err);
        alert('An error occurred while generating the spec sheet. Please try again.');
      } finally {
        btn.textContent = originalText;
        btn.disabled = false;
        btn.style.opacity = '1';
      }
    });
  });
})();
