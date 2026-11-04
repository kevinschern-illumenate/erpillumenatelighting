/**
 * Configurator estimate panel (plan 3.8).
 *
 * The configurators already show the part number, price and stock their validation returns. This
 * panel adds the lead-time class and labels it all as an estimate that the quote confirms. The
 * page renders #ill-live-estimate only while the ill_portal_live_estimate kill switch is on.
 * Without it nothing is drawn and no request is made. Text is set with .text() only.
 *
 *   IllConfigurator.renderEstimate(host, {
 *     family,         // fixture | tape_neon | led_sheet | kit | driver | controller
 *     template,       // template name (led_sheet, driver, controller)
 *     tape_offering,  // resolved tape offering (fixture, tape_neon)
 *     schedule_name,  // the schedule a collaborator configures for
 *     show_pricing,   // the page's pricing visibility
 *     price,          // optional estimated total; null = no current price
 *     lead_time       // optional, when the validation already resolved it (tape/neon)
 *   })
 */
(function (root) {
	'use strict';
	var IllConfigurator = root.IllConfigurator = root.IllConfigurator || {};
	var METHOD = 'illumenate_lighting.illumenate_lighting.portal.estimate.lead_time';
	var TEMPLATE_FAMILIES = { led_sheet: 1, driver: 1, controller: 1 };
	var OFFERING_FAMILIES = { fixture: 1, tape_neon: 1 };
	var cache = {};
	var sequence = 0;

	function $(value) { return root.jQuery(value); }
	function text(value, args) {
		if (root.__) return root.__(value, args);
		return String(value).replace(/\{(\d+)\}/g, function (match, index) { return args && args[index] != null ? args[index] : match; });
	}

	function enabled() {
		var node = root.document && root.document.getElementById('ill-live-estimate');
		if (!node) return false;
		try {
			var parsed = JSON.parse(node.textContent || '{}');
			return !!(parsed && parsed.enabled);
		} catch (_) { return false; }
	}

	function days(value) {
		var number = Number(value);
		return value == null || value === '' || !isFinite(number) ? null : number;
	}

	// "Standard · 10–15 days"; no class means the quote states the lead time.
	function leadTimeText(leadTime) {
		if (!leadTime) return text('Confirmed on your quote');
		var low = days(leadTime.days_min), high = days(leadTime.days_max), span = '';
		if (low != null && high != null) span = low === high ? text('{0} days', [low]) : text('{0}–{1} days', [low, high]);
		else if (high != null) span = text('Up to {0} days', [high]);
		else if (low != null) span = text('{0}+ days', [low]);
		var label = String(leadTime.label || leadTime.code || '');
		return label && span ? label + ' · ' + span : (label || span || text('Confirmed on your quote'));
	}

	function lookup(options) {
		var family = options.family;
		if (TEMPLATE_FAMILIES[family]) return options.template ? { family: family, template: options.template } : null;
		if (OFFERING_FAMILIES[family]) return options.tape_offering ? { family: family, tape_offering: options.tape_offering } : null;
		return null;
	}

	function row(className, label) {
		var $value = $('<strong></strong>');
		var $row = $('<div class="d-flex justify-content-between"></div>').addClass(className)
			.append($('<span class="text-muted"></span>').text(label), $value);
		return { $row: $row, $value: $value };
	}

	function fetchLeadTime(args, schedule, done) {
		var key = JSON.stringify([args.family, args.template || '', args.tape_offering || '']);
		if (Object.prototype.hasOwnProperty.call(cache, key)) { done(cache[key]); return; }
		if (!root.frappe || !root.frappe.call) { done(null); return; }
		var request = { family: args.family };
		if (args.template) request.template = args.template;
		if (args.tape_offering) request.tape_offering = args.tape_offering;
		if (schedule) request.schedule_name = schedule;
		root.frappe.call({
			method: METHOD, type: 'GET', args: request,
			callback: function (r) {
				var value = (r && r.message && r.message.lead_time) || null;
				cache[key] = value;
				done(value);
			},
			error: function () { done(null); }
		});
	}

	function renderEstimate(host, options) {
		var $host = $(host);
		$host.children('.ill-estimate').remove();
		if (!enabled() || !$host.length) return null;
		options = options || {};
		var token = String(++sequence);
		var $panel = $('<div class="ill-estimate small border-top pt-2 mt-2" role="note"></div>').attr('data-estimate', token);
		$panel.append($('<div class="ill-estimate-title font-weight-bold mb-1"></div>').text(text('Estimate — confirmed on your quote')));
		if (options.show_pricing && options.price !== undefined) {
			var price = row('ill-estimate-price', text('Estimated price'));
			var amount = options.price == null ? NaN : Number(options.price);
			price.$value.text(isFinite(amount) ? '$' + amount.toFixed(2) : text('Confirmed on your quote'));
			$panel.append(price.$row);
		}
		var lead = row('ill-estimate-lead', text('Lead time'));
		$panel.append(lead.$row);
		$host.append($panel);

		if (options.lead_time !== undefined) {
			lead.$value.text(leadTimeText(options.lead_time));
			return $panel;
		}
		var args = lookup(options);
		if (!args) { lead.$value.text(leadTimeText(null)); return $panel; }
		lead.$value.text(text('Loading…'));
		fetchLeadTime(args, options.schedule_name, function (value) {
			// A newer result may have replaced this panel while the request was in flight.
			if ($panel.attr('data-estimate') !== token || !$panel.closest('body').length) return;
			lead.$value.text(leadTimeText(value));
		});
		return $panel;
	}

	IllConfigurator.estimateEnabled = enabled;
	IllConfigurator.renderEstimate = renderEstimate;
	IllConfigurator.estimateLeadTimeText = leadTimeText;
	IllConfigurator._resetEstimateCache = function () { cache = {}; };
})(typeof window !== 'undefined' ? window : this);
