/**
 * Gallery publication panel (plan 6): a brand picker, the readiness list and
 * the Approve and Stage / Publish Live / Retire / Retry buttons on the
 * ilL-Webflow-Gallery form. Every server string is escaped before it is
 * written into the panel. Mirrors public/js/product_publication.js.
 */
(function (root, factory) {
	'use strict';
	var api = factory(root);
	if (typeof module === 'object' && module.exports) module.exports = api;
	if (root) root.IllGalleryPublication = api;
}(typeof window !== 'undefined' ? window : null, function () {
	'use strict';

	var API = 'illumenate_lighting.illumenate_lighting.api.gallery_publication.';
	var JOB = 'ilL-Gallery-Publish-Job';
	var LABELS = ['Approve and Stage', 'Publish Live', 'Retire', 'Retry'];

	function esc(value) {
		return frappe.utils.escape_html(value == null ? '' : String(value));
	}

	function short(hash) {
		return esc((hash || '').slice(0, 12)) || '—';
	}

	function call(method, args, freeze) {
		var options = { method: API + method, type: 'POST', args: args };
		if (freeze) options.freeze = true;
		return frappe.call(options);
	}

	function errorText(error) {
		return (error && error.message) || __('The request failed. Correct the reported error and retry.');
	}

	async function brandChoices() {
		return frappe.db.get_list('ilL-Webflow-Brand', {
			filters: { is_active: 1, sync_enabled: 1 },
			fields: ['name', 'is_default'],
			limit: 0,
		});
	}

	// First enabled target brand of the gallery, else the default brand.
	function defaultBrand(frm, brands) {
		var names = brands.map(function (row) { return row.name; });
		var rows = (frm.doc.target_brands || []).filter(function (row) { return row.enabled && row.brand; });
		var target = rows.filter(function (row) { return !names.length || names.indexOf(row.brand) >= 0; })[0];
		if (target) return target.brand;
		var fallback = brands.filter(function (row) { return row.is_default; })[0] || brands[0];
		return fallback ? fallback.name : '';
	}

	function renderPanel(frm, brands, brand, result, job, error) {
		var html = '<p><label>' + esc(__('Brand')) + ' <select class="form-control input-sm ill-gallery-brand">' +
			brands.map(function (row) {
				return '<option value="' + esc(row.name) + '"' + (row.name === brand ? ' selected' : '') + '>' + esc(row.name) + '</option>';
			}).join('') + '</select></label></p>';
		if (!brand) {
			html = '<p class="text-muted">' + esc(__('No Webflow brand is enabled for this gallery.')) + '</p>';
		}
		if (error) {
			html += '<p class="text-danger">' + esc(__('Inspection failed')) + ': ' + esc(error) + '</p>';
		}
		if (result) {
			var readiness = result.readiness || {};
			html += '<p>' + esc(result.state) + ' &middot; ' + short(result.current_hash) + '</p>';
			(readiness.issues || []).forEach(function (issue) {
				html += '<p class="text-danger">' + esc(issue.record) + ' / ' + esc(issue.field) + ': ' + esc(issue.message) + '</p>';
			});
			(readiness.warnings || []).forEach(function (warning) {
				html += '<p class="text-muted">' + esc(__('Warning')) + ': ' + esc(warning.record) + ' / ' + esc(warning.field) + ': ' + esc(warning.message) + '</p>';
			});
			html += '<p>' + esc(__('Staged revision')) + ': ' + short(result.staged_hash) + '<br>' +
				esc(__('Live revision')) + ': ' + short(result.live_hash) + '</p>';
		}
		if (job && job.state === 'FAILED') {
			html += '<p class="text-danger">' + esc(__('Last job failed')) + ' (' + esc(job.operation) + '): ' + esc(job.last_error) + '</p>';
		}
		var panel = frm.__ill_gallery_panel;
		if (!panel) {
			panel = frm.__ill_gallery_panel = frm.dashboard.add_section('<div class="ill-gallery-publication"></div>');
		}
		panel.html(html);
		panel.off('change.illgallery').on('change.illgallery', 'select.ill-gallery-brand', function () {
			frm.__ill_gallery_brand = this.value;
			render(frm);
		});
	}

	// One action at a time, only on a saved form; failures are shown, never thrown.
	function guarded(frm, action) {
		return async function () {
			if (frm.__ill_gallery_busy) return;
			if (frm.is_dirty()) {
				frappe.msgprint(esc(__('Save the gallery first.')));
				return;
			}
			frm.__ill_gallery_busy = true;
			try {
				await action();
				await frm.reload_doc();
			} catch (error) {
				frappe.msgprint(esc(errorText(error)));
				await render(frm);
			} finally {
				frm.__ill_gallery_busy = false;
			}
		};
	}

	function request(frm, brand, operation) {
		return guarded(frm, async function () {
			var current = await call('inspect', { gallery: frm.doc.name, brand: brand });
			var receipt = await call('request', {
				gallery: frm.doc.name, brand: brand, operation: operation,
				expected_hash: current.message.current_hash,
			}, true);
			frappe.show_alert({ message: __('Publication job: {0}', [receipt.message.job]), indicator: 'green' });
		});
	}

	async function render(frm) {
		LABELS.forEach(function (label) {
			if (frm.remove_custom_button) frm.remove_custom_button(__(label), __('Publication'));
		});
		var brands = await brandChoices();
		var brand = frm.__ill_gallery_brand || defaultBrand(frm, brands);
		if (!brand) { renderPanel(frm, brands, '', null, null); return; }
		var dirty = !!frm.is_dirty();
		var result, job;
		try {
			result = (await call('inspect', { gallery: frm.doc.name, brand: brand })).message;
			job = (await frappe.db.get_list(JOB, {
				filters: { gallery: frm.doc.name, brand: brand },
				fields: ['name', 'state', 'operation', 'last_error', 'next_attempt_on'],
				order_by: 'creation desc', limit: 1,
			}))[0];
		} catch (error) {
			renderPanel(frm, brands, brand, null, null, errorText(error));
			return;
		}
		renderPanel(frm, brands, brand, result, job);
		var group = __('Publication');
		var stage = frm.add_custom_button(__('Approve and Stage'), request(frm, brand, 'STAGE'), group);
		if (stage && stage.prop) stage.prop('disabled', dirty);
		var publish = frm.add_custom_button(__('Publish Live'), request(frm, brand, 'PUBLISH'), group);
		var ready = result.state === 'STAGED' && !!result.current_hash &&
			result.approved_hash === result.current_hash && result.staged_hash === result.current_hash;
		if (publish && publish.prop) publish.prop('disabled', dirty || !ready);
		var retire = frm.add_custom_button(__('Retire'), request(frm, brand, 'RETIRE'), group);
		if (retire && retire.prop) retire.prop('disabled', dirty || !!frm.doc.is_active);
		if (job && job.state === 'FAILED') {
			var retry = frm.add_custom_button(__('Retry'), guarded(frm, async function () {
				await call('retry', { job: job.name }, true);
			}), group);
			if (retry && retry.prop) retry.prop('disabled', dirty);
		}
	}

	async function refresh(frm) {
		if (frm.fields_dict && frm.fields_dict.gallery_images && frm.fields_dict.gallery_images.set_description) {
			frm.fields_dict.gallery_images.set_description(__('The first row is always the hero image.'));
		}
		if (frm.is_new()) return;
		await render(frm);
	}

	return { refresh: refresh };
}));
