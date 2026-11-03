// Desk Configurator Dialog: save call and the done step. Split verbatim from desk_dialog.js (plan 7.5);
// loads after desk/dialog/state.js, which defines the controller and its shared helpers.
(function (root) {
	'use strict';

	var IllDesk = root.IllDesk;
	var D = IllDesk._dialog;
	var DESK_API = D.DESK_API;
	var MARKUP_METHOD = D.MARKUP_METHOD;
	var BUTTON_LABEL = D.BUTTON_LABEL;
	var RECONFIGURE_LABEL = D.RECONFIGURE_LABEL;
	var INTERNAL_ROLES = D.INTERNAL_ROLES;
	var PRODUCT_TYPES = D.PRODUCT_TYPES;
	var CATALOG_CLASSES = D.CATALOG_CLASSES;
	var CATALOG_SCOPES = D.CATALOG_SCOPES;
	var BUILD_FIELDS = D.BUILD_FIELDS;
	var STEPS = D.STEPS;
	var isInternalUser = D.isInternalUser;
	var canConfigure = D.canConfigure;
	var customerOf = D.customerOf;
	var variantOriginFor = D.variantOriginFor;
	var escapeHtml = D.escapeHtml;
	var isFixture = D.isFixture;
	var isSheet = D.isSheet;
	var isCatalog = D.isCatalog;
	var productTypeOf = D.productTypeOf;
	var productTypeLabel = D.productTypeLabel;
	var pickHeader = D.pickHeader;
	var usedFixtureTypes = D.usedFixtureTypes;
	var usedSectionLabels = D.usedSectionLabels;
	var isConfiguredRow = D.isConfiguredRow;
	var configuredRowFor = D.configuredRowFor;
	var errorText = D.errorText;
	var makeControl = D.makeControl;
	var statusBadge = D.statusBadge;
	var DialogController = D.DialogController;

	// ── Save (driven by the configurator's Add/Save button) ──────────
	DialogController.prototype.onConfiguratorSave = function (payload) {
		var self = this;
		if (this.saving) return;
		payload = payload || {};

		var productType = payload.product_type || this.productType;
		var isNew = typeof this.frm.is_new === 'function' && this.frm.is_new();
		var args = {
			parent_doctype: this.frm.doctype,
			parent_name: isNew ? null : this.frm.doc.name,
			product_type: productType,
			selections_json: JSON.stringify(payload.selections || {}),
			header_json: JSON.stringify(pickHeader(this.frm.doc)),
			qty: this.qty,
			fixture_type: this.fixtureType,
			location: this.location || null,
			notes: this.notes || null,
			schedule: this.schedule || null,
			line_idx: this.lineIdx != null ? this.lineIdx : null,
			line_key: ((this.pickerData || {}).lines || []).find(function (row) { return row.idx === self.lineIdx; })?.line_key || null,
			expected_modified: (this.pickerData || {}).modified || null,
			variant_origin: variantOriginFor(this.frm)
		};
		if (isCatalog(productType)) {
			if (payload.template) args.template = payload.template;
			if (payload.product_slug) args.product_slug = payload.product_slug;
		} else if (isFixture(productType)) {
			args.product_slug = payload.product_slug || '';
		} else if (isSheet(productType)) {
			// selections_json already carries template / spec / options / coverage.
		} else {
			if (payload.segments) {
				args.segments_json = typeof payload.segments === 'string' ? payload.segments : JSON.stringify(payload.segments);
			}
			if (payload.tape_neon_template) args.tape_neon_template = payload.tape_neon_template;
		}

		var signature = JSON.stringify(args);
		if (!this.saveAttempt || this.saveAttempt.signature !== signature) this.saveAttempt = {signature: signature, key: root.crypto.randomUUID()};
		args.idempotency_key = this.saveAttempt.key;
		this.saving = true;
		this.toggleConfiguratorButtons(true);
		frappe.call({
			method: DESK_API + 'build_configured_line',
			args: args,
			freeze: true,
			freeze_message: __('Saving configuration…'),
			callback: function (r) {
				self.saving = false;
				var msg = (r && r.message) || {};
				if (!msg.success) {
					self.toggleConfiguratorButtons(false);
					var detail = errorText(msg) || __('Configured product save failed.');
					if (msg.schedule_not_editable) {
						detail += '<br>' + __('Go back and create a new schedule version.');
					}
					frappe.msgprint({ title: __('Save failed'), indicator: 'red', message: detail });
					return;
				}
				self.applyRowToForm(msg);
				self.renderDone(msg);
			},
			error: function () {
				self.saving = false;
				self.toggleConfiguratorButtons(false);
			}
		});
	};

	// ── Done / Add another ───────────────────────────────────────────
	DialogController.prototype.renderDone = function (msg) {
		var self = this;
		this.teardownConfigurator();
		this.dialog.get_primary_btn().hide();
		this.dialog.set_secondary_action_label(__('Done'));
		this.dialog.set_secondary_action(function () { self.dialog.hide(); });

		var html = '<div class="ill-desk-done text-center py-4">'
			+ '<div class="ill-desk-done-icon text-success"><i class="fa fa-check-circle fa-3x"></i></div>'
			+ '<h5 class="mt-3">' + (msg.reconfigured
				? __('Updated {0} · {1}', [escapeHtml(msg.fixture_type), escapeHtml(msg.item_code)])
				: __('Added {0} · {1}', [escapeHtml(msg.fixture_type), escapeHtml(msg.item_code)])) + '</h5>'
			+ (msg.schedule
				? '<p class="text-muted mb-1">' + __('Schedule line saved to {0}.', ['<strong>' + escapeHtml(this.scheduleName || msg.schedule) + '</strong>']) + '</p>'
				: '<p class="text-warning mb-1">' + __('Not linked to a fixture schedule.') + '</p>')
			+ '<p class="text-muted small">' + __('The row is on the {0}; save the document to keep it.', [__(this.frm.doctype)]) + '</p>'
			+ '</div>';
		this.body$().html(html);

		var footer = '<div class="ill-desk-footer">'
			+ '<button type="button" class="btn btn-primary ill-desk-add-another">'
			+ '<i class="fa fa-plus"></i> ' + __('Add another') + '</button>'
			+ '<button type="button" class="btn btn-default ml-2 ill-desk-done-btn">' + __('Done') + '</button>'
			+ '</div>';
		this.footer$().html(footer);
		this.footer$().find('.ill-desk-add-another').on('click', function () {
			self.fixtureType = msg.next_fixture_type || '';
			self.lineIdx = null;
			self.initialRequest = null;
			self.editingRow = null;
			self.notes = '';
			self.renderLineStep();
		});
		this.footer$().find('.ill-desk-done-btn').on('click', function () { self.dialog.hide(); });
	};

}(window));
