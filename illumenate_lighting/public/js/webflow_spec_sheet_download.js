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

    // Fall back to last URL segment
    var parts = window.location.pathname.replace(/\/+$/, '').split('/');
    return parts[parts.length - 1] || '';
  }

  /**
   * Read the current configurator selections.
   *
   * This looks for the global IllumenateConfigurator object that the
   * Webflow configurator JS creates. Adjust the property name if your
   * configurator stores selections differently.
   */
  function getSelections() {
    // Option 1: Global IllumenateConfigurator class (from WEBFLOW_INTEGRATION_GUIDE)
    if (window.IllumenateConfigurator && window.IllumenateConfigurator.selections) {
      return window.IllumenateConfigurator.selections;
    }

    // Option 2: Global WebflowConfigurator object (from portal JS)
    if (window.WebflowConfigurator && window.WebflowConfigurator.selections) {
      return window.WebflowConfigurator.selections;
    }

    // Option 3: Configurator instance on the page
    if (window.configurator && window.configurator.selections) {
      return window.configurator.selections;
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
    return required.every(function (key) {
      return selections[key];
    });
  }

  // ─── Main ───────────────────────────────────────────────────────

  document.addEventListener('DOMContentLoaded', function () {
    var btn = document.getElementById('ill-download-spec-sheet');
    if (!btn) return; // Button not on this page

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
