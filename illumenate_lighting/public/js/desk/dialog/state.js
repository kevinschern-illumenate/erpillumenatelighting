/**
 * Desk Configurator Dialog — "Configure & Add Fixture" for Quotation / Sales Order.
 *
 * Mounts the SAME scoped portal configurator classes (IllConfigurator.Fixture /
 * TapeNeon / LedSheet / Kit / Driver / DriverController) inside a Frappe modal and wires them to a project +
 * fixture-schedule so a line configured here shows up in the customer portal
 * without double entry.
 *
 * Flow:
 *   1. project   → pick / create ilL-Project + ilL-Project-Fixture-Schedule
 *                  (locked to frm.doc.ill_fixture_schedule when already set)
 *   2. line      → product type, existing pending line or new, Fixture Type,
 *                  Section / Room, qty, notes
 *   3. configure → embedded scoped configurator; its own Add/Save button calls
 *                  context.saveHandler → desk_configurator.build_configured_line
 *   4. done      → row inserted client-side (works on unsaved docs), header link
 *                  set; "Add another" loops back to step 2.
 *
 * Server builds (configured record, Item, BOM, Item Price, schedule line);
 * client inserts the row. The parent document is never auto-saved.
 *
 * "Reconfigure Row" on the Items grid reopens a configured row (opts.rowName):
 * its rows, and the rows of its schedule line's supplies / accessories, are
 * replaced in place so the document keeps matching the schedule.
 *
 * Public API (consumed by the quote_order_configurator.js shim):
 *   IllDesk.addConfiguratorButton(frm)
 *   IllDesk.openConfiguratorDialog(frm, opts)
 *   IllDesk.reconfigureSelectedRow(frm)
 *
 * Files (plan 7.5): dialog/state.js (constants, entry points, helpers, controller),
 * dialog/family_steps.js (steps 1-3), dialog/pricing.js (server row values onto the form)
 * and dialog/save.js (save call and the done step). Load them in that order.
 */
