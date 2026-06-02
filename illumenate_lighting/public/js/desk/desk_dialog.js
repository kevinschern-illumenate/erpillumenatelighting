/**
 * Desk Configurator Dialog (Phase D – embedded portal configurator)
 *
 * "Configure & Add Fixture" Tools button for Quotation and Sales Order.
 * Instead of a bespoke desk wizard, this mounts the SAME scoped portal
 * configurator classes (IllConfigurator.Fixture / IllConfigurator.TapeNeon)
 * inside a Frappe modal so the desk experience matches the portal exactly.
 *
 * Flow:
 *
 *   pickType  → user picks Linear Fixture / LED Tape / LED Neon + qty
 *      ↓ Continue
 *   configure → server-rendered configurator markup
 *               (configured_product_builder.get_configurator_markup) is mounted
 *               into a `.ill-configurator.ill-desk-configurator` host and the
 *               matching scoped class is instantiated against it. The class's
 *               own Validate / Calculate / Add / Save buttons drive the flow.
 *      ↓ (the configurator's Add/Save button → context.saveHandler)
 *   save      → save_and_apply_from_portal writes the row, frm.reload_doc(),
 *               dialog closes.
 *
 * The configurator markup uses data-action buttons bound instance-locally by
 * the scoped classes, so the embedded instance never collides with any other
 * configurator instance.
 *
 * Public API (consumed by the quote_order_configurator.js shim):
 *   IllDesk.addConfiguratorButton(frm)
 *   IllDesk.openConfiguratorDialog(frm, opts)
 */
