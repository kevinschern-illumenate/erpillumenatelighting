/**
 * BOM Review Renderer (Phase 5)
 *
 * Pure helper that renders a BOM table inside a wrapper element.  Used by
 * `desk_dialog.js` for the BOM-review step and reusable from any other
 * desk-side surface (manufacturing review, item detail, etc.).
 *
 * Exposes:
 *   IllDesk.renderBOMReview($wrapper, items, opts)
 *     $wrapper : jQuery element to render into
 *     items    : array of { item_code, item_name, qty, uom, description }
 *     opts     : { messages: [], title: string, empty_message: string }
 *
 *   IllDesk.renderPricingBreakdown($wrapper, validation, opts)
 *     Renders a collapsible pricing/computed summary from a calculate
 *     response.
 */
(function (root) {
	'use strict';

	var IllDesk = root.IllDesk = root.IllDesk || {};

	function escapeHtml(value) {
		return $('<div>').text(value == null ? '' : String(value)).html();
	}

	function fmtNumber(n, decimals) {
		if (n == null || isNaN(n)) return '-';
		var d = (decimals == null) ? 2 : decimals;
		return Number(n).toFixed(d);
	}

	function fmtCurrency(n) {
		if (n == null || isNaN(n)) return '-';
		return '$' + Number(n).toFixed(2);
	}

	IllDesk.renderBOMReview = function ($wrapper, items, opts) {
		opts = opts || {};
		var $w = $wrapper.jquery ? $wrapper : $($wrapper);
		$w.empty();

		if (opts.title) {
			$w.append($('<h6></h6>').text(opts.title));
		}

		var msgs = opts.messages || [];
		if (msgs.length) {
			var $msgBox = $('<div class="bom-review-messages mb-2"></div>');
			msgs.forEach(function (m) {
				var sev = (m && m.severity) || 'info';
				var cls = (sev === 'error') ? 'alert-danger'
					: (sev === 'warning') ? 'alert-warning'
					: 'alert-info';
				$msgBox.append(
					$('<div></div>')
						.addClass('alert ' + cls + ' py-1 px-2 small mb-1')
						.text((m && m.text) || '')
				);
			});
			$w.append($msgBox);
		}

		if (!items || !items.length) {
			$w.append(
				'<div class="text-muted small">'
				+ escapeHtml(opts.empty_message || __('No BOM rows to display.'))
				+ '</div>'
			);
			return;
		}

		var rows = items.map(function (it) {
			return '<tr>'
				+ '<td>' + escapeHtml(it.item_code || '') + '</td>'
				+ '<td>' + escapeHtml(it.item_name || it.description || '') + '</td>'
				+ '<td class="text-right">' + escapeHtml(fmtNumber(it.qty, 3)) + '</td>'
				+ '<td>' + escapeHtml(it.uom || it.stock_uom || '') + '</td>'
				+ '</tr>';
		}).join('');

		var html = '<div class="table-responsive" style="max-height: 320px; overflow:auto;">'
			+   '<table class="table table-bordered table-condensed table-sm mb-1">'
			+     '<thead class="thead-light"><tr>'
			+       '<th>' + __('Item') + '</th>'
			+       '<th>' + __('Name') + '</th>'
			+       '<th class="text-right">' + __('Qty') + '</th>'
			+       '<th>' + __('UOM') + '</th>'
			+     '</tr></thead>'
			+     '<tbody>' + rows + '</tbody>'
			+   '</table>'
			+ '</div>'
			+ '<div class="text-muted small">' + __('{0} BOM rows', [items.length]) + '</div>';
		$w.append(html);
	};

	IllDesk.renderPricingBreakdown = function ($wrapper, validation, opts) {
		opts = opts || {};
		var $w = $wrapper.jquery ? $wrapper : $($wrapper);
		$w.empty();

		validation = validation || {};
		var pricing = validation.pricing || validation.pricing_breakdown || {};
		var computed = validation.computed || {};

		var summaryRows = [];
		if (validation.part_number || validation.candidate_part_number) {
			summaryRows.push([__('Part Number'),
				escapeHtml(validation.part_number || validation.candidate_part_number)]);
		}
		if (computed.manufacturable_overall_length_mm || computed.manufacturable_length_mm) {
			var mm = computed.manufacturable_overall_length_mm || computed.manufacturable_length_mm;
			summaryRows.push([__('Mfg Length'),
				fmtNumber(mm / 25.4) + '" (' + fmtNumber(mm / 304.8) + ' ft)']);
		}
		if (computed.requested_length_mm || computed.requested_overall_length_mm) {
			var rmm = computed.requested_length_mm || computed.requested_overall_length_mm;
			summaryRows.push([__('Requested Length'), fmtNumber(rmm / 25.4) + '"']);
		}
		if (computed.total_watts != null) {
			summaryRows.push([__('Total Watts'), fmtNumber(computed.total_watts) + ' W']);
		}
		if (computed.runs_count) {
			summaryRows.push([__('Runs'), computed.runs_count]);
		}
		if (computed.segment_count) {
			summaryRows.push([__('Segments'), computed.segment_count]);
		}

		if (summaryRows.length) {
			var $summary = $('<table class="table table-sm table-borderless mb-2"><tbody></tbody></table>');
			var $tbody = $summary.find('tbody');
			summaryRows.forEach(function (r) {
				$tbody.append(
					'<tr>'
					+ '<th class="small text-muted" style="width:40%;">' + r[0] + '</th>'
					+ '<td class="small">' + r[1] + '</td>'
					+ '</tr>'
				);
			});
			$w.append($summary);
		}

		// ── Collapsible pricing breakdown ──
		var hasPricing = pricing && (
			pricing.total_msrp != null
			|| pricing.subtotal_msrp != null
			|| (pricing.line_items && pricing.line_items.length)
			|| (pricing.adders && pricing.adders.length)
		);
		if (!hasPricing) return;

		var collapseId = 'ill-pricing-collapse-' + Math.floor(Math.random() * 1e9);
		var headerLabel = __('Pricing breakdown');
		if (pricing.total_msrp != null) {
			headerLabel += ' — ' + fmtCurrency(pricing.total_msrp);
		}

		var $card = $(
			'<div class="card mb-2">'
			+   '<div class="card-header py-1 px-2 small" style="cursor:pointer;" data-toggle="collapse" data-target="#' + collapseId + '">'
			+     '<i class="fa fa-chevron-right mr-1"></i>'
			+     '<strong>' + escapeHtml(headerLabel) + '</strong>'
			+   '</div>'
			+   '<div id="' + collapseId + '" class="collapse">'
			+     '<div class="card-body p-2"></div>'
			+   '</div>'
			+ '</div>'
		);
		var $body = $card.find('.card-body');

		if (pricing.line_items && pricing.line_items.length) {
			var lineRows = pricing.line_items.map(function (li) {
				return '<tr>'
					+ '<td>' + escapeHtml(li.label || li.item_code || '') + '</td>'
					+ '<td class="text-right">' + escapeHtml(fmtNumber(li.qty, 3)) + '</td>'
					+ '<td class="text-right">' + escapeHtml(fmtCurrency(li.unit_msrp)) + '</td>'
					+ '<td class="text-right">' + escapeHtml(fmtCurrency(li.total_msrp)) + '</td>'
					+ '</tr>';
			}).join('');
			$body.append(
				'<table class="table table-sm table-bordered mb-1">'
				+ '<thead class="thead-light"><tr>'
				+ '<th>' + __('Component') + '</th>'
				+ '<th class="text-right">' + __('Qty') + '</th>'
				+ '<th class="text-right">' + __('Unit') + '</th>'
				+ '<th class="text-right">' + __('Total') + '</th>'
				+ '</tr></thead><tbody>' + lineRows + '</tbody></table>'
			);
		}

		if (pricing.adders && pricing.adders.length) {
			var adderRows = pricing.adders.map(function (a) {
				return '<tr><td>' + escapeHtml(a.label || a.code || '')
					+ '</td><td class="text-right">' + escapeHtml(fmtCurrency(a.amount)) + '</td></tr>';
			}).join('');
			$body.append(
				'<div class="small text-muted mb-1">' + __('Option adders') + '</div>'
				+ '<table class="table table-sm mb-2">'
				+ '<tbody>' + adderRows + '</tbody></table>'
			);
		}

		var totalRows = [];
		if (pricing.subtotal_msrp != null) {
			totalRows.push([__('Subtotal'), fmtCurrency(pricing.subtotal_msrp)]);
		}
		if (pricing.length_adder_msrp != null) {
			totalRows.push([__('Length Adder'), fmtCurrency(pricing.length_adder_msrp)]);
		}
		if (pricing.total_msrp != null) {
			totalRows.push(['<strong>' + __('Total MSRP') + '</strong>',
				'<strong>' + fmtCurrency(pricing.total_msrp) + '</strong>']);
		}
		if (totalRows.length) {
			var $tot = $('<table class="table table-sm mb-0"><tbody></tbody></table>');
			var $totBody = $tot.find('tbody');
			totalRows.forEach(function (r) {
				$totBody.append('<tr><td>' + r[0] + '</td><td class="text-right">' + r[1] + '</td></tr>');
			});
			$body.append($tot);
		}

		$w.append($card);

		// Toggle chevron icon
		$card.find('.card-header').on('click', function () {
			var $i = $(this).find('i.fa');
			setTimeout(function () {
				if ($card.find('.collapse').hasClass('show')) {
					$i.removeClass('fa-chevron-right').addClass('fa-chevron-down');
				} else {
					$i.removeClass('fa-chevron-down').addClass('fa-chevron-right');
				}
			}, 50);
		});
	};

}(window));
