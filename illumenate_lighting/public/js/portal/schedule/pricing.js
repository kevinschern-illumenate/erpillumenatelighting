// Schedule detail page (pricing). Extracted verbatim from templates/pages/schedule.html (plan 2.1).
// ----------------------------------------------------------------------------
// Dealer pricing toggle
// ----------------------------------------------------------------------------
var dealerPricingActive = false;
var dealerPricingData = null;  // cached after first successful fetch
var dealerCustomerGroup = scheduleContext.dealer_customer_group;

function toggleDealerPricing() {
	if (dealerPricingActive) {
		restoreMsrpPricing();
	} else if (dealerPricingData) {
		applyDealerPricing(dealerPricingData);
	} else {
		fetchDealerPricing();
	}
}

function fetchDealerPricing() {
	var btn = document.getElementById('dealerPricingBtn');
	btn.disabled = true;
	btn.innerHTML = '<i class="fa fa-spinner fa-spin" aria-hidden="true"></i> ' + __('Loading...');

	frappe.call({
		method: 'illumenate_lighting.illumenate_lighting.api.portal.get_schedule_dealer_pricing',
		args: { schedule_name: schedule_name },
		callback: function(r) {
			btn.disabled = false;
			if (r.message && r.message.lines) {
				dealerPricingData = r.message;
				applyDealerPricing(r.message);
			} else if (r.message && r.message.error) {
				var messages = {
					'no_customer_linked': __('Your account is not yet linked to a customer record. Contact your administrator.'),
					'no_customer_group': __('No customer group is configured for your account. Contact your administrator.')
				};
				frappe.msgprint(messages[r.message.error] || (__('Could not load dealer pricing: ') + r.message.error));
				btn.innerHTML = '<i class="fa fa-tag" aria-hidden="true"></i> ' + __('Show Dealer Pricing');
			} else {
				btn.innerHTML = '<i class="fa fa-tag" aria-hidden="true"></i> ' + __('Show Dealer Pricing');
			}
		},
		error: function() {
			btn.disabled = false;
			btn.innerHTML = '<i class="fa fa-tag" aria-hidden="true"></i> ' + __('Show Dealer Pricing');
		}
	});
}

function _formatMoney(value) {
	return '$' + Number(value).toFixed(2);
}

function _escapeHtml(text) {
	var div = document.createElement('div');
	div.appendChild(document.createTextNode(text == null ? '' : String(text)));
	return div.innerHTML;
}

function applyDealerPricing(data) {
	var lines = data.lines || {};
	document.querySelectorAll('td.dealer-pricing-cell').forEach(function(cell) {
		var idx = cell.getAttribute('data-line-idx');
		var priceType = cell.getAttribute('data-price-type');
		var lineData = lines[idx];
		if (!lineData) { return; }

		var mainSpan = cell.querySelector('.dealer-price-value');
		var driverSpan = cell.querySelector('.dealer-price-driver');

		if (mainSpan) {
			var mainVal = (priceType === 'unit') ? lineData.tier_unit : lineData.line_total_tier;
			if (mainVal !== null && mainVal !== undefined) {
				mainSpan.textContent = _formatMoney(mainVal);
			}
		}
		if (driverSpan && lineData.driver_msrp_unit) {
			var driverVal;
			if (priceType === 'unit') {
				driverVal = lineData.driver_tier_unit;
			} else {
				// Scale the stored driver line-total MSRP by the driver tier ratio.
				var ratio = lineData.driver_msrp_unit ? (lineData.driver_tier_unit / lineData.driver_msrp_unit) : 1;
				var driverMsrpTotal = parseFloat(driverSpan.getAttribute('data-msrp-value'));
				driverVal = driverMsrpTotal * ratio;
			}
			if (driverVal !== null && driverVal !== undefined) {
				driverSpan.textContent = _formatMoney(driverVal);
			}
		}
	});

	// Schedule total: show dealer total with MSRP reference.
	var totalSpan = document.querySelector('.dealer-total-value');
	if (totalSpan && data.schedule_total_tier !== undefined) {
		var msrpTotal = parseFloat(totalSpan.getAttribute('data-msrp-value'));
		totalSpan.innerHTML = _formatMoney(data.schedule_total_tier) +
			' <span class="text-muted small">(' + __('MSRP') + ': ' + _formatMoney(msrpTotal) + ')</span>';
	}

	// Column header suffixes.
	_setHeaderDealerSuffix(true);

	// Button + label state.
	var btn = document.getElementById('dealerPricingBtn');
	btn.classList.remove('btn-outline-warning');
	btn.classList.add('btn-warning');
	var groupLabel = data.customer_group || dealerCustomerGroup || '';
	btn.innerHTML = '<i class="fa fa-tag" aria-hidden="true"></i> ' + __('Showing Dealer Pricing') +
		(groupLabel ? ' (' + _escapeHtml(groupLabel) + ')' : '');

	var label = document.getElementById('dealerPricingModeLabel');
	if (label) {
		var pct = Number(data.discount_percentage || 0).toFixed(1);
		if (Number(data.discount_percentage || 0) > 0) {
			label.textContent = __('Dealer price for Customer Group') + ': ' + (groupLabel || '') +
				' \u2014 ' + pct + '% ' + __('discount');
		} else {
			label.textContent = __('No dealer discount configured for your account');
		}
		// The portal applies the customer-group rule only; ERPNext prices the
		// order with its full pricing engine when the request is created.
		label.textContent += ' \u2014 ' + __('estimate; final pricing is confirmed on your order request');
		label.style.display = '';
	}

	dealerPricingActive = true;
}

function restoreMsrpPricing() {
	document.querySelectorAll('td.dealer-pricing-cell').forEach(function(cell) {
		cell.querySelectorAll('.dealer-price-value, .dealer-price-driver').forEach(function(span) {
			var msrp = span.getAttribute('data-msrp-value');
			if (msrp !== null) {
				span.textContent = _formatMoney(msrp);
			}
		});
	});

	var totalSpan = document.querySelector('.dealer-total-value');
	if (totalSpan) {
		var msrpTotal = totalSpan.getAttribute('data-msrp-value');
		if (msrpTotal !== null) {
			totalSpan.textContent = _formatMoney(msrpTotal);
		}
	}

	_setHeaderDealerSuffix(false);

	var btn = document.getElementById('dealerPricingBtn');
	btn.classList.remove('btn-warning');
	btn.classList.add('btn-outline-warning');
	btn.innerHTML = '<i class="fa fa-tag" aria-hidden="true"></i> ' + __('Show Dealer Pricing');

	var label = document.getElementById('dealerPricingModeLabel');
	if (label) {
		label.style.display = 'none';
	}

	dealerPricingActive = false;
}

function _setHeaderDealerSuffix(active) {
	var unitTh = document.getElementById('unitPriceHeader');
	if (unitTh) {
		unitTh.textContent = active ? __('Dealer Price') : __('Unit Price');
	}
	// Line Total header stays unchanged in both modes
}
