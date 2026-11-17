// Desk Configurator Dialog: server-built row values and totals onto the form. Split verbatim from desk_dialog.js (plan 7.5);
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

	DialogController.prototype.applyRowToForm = function (msg) {
		var frm = this.frm;
		var values = msg.row_values || {};
		if (msg.save_receipt && (frm.doc.items || []).some(function (row) { return row.ill_configuration_save_key === msg.save_receipt; })) return;
		var childDoctype = frm.doctype + ' Item';
		var row = null;
		var lineName = msg.schedule_line_name || null;
		var replacedLines = msg.replaced_line_names || [];

		if (this.rowName && locals[childDoctype] && locals[childDoctype][this.rowName]) {
			row = locals[childDoctype][this.rowName];
		} else if (lineName) {
			// A reconfigured schedule line: its first row on this document takes the new build.
			row = (frm.doc.items || []).find(function (r) {
				return r.ill_schedule_line_id === lineName && !r.ill_is_power_supply_line;
			}) || null;
		}
		if (!row) {
			// Reuse the blank default row a new document starts with.
			row = (frm.doc.items || []).find(function (r) { return !r.item_code && !r.ill_configured_product; }) || null;
			if (!row) row = frm.add_child('items', {});
		}
		// The previous build's rows go: every other row of this schedule line, the
		// rows of the supply / accessory lines the rewrite replaced and, for a row
		// on no schedule, the supplies, sheet accessories and kit components built with it.
		var previousOwner = row.ill_configured_product || row.ill_configured_group || null;
		var previousSheet = row.ill_configured_led_sheet || null;
		var previousRequest = row.ill_configurator_request || null;
		var previousType = row.ill_fixture_type;
		// A reopened row moved to another line leaves its old line with no rows; saving drops that line.
		var previousLine = this.rowName ? (row.ill_schedule_line_id || null) : null;
		var reconfiguring = !!(this.rowName || (lineName && row.ill_schedule_line_id === lineName));
		msg.reconfigured = reconfiguring;
		var stale = (frm.doc.items || []).filter(function (r) {
			if (r === row) return false;
			if (lineName && r.ill_schedule_line_id === lineName) return true;
			if (previousLine && r.ill_schedule_line_id === previousLine) return true;
			if (r.ill_schedule_line_id && replacedLines.indexOf(r.ill_schedule_line_id) >= 0) return true;
			if (!reconfiguring || r.ill_fixture_type !== previousType) return false;
			if (r.ill_is_power_supply_line) return !!previousOwner && r.ill_power_supply_for === previousOwner;
			if (r.ill_schedule_line_id || row.ill_schedule_line_id) return false;
			return (!!previousSheet && r.ill_configured_led_sheet === previousSheet)
				|| (!!previousRequest && r.ill_configurator_request === previousRequest);
		});
		if (stale.length) {
			frm.doc.items = frm.doc.items.filter(function (r) { return stale.indexOf(r) < 0; });
			stale.forEach(function (r) { frappe.model.clear_doc(r.doctype, r.name); });
			frm.doc.items.forEach(function (r, i) { r.idx = i + 1; });
		}
		// A reused row may have held another family: clear the build links the new values leave out.
		BUILD_FIELDS.forEach(function (k) { if (!(k in values) && row[k] != null) row[k] = null; });
		Object.keys(values).forEach(function (k) { row[k] = values[k]; });
		row.__unsaved = 1;

		// Included power supplies (and legacy LED Sheet jumpers / leaders) ride
		// along as their own rows, directly under the configured row.
		var added = (msg.accessory_rows || []).map(function (acc) {
			var accRow = frm.add_child('items', {});
			Object.keys(acc).forEach(function (k) { accRow[k] = acc[k]; });
			accRow.__unsaved = 1;
			return accRow;
		});
		if (added.length) {
			var ordered = frm.doc.items.filter(function (r) { return added.indexOf(r) < 0; });
			ordered.splice.apply(ordered, [ordered.indexOf(row) + 1, 0].concat(added));
			ordered.forEach(function (r, i) { r.idx = i + 1; });
			frm.doc.items = ordered;
		}

		if (msg.header_values && msg.header_values.ill_fixture_schedule
			&& !frm.doc.ill_fixture_schedule && frm.fields_dict.ill_fixture_schedule) {
			frm.set_value('ill_fixture_schedule', msg.header_values.ill_fixture_schedule);
			this.linkedToForm = true;
		}

		frm.refresh_field('items');
		if (frm.cscript && typeof frm.cscript.calculate_taxes_and_totals === 'function') {
			try { frm.cscript.calculate_taxes_and_totals(); } catch (e) { /* totals refresh on save */ }
		}
		frm.dirty();
		this.addedCount += 1 + ((msg.accessory_rows || []).length);
		this.rowName = null;

		var accNote = (msg.accessory_rows || []).length
			? ' ' + __('+ {0} accessory row(s)', [(msg.accessory_rows || []).length])
			: '';
		frappe.show_alert({
			message: (msg.schedule
				? __('Added {0} · {1} (saved to schedule {2})', [escapeHtml(msg.fixture_type), escapeHtml(msg.item_code), escapeHtml(msg.schedule)])
				: __('Added {0} · {1}', [escapeHtml(msg.fixture_type), escapeHtml(msg.item_code)])) + accNote,
			indicator: 'green'
		}, 6);
	};

}(window));