(function (root) {
	'use strict';

	var IllDesk = root.IllDesk = root.IllDesk || {};
	var CONFIG_API = 'illumenate_lighting.illumenate_lighting.api.configured_product_builder.';
	var MARKUP_METHOD = 'illumenate_lighting.templates.pages.configure.get_configurator_markup';

	var PRODUCT_TYPES = [
		{ value: 'Linear Fixture', label: __('Linear Fixture') },
		{ value: 'LED Tape',       label: __('LED Tape') },
		{ value: 'LED Neon',       label: __('LED Neon') }
	];

	// ──────────────────────────────────────────────────────────────────
	// Public entry points
	// ──────────────────────────────────────────────────────────────────

	IllDesk.addConfiguratorButton = function (frm) {
		if (!canConfigure(frm)) return;
		frm.add_custom_button(__('Configure & Add Fixture'), function () {
			IllDesk.openConfiguratorDialog(frm);
		}, __('Tools'));
	};

	IllDesk.openConfiguratorDialog = function (frm, opts) {
		var ctrl = new DialogController(frm, opts || {});
		ctrl.start();
		return ctrl;
	};

	// ──────────────────────────────────────────────────────────────────
	// Helpers
	// ──────────────────────────────────────────────────────────────────

	function canConfigure(frm) {
		if (!frm || !frm.doc) return false;
		if (frm.doc.docstatus !== 0) return false;
		if (typeof frm.is_new === 'function' && frm.is_new()) return false;
		if (typeof frm.is_read_only === 'function' && frm.is_read_only()) return false;
		return true;
	}

	function selectedItemRowName(frm) {
		var selected = (frm && frm.get_selected) ? frm.get_selected() : null;
		if (!selected || !selected.items || selected.items.length !== 1) return null;
		return selected.items[0];
	}

	function variantOriginFor(frm) {
		return (frm && frm.doctype === 'Sales Order') ? 'Sales Order Tool' : 'Quotation Tool';
	}

	function escapeHtml(value) {
		return $('<div>').text(value == null ? '' : String(value)).html();
	}

	function isFixture(productType) {
		return productType === 'Linear Fixture';
	}

	// ──────────────────────────────────────────────────────────────────
	// Controller
	// ──────────────────────────────────────────────────────────────────

	function DialogController(frm, opts) {
		this.frm = frm;
		this.opts = opts;
		this.dialog = null;
		this.state = 'pickType';
		this.productType = null;
		this.qty = 1;
		this.configurator = null;   // mounted IllConfigurator.* instance
		this.saving = false;
	}

	DialogController.prototype.start = function () {
		var self = this;
		this.dialog = new frappe.ui.Dialog({
			title: __('Configure & Add Product'),
			size: 'extra-large',
			fields: [
				{ fieldtype: 'HTML', fieldname: 'step_indicator' },
				{ fieldtype: 'HTML', fieldname: 'body' }
			],
			primary_action_label: __('Continue'),
			primary_action: function () { self.onPrimary(); }
		});
		this.dialog.onhide = function () { self.teardownConfigurator(); };
		this.dialog.show();
		this.renderPickType();
	};

	DialogController.prototype.body$ = function () {
		return this.dialog.fields_dict.body.$wrapper;
	};

	DialogController.prototype.renderStepIndicator = function () {
		var steps = [
			{ key: 'pickType',  label: __('Type') },
			{ key: 'configure', label: __('Configure') }
		];
		var current = this.state;
		var html = '<div class="ill-desk-stepper d-flex align-items-center mb-2">';
		steps.forEach(function (s, i) {
			var active = (s.key === current);
			var passed = (current === 'configure' && s.key === 'pickType');
			var color = active ? '#0d6efd' : (passed ? '#198754' : '#adb5bd');
			html += '<span class="badge mr-2" style="background:' + color + '; color:white;">'
				+ (i + 1) + '. ' + s.label + '</span>';
			if (i < steps.length - 1) html += '<span style="color:#dee2e6;">›</span><span class="mr-2"></span>';
		});
		html += '</div>';
		this.dialog.fields_dict.step_indicator.$wrapper.html(html);
	};

	DialogController.prototype.onPrimary = function () {
		if (this.state === 'pickType') return this.advanceFromPickType();
		// In the configure step the configurator's own buttons drive the flow.
	};

	// ── Step 1: pick product type ────────────────────────────────────
	DialogController.prototype.renderPickType = function () {
		this.state = 'pickType';
		this.teardownConfigurator();
		this.renderStepIndicator();
		this.dialog.set_primary_action(__('Continue'), this.onPrimary.bind(this));
		this.dialog.get_primary_btn().show();
		this.dialog.set_secondary_action_label(__('Cancel'));
		this.dialog.set_secondary_action(this.dialog.hide.bind(this.dialog));

		var self = this;
		var $body = this.body$();
		var html = '<div class="form-group">'
			+ '<label class="control-label">' + __('Product Type') + ' <span class="text-danger">*</span></label>'
			+ '<div class="ill-desk-type-pills">';
		PRODUCT_TYPES.forEach(function (pt) {
			var active = (self.productType === pt.value) ? 'active btn-primary' : 'btn-default';
			html += '<button type="button" class="btn mr-2 mb-2 ill-desk-type-pill ' + active
				+ '" data-value="' + escapeHtml(pt.value) + '">' + escapeHtml(pt.label) + '</button>';
		});
		html += '</div></div>'
			+ '<div class="form-group mt-3" style="max-width:200px;">'
			+   '<label class="control-label">' + __('Quantity') + '</label>'
			+   '<input type="number" class="form-control ill-desk-qty" min="1" step="1" value="' + (this.qty || 1) + '">'
			+ '</div>';

		$body.html(html);
		$body.find('.ill-desk-type-pill').on('click', function () {
			$body.find('.ill-desk-type-pill').removeClass('active btn-primary').addClass('btn-default');
			$(this).removeClass('btn-default').addClass('active btn-primary');
			self.productType = $(this).data('value');
		});
		$body.find('.ill-desk-qty').on('input', function () {
			self.qty = parseInt($(this).val(), 10) || 1;
		});
	};

	DialogController.prototype.advanceFromPickType = function () {
		if (!this.productType) {
			frappe.msgprint({ title: __('Select a product type'), indicator: 'orange',
				message: __('Please choose a product type to configure.') });
			return;
		}
		this.renderConfigure();
	};

	// ── Step 2: embedded configurator ────────────────────────────────
	DialogController.prototype.renderConfigure = function () {
		var self = this;
		this.state = 'configure';
		this.renderStepIndicator();

		// The configurator carries its own action buttons; replace the dialog's
		// primary with a "Back" affordance so users can change product type.
		this.dialog.get_primary_btn().hide();
		this.dialog.set_secondary_action_label(__('Back'));
		this.dialog.set_secondary_action(function () { self.renderPickType(); });

		var $body = this.body$();
		$body.html('<div class="text-center text-muted py-4">'
			+ '<i class="fa fa-spinner fa-spin fa-2x mb-2"></i>'
			+ '<p>' + __('Loading configurator…') + '</p></div>');

		frappe.call({
			method: MARKUP_METHOD,
			args: { product_category: this.productType },
			callback: function (r) {
				if (self.state !== 'configure') return; // user navigated away
				var markup = r && r.message;
				if (!markup) {
					$body.html('<div class="alert alert-danger">'
						+ __('Could not load the configurator markup.') + '</div>');
					return;
				}
				self.mountConfigurator(markup);
			},
			error: function () {
				$body.html('<div class="alert alert-danger">'
					+ __('Could not load the configurator markup.') + '</div>');
			}
		});
	};

	DialogController.prototype.mountConfigurator = function (markup) {
		var fixture = isFixture(this.productType);
		var scopeClass = fixture ? 'ill-configurator-fixture' : 'ill-configurator-tape-neon';
		var self = this;

		var $host = $('<div></div>')
			.addClass('ill-configurator ill-desk-configurator ' + scopeClass)
			.html(markup);
		this.body$().html('').append($host);

		var context = {
			product_category: this.productType,
			is_neon: this.productType === 'LED Neon',
			schedule_name: '',
			project_name: '',
			line_idx: null,
			product_slug: '',
			can_save: true,
			show_pricing: true,
			saveHandler: function (payload) { self.onConfiguratorSave(payload); }
		};

		try {
			if (fixture) {
				this.configurator = new root.IllConfigurator.Fixture($host[0], context);
			} else {
				this.configurator = new root.IllConfigurator.TapeNeon($host[0], context);
			}
			this.configurator.init();
		} catch (e) {
			console.error('[illumenate_lighting] Failed to mount configurator', e);
			this.body$().html('<div class="alert alert-danger">'
				+ __('Failed to initialize the configurator.') + '</div>');
		}
	};

	DialogController.prototype.teardownConfigurator = function () {
		if (this.configurator && typeof this.configurator.destroy === 'function') {
			try { this.configurator.destroy(); } catch (e) { /* noop */ }
		}
		this.configurator = null;
	};

	// ── Save (driven by the configurator's Add/Save button) ──────────
	DialogController.prototype.onConfiguratorSave = function (payload) {
		var self = this;
		if (this.saving) return;
		payload = payload || {};

		var productType = payload.product_type || this.productType;
		var selections = payload.selections || {};
		var args = {
			parent_doctype: this.frm.doctype,
			parent_name: this.frm.doc.name,
			product_type: productType,
			selections_json: JSON.stringify(selections),
			row_name: selectedItemRowName(this.frm),
			qty: this.qty,
			variant_origin: variantOriginFor(this.frm)
		};

		if (isFixture(productType)) {
			args.product_slug = payload.product_slug || '';
		} else {
			if (payload.segments) {
				args.segments_json = JSON.stringify(payload.segments);
			}
			if (payload.tape_neon_template) {
				args.tape_neon_template = payload.tape_neon_template;
			}
		}

		this.saving = true;
		frappe.call({
			method: CONFIG_API + 'save_and_apply_from_portal',
			args: args,
			freeze: true,
			freeze_message: __('Saving & applying…'),
			callback: function (r) {
				self.saving = false;
				var msg = (r && r.message) || {};
				if (!msg.success) {
					frappe.msgprint({ title: __('Save failed'), indicator: 'red',
						message: (msg.error || __('Configured product save failed.')) });
					return;
				}
				frappe.show_alert({
					message: __('Saved & applied: {0}', [msg.item_code]),
					indicator: 'green'
				});
				self.dialog.hide();
				self.frm.reload_doc();
			},
			error: function () {
				self.saving = false;
			}
		});
	};

}(window));
