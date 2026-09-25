/**
 * ilLumenate Spec Sheet Download Button — Webflow Embed Snippet
 *
 * Works with the Webflow product page configurator that uses radio buttons
 * with names: Series, Environment, CCT, Output, Lens, Mounting, Finish
 * and inputs: length-input, start-feed-length, end-feed-length
 *
 * Webflow setup:
 *   1. Button with id="ill-download-spec-sheet"
 *   2. Optional inputs with ids "ill-project-name", "ill-project-location",
 *      and "ill-fixture-type"
 *   3. Paste this script AFTER the configurator script in Before </body>
 */

(function () {
  'use strict';

  // ─── Configuration ──────────────────────────────────────────────
  var configElement = document.querySelector('[data-ill-erp-origin]');
  var ERPNEXT_SITE = (configElement && configElement.getAttribute('data-ill-erp-origin')) || window.ILL_ERPNEXT_ORIGIN || 'https://illumenatelighting.v.frappe.cloud';
  // Deployments can set their approved ERP origin without editing this asset.
  ERPNEXT_SITE = new URL(ERPNEXT_SITE).origin;
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
    'End Feed Direction':   'end_feed_direction',
    'Start Feed Length':    'start_feed_length_ft',
    'End Feed Length':      'end_feed_length_ft',
    // Driver / Controller configurator axes
    'Wattage':              'wattage',
    'Output Voltage':       'voltage_output',
    'Dimming Input':        'input_protocol',
    'Input Protocol':       'input_protocol',
    'Output Protocol':      'output_protocol',
    'Controller Type':      'controller_type',
    'Channels':             'channels',
    'Zones':                'zones',
    'Wireless Protocol':    'wireless_protocol',
    'Mounting Type':        'mounting_type'
  };

  // Product types whose configurator steps are entirely template-driven, so
  // the browser cannot know which of them are required. The backend validates.
  var VARIANT_PRODUCT_TYPES = ['Driver', 'Controller'];

  function isVariantProductType(productType) {
    return VARIANT_PRODUCT_TYPES.indexOf(productType) !== -1;
  }

  // ─── Helpers ────────────────────────────────────────────────────

  /**
   * Detect the product type from the page.
   * Checks data attribute first, then infers from available radio groups.
   *
   * Driver and Controller pages MUST declare data-ill-product-type — they
   * cannot be inferred, because their radio groups are template-driven.
   */
  async function mountSheetChoices() {
    var root = document.querySelector('[data-ill-sheet-configurator]');
    if (!root || getProductType() !== 'LED Sheet' || root.dataset.mounted === 'true') return;
    root.dataset.mounted = 'true';
    var download = document.getElementById('ill-download-spec-sheet');
    if (download) download.disabled = true;
    var status = document.createElement('p'); status.setAttribute('role', 'status');
    status.textContent = 'Loading available Sheet choices…'; root.replaceChildren(status);
    function control(id, title, kind, values) {
      var wrap = document.createElement('div'), label = document.createElement('label');
      var input = document.createElement(kind === 'select' ? 'select' : 'input');
      label.htmlFor = input.id = id; label.textContent = title;
      if (kind === 'select') (values || []).forEach(function (row) {
        var option = document.createElement('option'); option.value = row.value; option.textContent = row.label;
        option.selected = !!row.selected; input.appendChild(option);
      });
      else { input.type = kind; if (kind === 'number') { input.min = '0.001'; input.step = 'any'; } }
      wrap.append(label, input); root.appendChild(wrap); return input;
    }
    try {
      var url = new URL('/api/method/illumenate_lighting.illumenate_lighting.api.webflow_configurator.get_sheet_configurator_data', ERPNEXT_SITE);
      url.searchParams.set('webflow_product_slug', getProductSlug());
      var response = await fetch(url.toString(), {headers: {'Accept': 'application/json'}});
      var data = (await response.json()).message;
      if (!response.ok || !data || !data.success || !data.specs.length) throw new Error('Unavailable choices');
      control('ill-sheet-spec', 'Sheet specification', 'select', data.specs.map(function (spec) {
        return {value: spec.name, label: [spec.name, spec.cct, spec.total_sheet_watts ? spec.total_sheet_watts + ' W per panel' : ''].filter(Boolean).join(' · ')};
      }));
      ['width', 'height'].forEach(function (dimension) {
        control('ill-sheet-' + dimension, 'Coverage ' + dimension, 'number');
        control('ill-sheet-' + dimension + '-unit', dimension + ' unit', 'select', [
          {value: 'ft', label: 'Feet'}, {value: 'in', label: 'Inches'}, {value: 'mm', label: 'Millimeters'}]);
      });
      Object.keys(data.options || {}).forEach(function (kind, index) {
        var choices = data.options[kind], field = control('ill-sheet-option-' + index, kind, 'select', choices.map(function (choice) {
          return {value: choice.code || choice.attribute, label: choice.attribute, selected: choice.is_default};
        }));
        field.setAttribute('data-ill-sheet-option', kind);
      });
      var power = control('ill-sheet-include-power', 'Include power supplies', 'checkbox'); power.checked = true;
      control('ill-sheet-protocol', 'Dimming input protocol', 'select', [{value: '', label: 'Select protocol'}].concat((data.input_protocols || []).map(function (protocol) {
        return {value: protocol.code || protocol.name || protocol, label: protocol.label || protocol.name || protocol.code || protocol};
      })));
      status.textContent = 'Select coverage dimensions and options. Download shows engineering specifications; project ordering continues in the portal.';
      if (download) download.disabled = false;
    } catch (_) {
      status.textContent = 'Sheet choices could not be loaded. Your product remains selected.';
      var retry = document.createElement('button'); retry.type = 'button'; retry.textContent = 'Retry choices';
      retry.addEventListener('click', function () { root.dataset.mounted = ''; mountSheetChoices(); }); root.appendChild(retry);
    }
  }

  function getProductType() {
    var el = document.querySelector('[data-ill-product-type]');
    if (el) return el.getAttribute('data-ill-product-type');
    // Infer from available radio groups — if no Lens/Mounting, it's neon
    var hasLens = document.querySelector('input[name="Lens"]');
    var hasMounting = document.querySelector('input[name="Mounting"]');
    if (!hasLens && !hasMounting) return 'LED Neon';
    return 'Fixture Template';
  }

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

    if (getProductType() === 'LED Sheet') {
      var value = function (id) { var input = document.getElementById(id); return input ? input.value : ''; };
      var options = {};
      document.querySelectorAll('[data-ill-sheet-option]').forEach(function (input) {
        if (input.value && (!['radio', 'checkbox'].includes(input.type) || input.checked)) options[input.getAttribute('data-ill-sheet-option')] = input.value;
      });
      var power = document.getElementById('ill-sheet-include-power');
      return {spec: value('ill-sheet-spec'), options: options,
        coverage_width_value: value('ill-sheet-width'), coverage_width_unit: value('ill-sheet-width-unit') || 'ft',
        coverage_height_value: value('ill-sheet-height'), coverage_height_unit: value('ill-sheet-height-unit') || 'ft',
        include_power_supply: power ? power.checked : true, dimming_protocol_code: value('ill-sheet-protocol') || null};
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

    return Object.keys(sel).length > 0 ? sel : null;
  }

  /**
   * Check minimum selections for a useful spec sheet.
   * Required fields depend on the product type.
   */
  function hasMinimumSelections(selections) {
    if (!selections) return false;
    var productType = getProductType();
    var required;
    if (productType === 'LED Sheet') {
      return Number(selections.coverage_width_value || selections.coverage_width_ft) > 0 && Number(selections.coverage_height_value || selections.coverage_height_ft) > 0;
    } else if (isVariantProductType(productType)) {
      // Driver / Controller steps come from the template's allowed options, so
      // the required set is only known server-side. Let the backend decide and
      // report any missing steps.
      required = [];
    } else if (productType === 'LED Neon' || productType === 'LED Tape') {
      required = ['cct', 'output_level', 'finish', 'length_inches'];
    } else {
      required = [
        'environment_rating', 'cct', 'lens_appearance',
        'finish', 'mounting_method', 'length_inches'
      ];
    }
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
    document.querySelectorAll('[data-ill-portal-handoff]').forEach(function (link) {
      link.addEventListener('click', function (event) {
        if (getProductType() !== 'LED Sheet') return;
        event.preventDefault();
        var target = new URL('/portal/configure', ERPNEXT_SITE);
        target.searchParams.set('category', 'LED Sheet');
        target.searchParams.set('product_slug', getProductSlug());
        target.searchParams.set('sheet_selections', JSON.stringify(getSelections()));
        window.location.assign(target.toString());
      });
    });
    mountSheetChoices();
    var btn = document.getElementById('ill-download-spec-sheet');
    if (!btn) return;

    btn.addEventListener('click', async function (e) {
      e.preventDefault();

      var selections = getSelections();

      if (!hasMinimumSelections(selections)) {
        var productType = getProductType();
        var msg;
        if (productType === 'LED Sheet') {
          msg = 'Enter the Sheet coverage width and height, then select its specification and options.';
        } else if (isVariantProductType(productType)) {
          msg = 'Please complete your configuration before downloading a spec sheet.';
        } else if (productType === 'LED Neon' || productType === 'LED Tape') {
          msg = 'Please complete your configuration before downloading a spec sheet.\n\n' +
            'Required: CCT, Output, Finish, and Length.';
        } else {
          msg = 'Please complete your fixture configuration before downloading a spec sheet.\n\n' +
            'Required: Environment, CCT, Lens, Mounting, Finish, and Length.';
        }
        alert(msg);
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
      var fixtureTypeEl = document.getElementById('ill-fixture-type');

      var payload = {
        product_slug: productSlug,
        selections: JSON.stringify(selections),
        project_name: projectNameEl ? projectNameEl.value : '',
        project_location: projectLocationEl ? projectLocationEl.value : '',
        fixture_type: fixtureTypeEl ? fixtureTypeEl.value : ''
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
