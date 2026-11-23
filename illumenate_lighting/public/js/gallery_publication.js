/**
 * Gallery publication panel (plan 6): a brand picker, the readiness list and
 * the Approve and Stage / Publish Live / Retire / Retry buttons on the
 * ilL-Webflow-Gallery form. Every server string is escaped before it is
 * written into the panel. Mirrors public/js/product_publication.js.
 *
 * The same inspect result also drives a status pill on its own row at the top of the sidebar, placed the
 * way public/js/template_sidebar.js places its header block.
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
	var LABELS = ['Approve and Stage', 'Publish Live', 'Retire', 'Retry', 'View in Webflow'];
	// The Galleries collection page on the Webflow site is /gallery (its template page slug is detail_gallery).
	var GALLERY_PATH = '/gallery/';
	var SECTION = 'ill-gallery-publication-section';
	var PILL = 'ill-gallery-status';
	var HERO = 'ill-gallery-hero';

	// Sidebar status: the publication state of the chosen brand, in words a person can act on. Colours are
	// Frappe's indicator-pill classes.
	var STATUS = {
		needs_staging: { label: 'Needs staging', color: 'orange',
			hint: 'Not in Webflow yet. Approve and Stage to send it.' },
		changes: { label: 'Changes not staged', color: 'orange',
			hint: 'Edited since it was last staged. Approve and Stage again to send the changes.' },
		queued: { label: 'Queued', color: 'blue',
			hint: 'Waiting for the n8n workflow to pick it up.' },
		staged: { label: 'Staged', color: 'yellow',
			hint: 'Saved as a draft in Webflow. Publish Live to make it public.' },
		live: { label: 'Live', color: 'green', hint: 'Published on the Webflow site.' },
		failed: { label: 'Failed', color: 'red',
			hint: 'The last Webflow job failed. See the Webflow publication section for the error.' },
		retired: { label: 'Retired', color: 'gray', hint: 'Unpublished and archived in Webflow.' }
	};

	function esc(value) {
		return frappe.utils.escape_html(value == null ? '' : String(value));
	}

	function short(hash) {
		return esc((hash || '').slice(0, 12)) || '—';
	}

	// The status for an inspect result (the publication of the chosen brand), or null for none.
	// NEEDS_REVIEW (and READY) mean never staged, or edited since it was staged or live.
	function statusOf(result) {
		if (!result) return null;
		var key = {
			QUEUED: 'queued', STAGED: 'staged', LIVE: 'live', FAILED: 'failed', RETIRED: 'retired'
		}[result.state];
		if (!key) key = (result.staged_hash || result.live_hash) ? 'changes' : 'needs_staging';
		return { key: key, label: STATUS[key].label, color: STATUS[key].color, hint: STATUS[key].hint };
	}

	// Always one pill or none: removed and rebuilt on every render, first child of the sidebar.
	function setStatusPill(frm, status, brand) {
		var wrapper = frm.page && frm.page.wrapper;
		var side = wrapper && wrapper.find ? wrapper.find('.layout-side-section').first() : null;
		if (!side || !side.length) return;
		side.find('.' + PILL).remove();
		if (!status) return;
		var title = __(status.hint) + (brand ? ' (' + brand + ')' : '');
		side.prepend('<div class="' + PILL + '" style="padding: 0 15px; margin-top: 10px; margin-bottom: -10px;">' +
			'<span class="indicator-pill ' + esc(status.color) + '" title="' + esc(title) + '">' +
			esc(__(status.label)) + '</span></div>');
	}

	function node(tag, className, text) {
		var el = document.createElement(tag);
		if (className) el.className = className;
		if (text !== undefined) el.textContent = text;
		return el;
	}

	// The first image row is the hero (card thumbnail and detail hero). Shown above the table in the
	// Images section, in the same card style as the main image on the template forms.
	function setHeroPreview(frm) {
		var field = frm.fields_dict && frm.fields_dict.gallery_images;
		var host = field && field.$wrapper && field.$wrapper.get && field.$wrapper.get(0);
		if (!host || !host.parentNode) return;
		var old = host.parentNode.querySelector(':scope > .' + HERO);
		if (old) old.remove();
		var rows = (frm.doc.gallery_images || []).slice().sort(function (a, b) {
			return (a.idx || 0) - (b.idx || 0);
		});
		var first = rows[0];
		var card = node('div', HERO + ' frappe-card');
		card.style.cssText = 'padding:12px;margin-bottom:12px';
		card.appendChild(node('div', 'h6 text-uppercase text-muted',
			__('Hero image — the first row of the table below')));
		if (first && first.image) {
			var image = node('img');
			image.alt = first.alt_text || '';
			image.style.cssText = 'max-width:100%;max-height:240px;object-fit:contain;display:block;margin:8px 0';
			var badge = node('span', 'indicator-pill gray', __('Checking size…'));
			image.addEventListener('load', function () {
				badge.className = 'indicator-pill green';
				badge.textContent = image.naturalWidth + ' × ' + image.naturalHeight + ' px';
			});
			image.addEventListener('error', function () {
				badge.className = 'indicator-pill red';
				badge.textContent = __('Image could not be loaded');
			});
			image.src = first.image;
			card.appendChild(image);
			card.appendChild(badge);
			if (!String(first.alt_text || '').trim()) {
				card.appendChild(node('div', 'text-warning small', __('Add alt text for the hero image in the first row.')));
			}
		} else {
			card.appendChild(node('div', 'text-warning',
				__('No hero image yet. The image in the first row becomes the hero.')));
		}
		host.parentNode.insertBefore(card, host);
	}

	// The public address of a live gallery, or null when the brand has no usable site URL.
	function webflowUrl(siteUrl, slug) {
		var base = String(siteUrl || '').trim().replace(/\/+$/, '');
		if (!/^https?:\/\/[^\s]+$/i.test(base) || !slug) return null;
		return base + GALLERY_PATH + encodeURIComponent(slug);
	}

	// Opens the gallery's page on the brand's Webflow site. A staged draft has no public page yet.
	function viewInWebflow(frm, brand, live) {
		return async function () {
			if (!live) {
				frappe.msgprint(__('This gallery is not live in Webflow yet. Use Publish Live first, then it can be viewed.'));
				return;
			}
			var siteUrl = '';
			try {
				var found = await frappe.db.get_value('ilL-Webflow-Brand', brand, 'webflow_site_url');
				siteUrl = found && found.message && found.message.webflow_site_url;
			} catch (error) { siteUrl = ''; }
			var url = webflowUrl(siteUrl, frm.doc.slug);
			if (!url) {
				frappe.msgprint(__('Set the Webflow Site URL on the brand {0} to view galleries in Webflow.', [brand]));
				return;
			}
			window.open(url, '_blank', 'noopener');
		};
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
		// Rebuilt on every render, never cached on frm: Frappe reuses frm across documents. The panel lives in the
		// "Webflow publication" section at the bottom of the form (the publication_panel HTML field); a site that
		// has not migrated that field yet falls back to a dashboard section at the top (cleared on refresh by
		// Frappe, same pattern as desk_conversation.js).
		var host = panelHost(frm), panel, listener;
		if (host) {
			host.html('<div class="ill-gallery-publication"></div>');
			panel = host.find('.ill-gallery-publication');
			listener = host.off('change.illgallery');
		} else {
			var dashboard = frm.dashboard;
			if (dashboard.wrapper && dashboard.wrapper.find) dashboard.wrapper.find('.' + SECTION).remove();
			var section = dashboard.add_section('<div class="ill-gallery-publication"></div>', __('Webflow publication'), SECTION);
			if (dashboard.show) dashboard.show();
			panel = section.find('.ill-gallery-publication');
			if (!panel.length) panel = section;
			listener = panel;
		}
		panel.html(html);
		listener.on('change.illgallery', 'select.ill-gallery-brand', function () {
			frm.__ill_gallery_brand = this.value;
			render(frm);
		});
	}

	// The jQuery wrapper of the form's publication_panel field, or null when the form has none.
	function panelHost(frm) {
		var field = frm.fields_dict && frm.fields_dict.publication_panel;
		return field && field.$wrapper && field.$wrapper.length ? field.$wrapper : null;
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
		if (!brand) { setStatusPill(frm, null); renderPanel(frm, brands, '', null, null); return; }
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
			setStatusPill(frm, null);
			renderPanel(frm, brands, brand, null, null, errorText(error));
			return;
		}
		setStatusPill(frm, statusOf(result), brand);
		renderPanel(frm, brands, brand, result, job);
		var group = __('Publication');
		var stage = frm.add_custom_button(__('Approve and Stage'), request(frm, brand, 'STAGE'), group);
		if (stage && stage.prop) stage.prop('disabled', dirty);
		var publish = frm.add_custom_button(__('Publish Live'), request(frm, brand, 'PUBLISH'), group);
		// By hashes only, as on the product form: a save that changed nothing sent leaves the
		// state NEEDS_REVIEW until the next inspect, but the staged revision is still current.
		var ready = !!result.current_hash && result.approved_hash === result.current_hash &&
			result.staged_hash === result.current_hash && result.live_hash !== result.current_hash;
		if (publish && publish.prop) publish.prop('disabled', dirty || !ready);
		var retire = frm.add_custom_button(__('Retire'), request(frm, brand, 'RETIRE'), group);
		if (retire && retire.prop) retire.prop('disabled', dirty || !!frm.doc.is_active);
		frm.add_custom_button(__('View in Webflow'), viewInWebflow(frm, brand, !!result.live_hash && result.state !== 'RETIRED'), group);
		if (job && job.state === 'FAILED') {
			var retry = frm.add_custom_button(__('Retry'), guarded(frm, async function () {
				await call('retry', { job: job.name }, true);
			}), group);
			if (retry && retry.prop) retry.prop('disabled', dirty);
		}
	}

	async function refresh(frm) {
		setHeroPreview(frm);
		if (frm.fields_dict && frm.fields_dict.gallery_images && frm.fields_dict.gallery_images.set_description) {
			frm.fields_dict.gallery_images.set_description(__('The first row is always the hero image.'));
		}
		if (frm.is_new()) {
			setStatusPill(frm, null);
			var host = panelHost(frm);
			if (host) host.html('<p class="text-muted">' + esc(__('Save the gallery to see its Webflow publication status.')) + '</p>');
			return;
		}
		await render(frm);
	}

	return { refresh: refresh, statusOf: statusOf, setHeroPreview: setHeroPreview, webflowUrl: webflowUrl };
}));
