/**
 * Desk Configurator Dialog — "Configure & Add Fixture" for Quotation / Sales Order.
 *
 * Mounts the SAME scoped portal configurator classes (IllConfigurator.Fixture /
 * IllConfigurator.TapeNeon) inside a Frappe modal and wires them to a project +
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
 * Public API (consumed by the quote_order_configurator.js shim):
 *   IllDesk.addConfiguratorButton(frm)
 *   IllDesk.openConfiguratorDialog(frm, opts)
 */
(function (root) {
	'use strict';

	var IllDesk = root.IllDesk = root.IllDesk || {};
	var DESK_API = 'illumenate_lighting.illumenate_lighting.api.desk_configurator.';
	var MARKUP_METHOD = 'illumenate_lighting.templates.pages.configure.get_configurator_markup';
	var BUTTON_LABEL = __('Configure & Add Fixture');
	var INTERNAL_ROLES = ['System Manager', 'Administrator'];

	var PRODUCT_TYPES = [
		{ value: 'Linear Fixture', label: __('Linear Fixture') },
		{ value: 'LED Tape',       label: __('LED Tape') },
		{ value: 'LED Neon',       label: __('LED Neon') }
	];

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
			if (grid && grid.custom_buttons && grid.custom_buttons[BUTTON_LABEL]) {
				grid.custom_buttons[BUTTON_LABEL].addClass('hidden');
			}
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
		}
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

	function usedFixtureTypes(frm) {
		return (frm.doc.items || []).map(function (r) { return r.ill_fixture_type; }).filter(Boolean);
	}

	function usedSectionLabels(frm) {
		var seen = {};
		return (frm.doc.items || []).map(function (r) { return r.ill_section_label; })
			.filter(function (v) { if (!v || seen[v]) return false; seen[v] = true; return true; });
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
		this.renderProjectStep();
	};

	DialogController.prototype.body$ = function () { return this.dialog.fields_dict.body.$wrapper; };
	DialogController.prototype.footer$ = function () { return this.dialog.fields_dict.footer.$wrapper; };

	DialogController.prototype.onHide = function () {
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

	// ── Step 1: Project & Schedule ───────────────────────────────────
	DialogController.prototype.renderProjectStep = function () {
		var self = this;
		this.state = 'project';
		this.teardownConfigurator();
		this.renderStepIndicator();
		this.footer$().empty();
		this.dialog.set_primary_action(__('Continue'), this.onPrimary.bind(this));
		this.dialog.get_primary_btn().show();
		this.dialog.set_secondary_action_label(__('Cancel'));
		this.dialog.set_secondary_action(function () { self.dialog.hide(); });

		var $body = this.body$();
		$body.html('<div class="text-muted py-3"><i class="fa fa-spinner fa-spin"></i> ' + __('Loading…') + '</div>');

		this.call('get_desk_context', {
			parent_doctype: this.frm.doctype,
			customer: this.customer,
			linked_schedule: this.linkedToForm ? this.frm.doc.ill_fixture_schedule : null
		}).then(function (ctx) {
			if (self.state !== 'project') return;
			if (!ctx.success) {
				$body.html('<div class="alert alert-danger">' + escapeHtml(ctx.error || __('Could not load context.')) + '</div>');
				return;
			}
			self.context = ctx;
			if (ctx.linked_schedule) {
				self.renderLinkedSchedule(ctx.linked_schedule);
			} else {
				self.renderProjectPickers(ctx);
			}
		}).catch(function () {
			$body.html('<div class="alert alert-danger">' + __('Could not load the project context.') + '</div>');
		});
	};

	DialogController.prototype.renderLinkedSchedule = function (linked) {
		this.schedule = linked.name;
		this.scheduleName = linked.schedule_name;
		this.scheduleStatus = linked.status;
		this.scheduleLocked = !!linked.is_locked;
		this.project = linked.ill_project;
		this.projectName = linked.project_name;
		this.skipSchedule = false;

		var html = '<div class="ill-desk-linked card">'
			+ '<div class="card-body">'
			+ '<div class="d-flex align-items-center flex-wrap">'
			+ '<span class="badge badge-info mr-2">' + __('Linked') + '</span>'
			+ '<strong>' + escapeHtml(linked.project_name || linked.ill_project) + '</strong>'
			+ '<span class="mx-2 text-muted">›</span>'
			+ '<span>' + escapeHtml(linked.schedule_name || linked.name) + '</span>'
			+ '<span class="text-muted ml-2 small">(' + escapeHtml(linked.name) + ' · v' + escapeHtml(linked.version || 1) + ')</span>'
			+ '<span class="ml-2">' + statusBadge(linked.status, linked.is_locked) + '</span>'
			+ '</div>'
			+ '<p class="text-muted small mt-2 mb-0">'
			+ __('This {0} is already linked to this fixture schedule. New lines will be written to it; a document can carry only one schedule.', [__(this.frm.doctype)])
			+ '</p>'
			+ '<div class="ill-desk-schedule-status mt-2"></div>'
			+ '</div></div>';
		this.body$().html(html);

		if (!linked.can_write) {
			this.showScheduleProblem(__('You do not have write access to this schedule.'), false);
		} else if (!linked.is_editable) {
			this.showScheduleProblem(linked.not_editable_reason, true);
		}
	};

	DialogController.prototype.showScheduleProblem = function (reason, offerVersion) {
		var self = this;
		var $slot = this.body$().find('.ill-desk-schedule-status');
		var html = '<div class="alert alert-warning mb-0"><div>' + escapeHtml(reason) + '</div>';
		if (offerVersion) {
			html += '<button type="button" class="btn btn-sm btn-default mt-2 ill-desk-new-version">'
				+ __('Create new version') + '</button>';
		}
		html += '</div>';
		$slot.html(html);
		$slot.find('.ill-desk-new-version').on('click', function () { self.createNewVersion(); });
	};

	DialogController.prototype.createNewVersion = function () {
		var self = this;
		if (!this.schedule) return;
		this.setBusy(true);
		this.call('create_schedule_version', { schedule: this.schedule },
			{ freeze: true, freeze_message: __('Creating new schedule version…') })
			.then(function (res) {
				self.setBusy(false);
				if (!res.success) {
					frappe.msgprint({ title: __('Could not create version'), indicator: 'red',
						message: escapeHtml(res.error || '') });
					return;
				}
				var previous = self.schedule;
				self.schedule = res.name;
				self.scheduleName = res.schedule_name;
				self.scheduleStatus = res.status;
				self.scheduleLocked = !!res.is_locked;
				// The document may carry only one schedule: follow the new version.
				if (self.frm.doc.ill_fixture_schedule && self.frm.doc.ill_fixture_schedule !== res.name) {
					self.frm.set_value('ill_fixture_schedule', res.name);
				}
				frappe.show_alert({
					message: res.reused_existing_version
						? __('Continuing on open version {0}', [escapeHtml(res.name)])
						: __('Created schedule version {0} (previous {1} is now locked)', [escapeHtml(res.name), escapeHtml(previous)]),
					indicator: 'green'
				}, 7);
				self.renderLineStep();
			})
			.catch(function () { self.setBusy(false); });
	};

	DialogController.prototype.renderProjectPickers = function (ctx) {
		var self = this;
		var defaultProjectName = this.frm.doc.title || this.frm.doc.customer_name || this.customer || '';

		var html = '<div class="ill-desk-project-step">'
			+ '<p class="text-muted small mb-3">' + __('Customer: {0}', ['<strong>' + escapeHtml(this.customer) + '</strong>']) + '</p>'
			+ '<div class="row ill-desk-pickers">'
			+   '<div class="col-md-6">'
			+     '<div class="ill-desk-ctl" data-ctl="project"></div>'
			+     '<div class="ill-desk-ctl" data-ctl="new_project"></div>'
			+     '<div class="ill-desk-ctl" data-ctl="new_project_name"></div>'
			+   '</div>'
			+   '<div class="col-md-6">'
			+     '<div class="ill-desk-ctl" data-ctl="schedule"></div>'
			+     '<div class="ill-desk-ctl" data-ctl="new_schedule"></div>'
			+     '<div class="ill-desk-ctl" data-ctl="new_schedule_name"></div>'
			+     '<div class="ill-desk-schedule-status mt-1"></div>'
			+   '</div>'
			+ '</div>'
			+ '<hr class="my-2">'
			+ '<div class="ill-desk-ctl" data-ctl="skip_schedule"></div>'
			+ '<div class="ill-desk-skip-warning alert alert-warning small" style="display:none;">'
			+   __('Lines added without a fixture schedule are NOT visible to the customer in the portal and cannot be traced back to a schedule line.')
			+ '</div>'
			+ '</div>';
		var $body = this.body$();
		$body.html(html);

		var slot = function (name) { return $body.find('.ill-desk-ctl[data-ctl="' + name + '"]'); };
		var c = this.controls = {};

		c.project = makeControl({
			fieldtype: 'Link', fieldname: 'project', label: __('Project'), options: 'ilL-Project',
			get_query: function () { return { filters: { customer: self.customer, is_active: 1 } }; },
			onchange: function () {
				var val = c.project.get_value();
				if (val && val !== self.project) {
					self.project = val;
					if (c.schedule && c.schedule.get_value()) c.schedule.set_value('');
					self.schedule = null;
				} else if (!val) {
					self.project = null;
				}
			}
		}, slot('project'));

		c.new_project = makeControl({
			fieldtype: 'Check', fieldname: 'new_project', label: __('Create a new project'),
			onchange: function () {
				var on = !!c.new_project.get_value();
				slot('new_project_name').toggle(on);
				slot('project').toggle(!on);
				if (on) {
					// A new project has no schedules yet: force "new schedule".
					c.new_schedule.set_value(1);
					slot('new_schedule').hide();
					slot('new_schedule_name').show();
					slot('schedule').hide();
				} else {
					slot('new_schedule').show();
				}
			}
		}, slot('new_project'));

		c.new_project_name = makeControl({
			fieldtype: 'Data', fieldname: 'new_project_name', label: __('New project name')
		}, slot('new_project_name'));
		c.new_project_name.set_value(defaultProjectName);
		slot('new_project_name').hide();

		c.schedule = makeControl({
			fieldtype: 'Link', fieldname: 'schedule', label: __('Fixture Schedule'),
			options: 'ilL-Project-Fixture-Schedule',
			get_query: function () {
				var filters = { is_locked: 0 };
				if (self.project) filters.ill_project = self.project;
				else filters.customer = self.customer;
				return { filters: filters };
			},
			onchange: function () {
				var val = c.schedule.get_value();
				self.schedule = val || null;
				$body.find('.ill-desk-schedule-status').empty();
				if (val && !self.project) {
					frappe.db.get_value('ilL-Project-Fixture-Schedule', val, 'ill_project')
						.then(function (r) {
							var d = (r && r.message) || {};
							if (d.ill_project) { self.project = d.ill_project; c.project.set_value(d.ill_project); }
						});
				}
			}
		}, slot('schedule'));

		c.new_schedule = makeControl({
			fieldtype: 'Check', fieldname: 'new_schedule', label: __('Create a new schedule'),
			onchange: function () {
				var on = !!c.new_schedule.get_value();
				slot('new_schedule_name').toggle(on);
				slot('schedule').toggle(!on);
			}
		}, slot('new_schedule'));

		c.new_schedule_name = makeControl({
			fieldtype: 'Data', fieldname: 'new_schedule_name', label: __('New schedule name')
		}, slot('new_schedule_name'));
		c.new_schedule_name.set_value('Main Schedule');
		slot('new_schedule_name').hide();

		c.skip_schedule = makeControl({
			fieldtype: 'Check', fieldname: 'skip_schedule',
			label: __('Skip schedule (add to this document only)'),
			onchange: function () {
				var on = !!c.skip_schedule.get_value();
				self.skipSchedule = on;
				$body.find('.ill-desk-skip-warning').toggle(on);
				$body.find('.ill-desk-pickers').toggleClass('ill-desk-disabled', on);
			}
		}, slot('skip_schedule'));

		// Convenience: a single matching project pre-selects itself.
		if (ctx.projects && ctx.projects.length === 1) {
			c.project.set_value(ctx.projects[0].value);
		}
	};

	DialogController.prototype.advanceFromProject = function () {
		var self = this;
		if (this.linkedToForm) {
			if (!this.context || !this.context.linked_schedule) return;
			var linked = this.context.linked_schedule;
			if (!linked.can_write) {
				frappe.msgprint({ title: __('No access'), indicator: 'red',
					message: __('You do not have write access to schedule {0}.', [escapeHtml(linked.name)]) });
				return;
			}
			if (this.schedule === linked.name && !linked.is_editable) {
				frappe.msgprint({ title: __('Schedule not editable'), indicator: 'orange',
					message: escapeHtml(linked.not_editable_reason || '') + '<br>' + __('Use "Create new version" to continue.') });
				return;
			}
			return this.renderLineStep();
		}

		if (this.skipSchedule) {
			this.schedule = null;
			this.project = null;
			return this.renderLineStep();
		}

		var c = this.controls;
		var args = { customer: this.customer };
		if (c.new_project.get_value()) {
			args.project_name = (c.new_project_name.get_value() || '').trim();
			if (!args.project_name) {
				frappe.msgprint({ title: __('Project name required'), indicator: 'orange',
					message: __('Enter a name for the new project.') });
				return;
			}
		} else {
			args.project = c.project.get_value();
			if (!args.project) {
				frappe.msgprint({ title: __('Project required'), indicator: 'orange',
					message: __('Pick a project, create a new one, or tick "Skip schedule".') });
				return;
			}
		}
		if (c.new_schedule.get_value() || args.project_name) {
			args.schedule_name = (c.new_schedule_name.get_value() || '').trim() || 'Main Schedule';
		} else {
			args.schedule = c.schedule.get_value();
			if (!args.schedule) {
				frappe.msgprint({ title: __('Schedule required'), indicator: 'orange',
					message: __('Pick a fixture schedule or create a new one.') });
				return;
			}
		}

		this.setBusy(true);
		this.call('ensure_project_and_schedule', args, { freeze: true, freeze_message: __('Preparing schedule…') })
			.then(function (res) {
				self.setBusy(false);
				if (!res.success) {
					frappe.msgprint({ title: __('Could not prepare schedule'), indicator: 'red',
						message: escapeHtml(res.error || '') });
					return;
				}
				self.project = res.project;
				self.projectName = res.project_name;
				self.schedule = res.schedule;
				self.scheduleName = res.schedule_name;
				self.scheduleStatus = res.status;
				self.scheduleLocked = !!res.is_locked;
				if (res.created_project || res.created_schedule) {
					frappe.show_alert({
						message: res.created_project
							? __('Created project {0} and schedule {1}', [escapeHtml(res.project_name), escapeHtml(res.schedule_name)])
							: __('Created schedule {0}', [escapeHtml(res.schedule_name)]),
						indicator: 'green'
					});
				}
				if (!res.is_editable) {
					self.showScheduleProblem(res.not_editable_reason, true);
					return;
				}
				self.renderLineStep();
			})
			.catch(function () { self.setBusy(false); });
	};

	// ── Step 2: Line details ─────────────────────────────────────────
	DialogController.prototype.renderLineStep = function () {
		var self = this;
		this.state = 'line';
		this.teardownConfigurator();
		this.renderStepIndicator();
		this.footer$().empty();
		this.dialog.set_primary_action(__('Continue'), this.onPrimary.bind(this));
		this.dialog.get_primary_btn().show();
		this.dialog.set_secondary_action_label(__('Back'));
		this.dialog.set_secondary_action(function () {
			if (self.linkedToForm) { self.dialog.hide(); return; }
			self.renderProjectStep();
		});

		var $body = this.body$();
		$body.html('<div class="text-muted py-3"><i class="fa fa-spinner fa-spin"></i> ' + __('Loading schedule…') + '</div>');

		var used = usedFixtureTypes(this.frm);
		var load = this.schedule
			? this.call('get_schedule_picker_data', { schedule: this.schedule, used_json: JSON.stringify(used) })
			: this.call('get_next_fixture_type', { schedule: null, used_json: JSON.stringify(used) })
				.then(function (next) {
					return { success: true, lines: [], locations: [], next_fixture_type: (typeof next === 'string') ? next : '' };
				});

		load.then(function (data) {
			if (self.state !== 'line') return;
			if (!data.success) {
				$body.html('<div class="alert alert-danger">' + escapeHtml(data.error || __('Could not load the schedule.')) + '</div>');
				return;
			}
			self.pickerData = data;
			if (self.schedule) {
				self.scheduleName = data.schedule_name || self.scheduleName;
				self.projectName = data.project_name || self.projectName;
				self.scheduleStatus = data.status;
				self.scheduleLocked = !!data.is_locked;
				if (!data.is_editable) {
					$body.html('<div class="ill-desk-schedule-status"></div>');
					self.showScheduleProblem(data.not_editable_reason, true);
					self.dialog.get_primary_btn().hide();
					return;
				}
			}
			self.renderLineForm(data);
		}).catch(function () {
			$body.html('<div class="alert alert-danger">' + __('Could not load the schedule.') + '</div>');
		});
	};

	DialogController.prototype.renderLineForm = function (data) {
		var self = this;
		var $body = this.body$();
		var pendingLines = (data.lines || []).filter(function (l) { return l.is_pending; });
		var showLineSelect = !!(this.schedule && pendingLines.length);

		var header = this.schedule
			? '<div class="ill-desk-context small text-muted mb-2">'
				+ '<i class="fa fa-folder-o"></i> ' + escapeHtml(this.projectName || this.project || '')
				+ ' <span class="mx-1">›</span> <i class="fa fa-list"></i> ' + escapeHtml(this.scheduleName || this.schedule)
				+ ' ' + statusBadge(data.status, data.is_locked) + '</div>'
			: '<div class="ill-desk-context small text-warning mb-2"><i class="fa fa-exclamation-triangle"></i> '
				+ __('No fixture schedule — this line is added to the {0} only.', [__(this.frm.doctype)]) + '</div>';

		var pills = '<div class="form-group"><label class="control-label">' + __('Product Type')
			+ ' <span class="text-danger">*</span></label><div class="ill-desk-type-pills">';
		PRODUCT_TYPES.forEach(function (pt) {
			var active = (self.productType === pt.value) ? ' active' : '';
			pills += '<button type="button" class="btn btn-default ill-desk-type-pill' + active
				+ '" data-value="' + escapeHtml(pt.value) + '">' + escapeHtml(pt.label) + '</button>';
		});
		pills += '</div></div>';

		var html = header + pills
			+ '<div class="row ill-desk-line-grid">'
			+   (showLineSelect ? '<div class="col-md-12"><div class="ill-desk-ctl" data-ctl="line_select"></div></div>' : '')
			+   '<div class="col-md-3"><div class="ill-desk-ctl" data-ctl="fixture_type"></div></div>'
			+   '<div class="col-md-6"><div class="ill-desk-ctl" data-ctl="location"></div></div>'
			+   '<div class="col-md-3"><div class="ill-desk-ctl" data-ctl="qty"></div></div>'
			+   '<div class="col-md-12"><div class="ill-desk-ctl" data-ctl="notes"></div></div>'
			+ '</div>';
		$body.html(html);

		$body.find('.ill-desk-type-pill').on('click', function () {
			$body.find('.ill-desk-type-pill').removeClass('active');
			$(this).addClass('active');
			self.productType = $(this).data('value');
		});

		var slot = function (name) { return $body.find('.ill-desk-ctl[data-ctl="' + name + '"]'); };
		var c = this.controls = {};
		var byIdx = {};
		pendingLines.forEach(function (l) { byIdx[String(l.idx)] = l; });

		c.fixture_type = makeControl({
			fieldtype: 'Data', fieldname: 'fixture_type', label: __('Fixture Type'), reqd: 1,
			description: __('e.g. A1 — the schedule line id and the row\'s Fixture Type')
		}, slot('fixture_type'));

		c.location = makeControl({
			fieldtype: 'Data', fieldname: 'location', label: __('Section / Room'), reqd: this.schedule ? 1 : 0,
			description: this.schedule
				? __('Location on the schedule line and the row\'s Section / Room')
				: __('Optional grouping label for the print format')
		}, slot('location'));

		c.qty = makeControl({ fieldtype: 'Int', fieldname: 'qty', label: __('Qty'), reqd: 1 }, slot('qty'));
		c.notes = makeControl({ fieldtype: 'Small Text', fieldname: 'notes', label: __('Notes') }, slot('notes'));

		if (showLineSelect) {
			var options = [{ value: '__new__', label: __('+ New schedule line') }].concat(
				pendingLines.map(function (l) {
					return {
						value: String(l.idx),
						label: l.line_id + ' — ' + (l.location || __('no location'))
							+ ' (' + (l.manufacturer_type === 'OTHER' ? __('Other manufacturer') : __('Pending')) + ')'
					};
				}));
			c.line_select = makeControl({
				fieldtype: 'Select', fieldname: 'line_select', label: __('Schedule line'),
				options: options,
				description: __('Pick a pending portal line to configure it in place, or add a new line.'),
				onchange: function () {
					var val = c.line_select.get_value();
					var line = byIdx[val];
					if (line) {
						self.lineIdx = line.idx;
						c.fixture_type.set_value(line.line_id);
						c.location.set_value(line.location || '');
						c.qty.set_value(line.qty || 1);
						c.notes.set_value(line.notes || '');
					} else {
						self.lineIdx = null;
						c.fixture_type.set_value(data.next_fixture_type || '');
					}
				}
			}, slot('line_select'));
			c.line_select.set_value(this.lineIdx != null ? String(this.lineIdx) : '__new__');
		} else {
			this.lineIdx = null;
		}

		if (this.lineIdx == null) {
			c.fixture_type.set_value(this.fixtureType || data.next_fixture_type || '');
			c.location.set_value(this.location || '');
			c.qty.set_value(this.qty || 1);
			c.notes.set_value(this.notes || '');
		}

		// Suggestions: schedule locations ∪ section labels already on the form.
		var suggestions = (data.locations || []).concat(usedSectionLabels(this.frm));
		var seen = {};
		suggestions = suggestions.filter(function (v) { if (!v || seen[v]) return false; seen[v] = true; return true; });
		if (suggestions.length && c.location.$input) {
			var listId = 'ill-desk-locations-' + frappe.utils.get_random(6);
			var $list = $('<datalist></datalist>').attr('id', listId);
			suggestions.forEach(function (v) { $list.append($('<option></option>').attr('value', v)); });
			c.location.$input.attr('list', listId).after($list);
		}
	};

	DialogController.prototype.advanceFromLine = function () {
		var self = this;
		var c = this.controls;
		if (!this.productType) {
			frappe.msgprint({ title: __('Select a product type'), indicator: 'orange',
				message: __('Please choose Linear Fixture, LED Tape or LED Neon.') });
			return;
		}
		var fixtureType = (c.fixture_type.get_value() || '').trim();
		var location = (c.location.get_value() || '').trim();
		var qty = parseInt(c.qty.get_value(), 10) || 0;
		if (!fixtureType) {
			frappe.msgprint({ title: __('Fixture Type required'), indicator: 'orange',
				message: __('Enter a Fixture Type such as A1.') });
			return;
		}
		if (this.schedule && !location) {
			frappe.msgprint({ title: __('Section / Room required'), indicator: 'orange',
				message: __('Enter the Section / Room (location) for this schedule line.') });
			return;
		}
		if (qty < 1) {
			frappe.msgprint({ title: __('Quantity required'), indicator: 'orange',
				message: __('Quantity must be at least 1.') });
			return;
		}

		var proceed = function () {
			self.fixtureType = fixtureType;
			self.location = location;
			self.qty = qty;
			self.notes = (c.notes.get_value() || '').trim();
			self.renderConfigureStep();
		};

		var duplicateOnForm = !this.rowName && usedFixtureTypes(this.frm).indexOf(fixtureType) !== -1;
		var duplicateOnSchedule = this.lineIdx == null && !!this.pickerData
			&& (this.pickerData.lines || []).some(function (l) { return l.line_id === fixtureType; });
		if (duplicateOnForm || duplicateOnSchedule) {
			frappe.confirm(
				__('Fixture Type {0} is already used on {1}. Add another line with the same Fixture Type?',
					[escapeHtml(fixtureType), duplicateOnForm ? __('this document') : __('the schedule')]),
				proceed
			);
			return;
		}
		proceed();
	};

	// ── Step 3: Configure ────────────────────────────────────────────
	DialogController.prototype.renderConfigureStep = function () {
		var self = this;
		this.state = 'configure';
		this.renderStepIndicator();
		this.footer$().empty();

		// The configurator carries its own action buttons.
		this.dialog.get_primary_btn().hide();
		this.dialog.set_secondary_action_label(__('Back'));
		this.dialog.set_secondary_action(function () { self.renderLineStep(); });

		var $body = this.body$();
		$body.html(this.lineSummaryHtml()
			+ '<div class="text-center text-muted py-4 ill-desk-loading">'
			+ '<i class="fa fa-spinner fa-spin fa-2x mb-2"></i>'
			+ '<p>' + __('Loading configurator…') + '</p></div>');

		frappe.call({
			method: MARKUP_METHOD,
			args: { product_category: this.productType },
			callback: function (r) {
				if (self.state !== 'configure') return;
				var markup = r && r.message;
				if (!markup) {
					$body.find('.ill-desk-loading').replaceWith('<div class="alert alert-danger">'
						+ __('Could not load the configurator markup.') + '</div>');
					return;
				}
				self.mountConfigurator(markup);
			},
			error: function () {
				$body.find('.ill-desk-loading').replaceWith('<div class="alert alert-danger">'
					+ __('Could not load the configurator markup.') + '</div>');
			}
		});
	};

	DialogController.prototype.lineSummaryHtml = function () {
		var parts = [
			'<strong>' + escapeHtml(this.fixtureType) + '</strong>',
			this.location ? escapeHtml(this.location) : '<span class="text-muted">' + __('no Section / Room') + '</span>',
			__('Qty {0}', [this.qty]),
			escapeHtml(this.productType)
		];
		var target = this.schedule
			? __('→ schedule {0}', [escapeHtml(this.scheduleName || this.schedule)])
			: '<span class="text-warning">' + __('→ document only') + '</span>';
		return '<div class="ill-desk-line-summary">' + parts.join(' <span class="text-muted">·</span> ')
			+ ' <span class="text-muted ml-2">' + target + '</span></div>';
	};

	DialogController.prototype.mountConfigurator = function (markup) {
		var fixture = isFixture(this.productType);
		var scopeClass = fixture ? 'ill-configurator-fixture' : 'ill-configurator-tape-neon';
		var self = this;

		var $host = $('<div></div>')
			.addClass('ill-configurator ill-desk-configurator ' + scopeClass)
			.html(markup);
		this.body$().find('.ill-desk-loading').remove();
		this.body$().append($host);

		var context = {
			product_category: this.productType,
			is_neon: this.productType === 'LED Neon',
			schedule_name: '',
			project_name: '',
			line_idx: null,
			product_slug: '',
			qty: this.qty,
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
			$host.html('<div class="alert alert-danger">' + __('Failed to initialize the configurator.') + '</div>');
		}
	};

	DialogController.prototype.teardownConfigurator = function () {
		if (this.configurator && typeof this.configurator.destroy === 'function') {
			try { this.configurator.destroy(); } catch (e) { /* noop */ }
		}
		this.configurator = null;
	};

	DialogController.prototype.toggleConfiguratorButtons = function (disabled) {
		this.body$().find('.ill-desk-configurator button').prop('disabled', !!disabled);
	};

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
			variant_origin: variantOriginFor(this.frm)
		};
		if (isFixture(productType)) {
			args.product_slug = payload.product_slug || '';
		} else {
			if (payload.segments) args.segments_json = JSON.stringify(payload.segments);
			if (payload.tape_neon_template) args.tape_neon_template = payload.tape_neon_template;
		}

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

	DialogController.prototype.applyRowToForm = function (msg) {
		var frm = this.frm;
		var values = msg.row_values || {};
		var childDoctype = frm.doctype + ' Item';
		var row = null;

		if (this.rowName && locals[childDoctype] && locals[childDoctype][this.rowName]) {
			row = locals[childDoctype][this.rowName];
		} else {
			// Reuse the blank default row a new document starts with.
			row = (frm.doc.items || []).find(function (r) { return !r.item_code && !r.ill_configured_product; }) || null;
			if (!row) row = frm.add_child('items', {});
		}
		Object.keys(values).forEach(function (k) { row[k] = values[k]; });
		row.__unsaved = 1;

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
		this.addedCount += 1;
		this.rowName = null;

		frappe.show_alert({
			message: msg.schedule
				? __('Added {0} · {1} (saved to schedule {2})', [escapeHtml(msg.fixture_type), escapeHtml(msg.item_code), escapeHtml(msg.schedule)])
				: __('Added {0} · {1}', [escapeHtml(msg.fixture_type), escapeHtml(msg.item_code)]),
			indicator: 'green'
		}, 6);
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
			+ '<h5 class="mt-3">' + __('Added {0} · {1}', [escapeHtml(msg.fixture_type), escapeHtml(msg.item_code)]) + '</h5>'
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
			self.notes = '';
			self.renderLineStep();
		});
		this.footer$().find('.ill-desk-done-btn').on('click', function () { self.dialog.hide(); });
	};

}(window));
