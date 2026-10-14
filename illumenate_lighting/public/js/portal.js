/**
 * ilLumenate Lighting Portal JavaScript
 * Global JavaScript utilities for all portal pages
 */

(function() {
	'use strict';

	// Portal namespace
	window.IlluminatePortal = window.IlluminatePortal || {};

	/**
	 * Initialize portal functionality
	 */
	IlluminatePortal.init = function() {
		this.initTooltips();
		this.initLoadingStates();
		this.initFormValidation();
        document.querySelectorAll('.ill-portal-navigation a').forEach(function (link) {
            if (link.pathname === location.pathname) link.setAttribute('aria-current', 'page');
        });
        if (typeof $ !== 'undefined') {
            const returnFocus = new WeakMap();
            $(document).off('.illPortalFocus').on('show.bs.modal.illPortalFocus', '.modal', function () { returnFocus.set(this, document.activeElement); })
                .on('shown.bs.modal.illPortalFocus', '.modal', function () { const input = this.querySelector('input:not([type="hidden"]), select, textarea, button'); if (input) input.focus(); })
                .on('hidden.bs.modal.illPortalFocus', '.modal', function () { const previous = returnFocus.get(this); if (previous && previous.isConnected) previous.focus(); });
        }
	};

	/**
	 * Initialize Bootstrap tooltips
	 */
	IlluminatePortal.initTooltips = function() {
		if (typeof $ !== 'undefined' && $.fn.tooltip) {
			$('[data-toggle="tooltip"]').tooltip();
		}
	};

	/**
	 * Handle loading states for buttons
	 */
	IlluminatePortal.initLoadingStates = function() {
		document.querySelectorAll('[data-loading-text]').forEach(function(btn) {
			btn.addEventListener('click', function() {
				const originalText = this.innerHTML;
				const loadingText = this.dataset.loadingText || 'Loading...';
				
				this.disabled = true;
				this.innerHTML = '<i class="fa fa-spinner fa-spin"></i> ' + loadingText;
				
				this.dataset.originalText = originalText;
			});
		});
	};

	/**
	 * Reset button loading state
	 */
	IlluminatePortal.resetButton = function(btn) {
		if (btn.dataset.originalText) {
			btn.innerHTML = btn.dataset.originalText;
			btn.disabled = false;
		}
	};

	/**
	 * Initialize form validation
	 */
	IlluminatePortal.initFormValidation = function() {
		document.querySelectorAll('form[data-validate]').forEach(function(form) {
			form.addEventListener('submit', function(e) {
				if (!form.checkValidity()) {
					e.preventDefault();
					e.stopPropagation();
				}
				form.classList.add('was-validated');
			});
		});
	};

	/**
	 * Show a toast notification
	 */
	IlluminatePortal.showToast = function(message, type) {
		type = type || 'info';
		
		const toast = document.createElement('div');
		toast.className = 'portal-toast portal-toast-' + type;
		toast.innerHTML = `
			<div class="toast-content">
				<i class="fa ${type === 'success' ? 'fa-check-circle' : type === 'error' ? 'fa-exclamation-circle' : 'fa-info-circle'}"></i>
				<span>${message}</span>
			</div>
		`;
		
		document.body.appendChild(toast);
		
		// Animate in
		setTimeout(function() {
			toast.classList.add('show');
		}, 10);
		
		// Remove after delay
		setTimeout(function() {
			toast.classList.remove('show');
			setTimeout(function() {
				toast.remove();
			}, 300);
		}, 3000);
	};

	/**
	 * Format currency
	 */
	IlluminatePortal.formatCurrency = function(value, currency) {
		currency = currency || 'USD';
		return new Intl.NumberFormat('en-US', {
			style: 'currency',
			currency: currency
		}).format(value);
	};

	/**
	 * Format date
	 */
	IlluminatePortal.formatDate = function(date, format) {
		if (!date) return '-';
		const d = new Date(date);
		return d.toLocaleDateString('en-US', {
			year: 'numeric',
			month: 'short',
			day: 'numeric'
		});
	};

	/**
	 * Debounce function for search inputs
	 */
	IlluminatePortal.debounce = function(func, wait) {
		let timeout;
		return function executedFunction(...args) {
			const later = function() {
				clearTimeout(timeout);
				func(...args);
			};
			clearTimeout(timeout);
			timeout = setTimeout(later, wait);
		};
	};

	/**
	 * Copy text to clipboard
	 */
	IlluminatePortal.copyToClipboard = function(text) {
		if (navigator.clipboard) {
			navigator.clipboard.writeText(text).then(function() {
				IlluminatePortal.showToast('Copied to clipboard', 'success');
			});
		} else {
			// Fallback for older browsers
			const textArea = document.createElement('textarea');
			textArea.value = text;
			document.body.appendChild(textArea);
			textArea.select();
			document.execCommand('copy');
			document.body.removeChild(textArea);
			IlluminatePortal.showToast('Copied to clipboard', 'success');
		}
	};

	/**
	 * Confirm dialog
	 */
	IlluminatePortal.confirm = function(message, callback) {
		frappe.confirm(message, callback);
	};

	/**
	 * API call wrapper
	 */
	IlluminatePortal.call = function(method, args, callback) {
		return frappe.call({
			method: 'illumenate_lighting.illumenate_lighting.api.portal.' + method,
			args: args,
			freeze: true,
			callback: function(r) {
				if (r.message && r.message.success) {
					if (callback) callback(null, r.message);
				} else {
					const error = r.message?.error || 'An error occurred';
					frappe.msgprint({
						title: 'Error',
						indicator: 'red',
						message: error
					});
					if (callback) callback(error, null);
				}
			}
		});
	};

	// Initialize on DOM ready
	document.addEventListener('DOMContentLoaded', function() {
		IlluminatePortal.init();
	});

})();