(function (root) {
	'use strict';

	var IllDesk = root.IllDesk = root.IllDesk || {};
	var DESK_API = 'illumenate_lighting.illumenate_lighting.api.desk_configurator.';
	var MARKUP_METHOD = 'illumenate_lighting.templates.pages.configure.get_configurator_markup';
	var BUTTON_LABEL = __('Configure & Add Fixture');
	var RECONFIGURE_LABEL = __('Reconfigure Row');
	var INTERNAL_ROLES = ['System Manager', 'Administrator', 'ilL Sales Review', 'ilL Order Approver'];

	var PRODUCT_TYPES = [
		{ value: 'Linear Fixture', label: __('Linear Fixture') },
		{ value: 'LED Tape',       label: __('LED Tape') },
		{ value: 'COB Tape',       label: __('COB Tape') },
		{ value: 'LED Neon',       label: __('LED Neon') },
		{ value: 'LED Sheet',      label: __('LED Sheet') },
		{ value: 'Extrusion Kit',  label: __('Extrusion Kit') },
		{ value: 'Driver',         label: __('Power Supply') },
		{ value: 'Controller',     label: __('Controller') }
	];

	// Catalog families: the choice resolves to existing Items (no build).
	var CATALOG_CLASSES = { 'Extrusion Kit': 'Kit', 'Driver': 'Driver', 'Controller': 'DriverController' };
	var CATALOG_SCOPES = { 'Extrusion Kit': 'ill-configurator-kit', 'Driver': 'ill-configurator-driver', 'Controller': 'ill-configurator-controller' };

	// Row fields written from a build (quote_order_configurator._apply_artifact_to_row).
	var BUILD_FIELDS = ['ill_product_type', 'ill_configured_group', 'ill_configured_fixture', 'ill_configured_tape_neon',
		'ill_configured_led_sheet', 'ill_configured_product_doctype', 'ill_configured_product', 'ill_configured_item',
		'ill_bom', 'ill_template_code', 'ill_requested_length_mm', 'ill_mfg_length_mm', 'ill_runs_count',
		'ill_total_watts', 'ill_finish', 'ill_lens', 'ill_engine_version', 'ill_is_power_supply_line',
		'ill_power_supply_for', 'ill_parent_configured_fixture', 'bom_no'];

	var STEPS = [
		{ key: 'project',   label: __('Project & Schedule') },
		{ key: 'line',      label: __('Line Details') },
		{ key: 'configure', label: __('Configure') }
	];

	// ──────────────────────────────────────────────────────────────────
	// Public entry points
	// ──────────────────────────────────────────────────────────────────

	IllDesk.addConfiguratorButton = function (frm) {
		var grid = frm && frm.fields_dict && frm.fields_dict.items && frm.fields_dict.items.grid;
		if (!canConfigure(frm)) {
			// Grid buttons survive form refreshes, so hide ours once the doc is no longer editable.
			[BUTTON_LABEL, RECONFIGURE_LABEL].forEach(function (label) {
				if (grid && grid.custom_buttons && grid.custom_buttons[label]) {
					grid.custom_buttons[label].addClass('hidden');
				}
			});
			return;
		}

		// Standalone toolbar action (not buried under Tools).
		var $btn = frm.add_custom_button(BUTTON_LABEL, function () {
			IllDesk.openConfiguratorDialog(frm);
		});
		if ($btn && $btn.addClass) $btn.addClass('btn-primary');

		// Items grid: sits next to "Add Row", where users build lines.
		// frappe's Grid.add_custom_button is idempotent per label (re-shows a hidden one).
		if (grid && typeof grid.add_custom_button === 'function') {
			grid.add_custom_button(BUTTON_LABEL, function () {
				IllDesk.openConfiguratorDialog(frm);
			});
			grid.add_custom_button(RECONFIGURE_LABEL, function () {
				IllDesk.reconfigureSelectedRow(frm);
			});
		}
	};

	// Reopens the ticked configured row with its saved selections. A ticked
	// power-supply or accessory row opens the configured row it belongs to.
	IllDesk.reconfigureSelectedRow = function (frm) {
		var grid = frm && frm.fields_dict && frm.fields_dict.items && frm.fields_dict.items.grid;
		var selected = (grid && typeof grid.get_selected_children === 'function') ? grid.get_selected_children() : [];
		if (selected.length !== 1) {
			frappe.msgprint({ title: __('Select one row'), indicator: 'orange',
				message: __('Tick the checkbox of one configured row in Items, then click {0}.', [RECONFIGURE_LABEL]) });
			return null;
		}
		var row = configuredRowFor(frm, selected[0]);
		if (!row) {
			frappe.msgprint({ title: __('Not a configured row'), indicator: 'orange',
				message: __('Row {0} was not added with {1}, so there is no configuration to reopen. Edit it in the grid instead.',
					[selected[0].idx, BUTTON_LABEL]) });
			return null;
		}
		return IllDesk.openConfiguratorDialog(frm, { rowName: row.name });
	};

	IllDesk.openConfiguratorDialog = function (frm, opts) {
		if (!frm || !frm.doc) return null;
		if (!isInternalUser()) {
			frappe.msgprint({ title: __('Not available'), indicator: 'orange',
				message: __('The desk configurator is available to internal users only.') });
			return null;
		}
		if (!customerOf(frm)) {
			frappe.msgprint({ title: __('Customer required'), indicator: 'orange',
				message: __('Set the Customer on this {0} first, then configure fixtures.', [__(frm.doctype)]) });
			var custField = frm.doctype === 'Quotation' ? 'party_name' : 'customer';
			if (frm.fields_dict[custField] && frm.fields_dict[custField].$input) {
				frm.fields_dict[custField].$input.focus();
			}
			return null;
		}
		var ctrl = new DialogController(frm, opts || {});
		ctrl.start();
		return ctrl;
	};

	// ──────────────────────────────────────────────────────────────────
	// Helpers
	// ──────────────────────────────────────────────────────────────────

	function isInternalUser() {
		if (frappe.session && frappe.session.user === 'Administrator') return true;
		if (!frappe.user || typeof frappe.user.has_role !== 'function') return false;
		return INTERNAL_ROLES.some(function (r) { return frappe.user.has_role(r); });
	}

	function canConfigure(frm) {
		if (!frm || !frm.doc) return false;
		if (frm.doc.docstatus !== 0) return false;
		if (typeof frm.is_read_only === 'function' && frm.is_read_only()) return false;
		return isInternalUser();
	}

	function customerOf(frm) {
		var doc = frm.doc || {};
		if (doc.customer) return doc.customer;
		if (frm.doctype === 'Quotation' && doc.quotation_to === 'Customer') return doc.party_name || null;
		return null;
	}

	function variantOriginFor(frm) {
		return (frm && frm.doctype === 'Sales Order') ? 'Sales Order Tool' : 'Quotation Tool';
	}

	function escapeHtml(value) {
		return frappe.utils.escape_html(value == null ? '' : String(value));
	}

	function isFixture(productType) {
		return productType === 'Linear Fixture';
	}

	function isSheet(productType) {
		return productType === 'LED Sheet';
	}

	function isCatalog(productType) {
		return Object.prototype.hasOwnProperty.call(CATALOG_CLASSES, productType);
	}

	// A dialog product type for a row: catalog rows (kit, supply, controller)
	// carry no ill_product_type, so their saved request names the family.
	function productTypeOf(productType, request) {
		var known = function (value) { return PRODUCT_TYPES.some(function (pt) { return pt.value === value; }); };
		if (known(productType)) return productType;
		var family = request && (request.family || ((request.selections || {}).group_request || {}).family);
		return known(family) ? family : (productType || null);
	}

	function productTypeLabel(productType) {
		var match = PRODUCT_TYPES.find(function (pt) { return pt.value === productType; });
		return match ? match.label : productType;
	}

	function pickHeader(doc) {
		var keys = ['customer', 'party_name', 'quotation_to', 'company', 'currency',
			'price_list_currency', 'selling_price_list', 'conversion_rate',
			'plc_conversion_rate', 'transaction_date', 'delivery_date',
			'customer_group', 'territory', 'ignore_pricing_rule'];
		var out = {};
		keys.forEach(function (k) {
			if (doc[k] !== undefined && doc[k] !== null && doc[k] !== '') out[k] = doc[k];
		});
		return out;
	}

	function usedFixtureTypes(frm, exceptLine) {
		return (frm.doc.items || []).filter(function (r) { return !exceptLine || r.ill_schedule_line_id !== exceptLine; })
			.map(function (r) { return r.ill_fixture_type; }).filter(Boolean);
	}

	function usedSectionLabels(frm) {
		var seen = {};
		return (frm.doc.items || []).map(function (r) { return r.ill_section_label; })
			.filter(function (v) { if (!v || seen[v]) return false; seen[v] = true; return true; });
	}

	function isConfiguredRow(row) {
		return !!(row && !row.ill_is_power_supply_line && (row.ill_configurator_request
			|| row.ill_configured_group || row.ill_configured_fixture || row.ill_configured_tape_neon || row.ill_configured_led_sheet));
	}

	// The configured row a ticked row belongs to: itself, or the row whose build
	// its power supply / LED Sheet accessory was added for (same Fixture Type).
	function configuredRowFor(frm, row) {
		if (!row) return null;
		var rows = frm.doc.items || [];
		var sameType = function (r) { return r.ill_fixture_type === row.ill_fixture_type; };
		if (row.ill_is_power_supply_line) {
			var owner = row.ill_power_supply_for;
			return owner ? rows.find(function (r) {
				return isConfiguredRow(r) && sameType(r)
					&& (r.ill_configured_product === owner || r.ill_configured_group === owner || r.ill_configured_led_sheet === owner);
			}) || null : null;
		}
		if (row.ill_configurator_request) return row;
		if (row.ill_configured_led_sheet) {
			// Jumper / leader rows share the sheet link; the panel row comes first.
			var sheetRows = rows.filter(function (r) { return r.ill_configured_led_sheet === row.ill_configured_led_sheet && sameType(r); });
			return sheetRows.find(function (r) { return r.ill_configurator_request; }) || sheetRows[0] || row;
		}
		return isConfiguredRow(row) ? row : null;
	}

	function errorText(msg) {
		if (!msg) return null;
		if (msg.error) return escapeHtml(msg.error);
		if (msg.messages && msg.messages.length) {
			return msg.messages.map(function (m) {
				return escapeHtml((m && (m.text || m.message)) || String(m));
			}).join('<br>');
		}
		return null;
	}

	function makeControl(df, $parent) {
		var control = frappe.ui.form.make_control({ df: df, parent: $parent, render_input: true });
		control.refresh();
		return control;
	}

	function statusBadge(status, isLocked) {
		var color = 'gray';
		if (isLocked) color = 'red';
		else if (status === 'DRAFT') color = 'blue';
		else if (status === 'READY') color = 'green';
		else if (status === 'QUOTED') color = 'orange';
		var text = isLocked ? __('LOCKED') : (status || '');
		return '<span class="indicator-pill ' + color + ' ill-desk-status">' + escapeHtml(text) + '</span>';
	}

	// ──────────────────────────────────────────────────────────────────
	// Controller
	// ──────────────────────────────────────────────────────────────────

	function DialogController(frm, opts) {
		this.frm = frm;
		this.opts = opts;
		this.dialog = null;
		this.state = 'project';
		this.configurator = null;
		this.controls = {};
		this.context = null;
		this.saving = false;
		this.busy = false;

		// Session state (kept for the whole dialog, across "Add another").
		this.customer = customerOf(frm);
		this.project = null;
		this.projectName = null;
		this.schedule = frm.doc.ill_fixture_schedule || null;
		this.scheduleName = null;
		this.scheduleStatus = null;
		this.scheduleLocked = false;
		this.skipSchedule = false;
		this.linkedToForm = !!frm.doc.ill_fixture_schedule;
		this.pickerData = null;
		this.productType = opts.productType || null;
		this.lineIdx = null;
		this.fixtureType = null;
		this.location = null;
		this.qty = 1;
		this.notes = '';
		this.rowName = opts.rowName || null;
		this.editingRow = this.rowName && (frm.doc.items || []).find(function (row) { return row.name === opts.rowName; });
		if (this.editingRow) {
			var row = this.editingRow;
			this.productType = row.ill_product_type || this.productType;
			this.fixtureType = row.ill_fixture_type; this.location = row.ill_section_label;
			this.qty = row.qty; this.notes = row.additional_notes || '';
			this.scheduleLineName = row.ill_schedule_line_id;
			try { this.initialRequest = row.ill_configurator_request ? JSON.parse(row.ill_configurator_request) : null; } catch (_) { this.initialRequest = null; }
			this.productType = productTypeOf(this.productType, this.initialRequest);
		}
		this.addedCount = 0;
	}

	DialogController.prototype.start = function () {
		var self = this;
		this.dialog = new frappe.ui.Dialog({
			title: BUTTON_LABEL,
			size: 'extra-large',
			fields: [
				{ fieldtype: 'HTML', fieldname: 'step_indicator' },
				{ fieldtype: 'HTML', fieldname: 'body' },
				{ fieldtype: 'HTML', fieldname: 'footer' }
			],
			primary_action_label: __('Continue'),
			primary_action: function () { self.onPrimary(); }
		});
		this.dialog.$wrapper.addClass('ill-desk-configurator-dialog');
		this.dialog.onhide = function () { self.onHide(); };
		this.dialog.show();
		if (this.editingRow && !this.initialRequest && !this.frm.is_new()) {
			this.call('reopen_row', {parent_doctype: this.frm.doctype, parent_name: this.frm.doc.name, row_name: this.rowName}).then(function (result) {
				if (self.closed) return;
				self.initialRequest = result.request;
				self.productType = productTypeOf(self.productType, self.initialRequest);
				self.renderProjectStep();
			}).catch(function () { self.body$().html('<div role="alert">' + __('This configuration could not be reopened. Close the dialog and review the document.') + '</div>'); });
		} else this.renderProjectStep();
	};

	DialogController.prototype.body$ = function () { return this.dialog.fields_dict.body.$wrapper; };
	DialogController.prototype.footer$ = function () { return this.dialog.fields_dict.footer.$wrapper; };

	DialogController.prototype.onHide = function () {
		this.closed = true;
		this.teardownConfigurator();
		if (this.addedCount && typeof this.frm.is_dirty === 'function' && this.frm.is_dirty()) {
			frappe.show_alert({
				message: __('Remember to save the {0} to keep the {1} configured line(s).',
					[__(this.frm.doctype), this.addedCount]),
				indicator: 'orange'
			}, 8);
		}
	};

	DialogController.prototype.setBusy = function (busy) {
		this.busy = !!busy;
		var $btn = this.dialog.get_primary_btn();
		if ($btn) $btn.prop('disabled', this.busy);
	};

	DialogController.prototype.renderStepIndicator = function () {
		var current = STEPS.map(function (s) { return s.key; }).indexOf(this.state);
		var html = '<div class="ill-desk-stepper">';
		STEPS.forEach(function (s, i) {
			var cls = i === current ? 'active' : (i < current ? 'done' : '');
			html += '<span class="ill-desk-step ' + cls + '"><span class="ill-desk-step-num">' + (i + 1)
				+ '</span>' + escapeHtml(s.label) + '</span>';
			if (i < STEPS.length - 1) html += '<span class="ill-desk-step-sep">›</span>';
		});
		html += '</div>';
		this.dialog.fields_dict.step_indicator.$wrapper.html(html);
	};

	DialogController.prototype.onPrimary = function () {
		if (this.busy) return;
		if (this.state === 'project') return this.advanceFromProject();
		if (this.state === 'line') return this.advanceFromLine();
	};

	DialogController.prototype.call = function (method, args, opts) {
		var self = this;
		opts = opts || {};
		return new Promise(function (resolve, reject) {
			frappe.call({
				method: DESK_API + method,
				args: args,
				freeze: !!opts.freeze,
				freeze_message: opts.freeze_message,
				callback: function (r) { resolve((r && r.message) || {}); },
				error: function (e) { self.setBusy(false); reject(e); }
			});
		});
	};

	// Shared with the other dialog files (plan 7.5 extraction); not a public API.
	IllDesk._dialog = {
		DESK_API: DESK_API,
		MARKUP_METHOD: MARKUP_METHOD,
		BUTTON_LABEL: BUTTON_LABEL,
		RECONFIGURE_LABEL: RECONFIGURE_LABEL,
		INTERNAL_ROLES: INTERNAL_ROLES,
		PRODUCT_TYPES: PRODUCT_TYPES,
		CATALOG_CLASSES: CATALOG_CLASSES,
		CATALOG_SCOPES: CATALOG_SCOPES,
		BUILD_FIELDS: BUILD_FIELDS,
		STEPS: STEPS,
		isInternalUser: isInternalUser,
		canConfigure: canConfigure,
		customerOf: customerOf,
		variantOriginFor: variantOriginFor,
		escapeHtml: escapeHtml,
		isFixture: isFixture,
		isSheet: isSheet,
		isCatalog: isCatalog,
		productTypeOf: productTypeOf,
		productTypeLabel: productTypeLabel,
		pickHeader: pickHeader,
		usedFixtureTypes: usedFixtureTypes,
		usedSectionLabels: usedSectionLabels,
		isConfiguredRow: isConfiguredRow,
		configuredRowFor: configuredRowFor,
		errorText: errorText,
		makeControl: makeControl,
		statusBadge: statusBadge,
		DialogController: DialogController
	};
}(window));
