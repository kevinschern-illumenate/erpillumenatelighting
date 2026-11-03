// Desk Configurator Dialog: steps 1-3 (project and schedule, line details, configure). Split verbatim from desk_dialog.js (plan 7.5);
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
			if (ctx.linked_missing) {
				// The linked schedule was deleted: unlink it so a new pick can take its place.
				self.linkedToForm = false;
				self.schedule = null;
				if (self.frm.fields_dict.ill_fixture_schedule) self.frm.set_value('ill_fixture_schedule', null);
				frappe.show_alert({
					message: __('Fixture Schedule {0} no longer exists; pick or create a schedule for this {1}.',
						[escapeHtml(ctx.linked_missing), __(self.frm.doctype)]),
					indicator: 'orange'
				}, 8);
			}
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
				if (res.reopened) {
					self.scheduleStatus = res.status;
					frappe.show_alert({
						message: __('Reopened schedule {0} ({1}); nothing still quotes it, so no new version was needed.',
							[escapeHtml(res.name), escapeHtml(res.status)]),
						indicator: 'green'
					}, 7);
					self.renderLineStep();
					return;
				}
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
		if (this.configurator && this.configurator.exportRequest) this.initialRequest = this.configurator.exportRequest();
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
		var rowLines = (this.frm.doc.items || []).map(function (r) { return r.ill_schedule_line_id; }).filter(Boolean);
		if (this.scheduleLineName) rowLines.push(this.scheduleLineName);
		var load = this.schedule
			? this.call('get_schedule_picker_data', {
				schedule: this.schedule, used_json: JSON.stringify(used), row_lines_json: JSON.stringify(rowLines)
			})
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
			self.relinkRows(data.line_aliases);
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
			if (self.scheduleLineName) {
				var selected = (data.lines || []).find(function (line) { return line.name === self.scheduleLineName; });
				if (selected) self.lineIdx = selected.idx;
				self.scheduleLineName = null;
			}
			self.renderLineForm(data);
		}).catch(function (err) {
			console.error('[illumenate_lighting] Could not load the schedule', err);
			$body.html('<div class="alert alert-danger">' + __('Could not load the schedule.') + ' '
				+ __('Close this dialog, reload the {0} and try again; if it keeps failing, check the Error Log.', [__(self.frm.doctype)])
				+ '</div>');
		});
	};

	// Rows linked to an earlier version of the schedule follow their line
	// (same line key) to the current version, so reconfiguring replaces them.
	DialogController.prototype.relinkRows = function (aliases) {
		if (!aliases || !Object.keys(aliases).length) return;
		var moved = 0;
		(this.frm.doc.items || []).forEach(function (r) {
			var target = aliases[r.ill_schedule_line_id];
			if (target) { r.ill_schedule_line_id = target; moved += 1; }
		});
		if (this.scheduleLineName && aliases[this.scheduleLineName]) this.scheduleLineName = aliases[this.scheduleLineName];
		if (moved) {
			this.frm.refresh_field('items');
			this.frm.dirty();
		}
	};

	DialogController.prototype.renderLineForm = function (data) {
		var self = this;
		var $body = this.body$();
		var pendingLines = (data.lines || []).filter(function (l) { return l.is_pending || !!l.initial_request || l.idx === self.lineIdx; });
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
			var family = $(this).data('value');
			if (self.productType !== family) self.initialRequest = null;
			self.productType = family;
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
							+ ' (' + (l.manufacturer_type === 'OTHER' ? __('Other manufacturer') : __(l.configuration_status || 'Pending')) + ')'
					};
				}));
			c.line_select = makeControl({
				fieldtype: 'Select', fieldname: 'line_select', label: __('Schedule line'),
				options: options,
				description: __('Pick a line to reconfigure it (its rows on this document are replaced), or add a new line.'),
				onchange: function () {
					if (self.restoringLineSelection) return;
					var val = c.line_select.get_value();
					var line = byIdx[val];
					if (line) {
						if (self.lineIdx !== line.idx || !self.initialRequest) self.initialRequest = line.initial_request || null;
						self.lineIdx = line.idx;
						var family = line.product_type || (line.initial_request || {}).family;
						if (family) self.productType = family;
						$body.find('.ill-desk-type-pill').each(function () { $(this).toggleClass('active', $(this).data('value') === self.productType); });
						c.fixture_type.set_value(line.line_id);
						c.location.set_value(line.location || '');
						c.qty.set_value(line.qty || 1);
						c.notes.set_value(line.notes || '');
						self.fixtureType = line.line_id; self.location = line.location || ''; self.qty = line.qty || 1; self.notes = line.notes || '';
					} else {
						if (self.lineIdx != null) self.initialRequest = null;
						self.lineIdx = null;
						c.fixture_type.set_value(data.next_fixture_type || '');
					}
				}
			}, slot('line_select'));
			self.restoringLineSelection = true;
			c.line_select.set_value(this.lineIdx != null ? String(this.lineIdx) : '__new__');
			self.restoringLineSelection = false;
		} else {
			this.lineIdx = null;
		}

		{
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
				message: __('Please choose the type of product to configure.') });
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

		// Rows of the line being reconfigured are replaced, so they are not duplicates.
		var editedLine = this.lineIdx != null
			? ((this.pickerData || {}).lines || []).find(function (l) { return l.idx === self.lineIdx; })
			: null;
		var duplicateOnForm = !this.rowName && usedFixtureTypes(this.frm, editedLine && editedLine.name).indexOf(fixtureType) !== -1;
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
		var loadToken = this.markupToken = {};
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
			args: { product_category: this.productType, selected_template: (this.initialRequest || {}).template },
			callback: function (r) {
				if (self.closed || self.state !== 'configure' || self.markupToken !== loadToken) return;
				var markup = r && r.message;
				if (!markup) {
					$body.find('.ill-desk-loading').replaceWith('<div class="alert alert-danger">'
						+ __('Could not load the configurator markup.') + '</div>');
					return;
				}
				self.mountConfigurator(markup);
			},
			error: function () {
				if (self.closed || self.state !== 'configure' || self.markupToken !== loadToken) return;
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
			escapeHtml(productTypeLabel(this.productType))
		];
		var target = this.schedule
			? __('→ schedule {0}', [escapeHtml(this.scheduleName || this.schedule)])
			: '<span class="text-warning">' + __('→ document only') + '</span>';
		return '<div class="ill-desk-line-summary">' + parts.join(' <span class="text-muted">·</span> ')
			+ ' <span class="text-muted ml-2">' + target + '</span></div>';
	};

	DialogController.prototype.mountConfigurator = function (markup) {
		if (isCatalog(this.productType)) return this.mountCatalogConfigurator(markup);
		var fixture = isFixture(this.productType);
		var sheet = isSheet(this.productType);
		var scopeClass = fixture ? 'ill-configurator-fixture' : (sheet ? 'ill-configurator-sheet' : 'ill-configurator-tape-neon');
		var self = this;

		var $host = $('<div></div>')
			.addClass('ill-configurator ill-desk-configurator ' + scopeClass)
			.html(markup);
		this.body$().find('.ill-desk-loading').remove();
		this.body$().append($host);

		var context = {
			product_category: this.productType,
			initial_request: this.initialRequest ? JSON.parse(JSON.stringify(this.initialRequest)) : null,
			selected_template: (this.initialRequest || {}).template,
			groups_enabled: !!(this.context && this.context.groups_enabled),
			is_neon: this.productType === 'LED Neon',
			is_tape: this.productType === 'LED Tape' || this.productType === 'COB Tape',
			is_tape_neon: !fixture && !sheet,
			has_templates: !!$host.find('[name=fixture_template_code] option[value!=""]').length,
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
			} else if (sheet) {
				this.configurator = new root.IllConfigurator.LedSheet($host[0], context);
			} else {
				this.configurator = new root.IllConfigurator.Coordinator($host[0], context);
			}
			this.configurator.init();
		} catch (e) {
			console.error('[illumenate_lighting] Failed to mount configurator', e);
			$host.html('<div class="alert alert-danger">' + __('Failed to initialize the configurator.') + '</div>');
		}
	};

	// Extrusion Kit / Power Supply / Controller: the portal's family classes; the
	// line details come from step 2, so the markup omits its own target and fields.
	DialogController.prototype.mountCatalogConfigurator = function (markup) {
		var self = this;
		var request = this.initialRequest ? JSON.parse(JSON.stringify(this.initialRequest)) : null;
		var $host = $('<div></div>')
			.addClass('ill-configurator ill-desk-configurator ' + CATALOG_SCOPES[this.productType])
			.html(markup);
		this.body$().find('.ill-desk-loading').remove();
		this.body$().append($host);
		try {
			this.configurator = new root.IllConfigurator[CATALOG_CLASSES[this.productType]]($host[0], {
				kind: this.productType,
				initial_request: request,
				selected_template: (request || {}).template || null,
				product_slug: (request || {}).product_slug || '',
				can_save: true,
				show_pricing: true,
				show_stock_qty: true,
				saveHandler: function (payload) { self.onConfiguratorSave(payload); }
			});
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

}(window));
