/**
 * Shared Configurator (Phase 4)
 *
 * Provides:
 *   - window.IllConfigurator namespace + registry
 *   - IllConfigurator.Base class with rootEl-scoped DOM helpers
 *   - Shared schedule-context loaders (project / schedule / line dropdowns)
 *   - Backwards-compatibility globals for legacy callers (product_detail.js,
 *     the Guided Wizard mode of configure.html, the desk configurator dialog,
 *     etc.).
 *
 * Multi-instance-safe: every DOM lookup goes through `instance.$(selector)`
 * which scopes to the configurator root element passed at construction time.
 */
(function (root) {
	'use strict';

	if (root.IllConfigurator) return;

	var registry = [];
	var defaultFixture = null;
	var defaultTapeNeon = null;

	// ───────────────────────────────────────────────────────────────────
	// Base class
	// ───────────────────────────────────────────────────────────────────
	function Base(rootEl, context) {
		// rootEl: DOM node, jQuery wrapper, or selector string. Defaults to document.
		var $r;
		if (!rootEl) {
			$r = $(document);
		} else if (rootEl.jquery) {
			$r = rootEl;
		} else {
			$r = $(rootEl);
		}
		this.$root = $r;
		this.rootEl = $r[0] || document;
		this.context = context || {};
		var handoff = this.context.quiz_handoff;
		if (!this.context.initial_request && handoff && Object.keys(handoff).length) {
			var neonTape = this.context.is_tape_neon;
			var handoffSelections = {};
			var aliases = neonTape ? {moisture: 'environment_rating', cct: 'cct', finish: 'finish', dimming: 'dimming_protocol_code'} : {moisture: 'environment_rating_code', cct: 'cct_code', lens: 'lens_appearance_code', finish: 'finish_code', mounting: 'mounting_method_code', dimming: 'dimming_protocol_code'};
			Object.keys(aliases).forEach(function (key) { if (handoff[key] != null) handoffSelections[aliases[key]] = handoff[key]; });
			this.context.initial_request = {template: handoff.template, selections: handoffSelections};
		}
		var draftId = new URLSearchParams(root.location.search).get('draft');
		if (draftId && this.context.schedule_name) {
			try {
				var draft = JSON.parse(root.sessionStorage.getItem('ill-line-draft:' + draftId) || 'null');
				if (draft && draft.schedule === this.context.schedule_name && Date.now() - draft.savedAt < 86400000) {
					this.context.draft = draft.metadata;
					this.context.draft_id = draftId;
				}
			} catch (_) {}
		}
		var resumeId = new URLSearchParams(root.location.search).get('resume');
		if (resumeId) {
			try {
				var resumed = JSON.parse(root.sessionStorage.getItem('ill-config-view:' + resumeId) || 'null');
				if (resumed && resumed.schedule === this.context.schedule_name && Date.now() - resumed.savedAt < 86400000) {
					this.context.initial_request = resumed.request;
					this.context.selected_template = resumed.request.template;
					this.context.expected_modified = resumed.expected_modified || this.context.expected_modified;
					this.context.resume_id = resumeId;
				}
			} catch (_) {}
		}
		var group = ((this.context.initial_request || {}).selections || {}).group_request;
		if (group && group.members && group.members.length) {
			this.context.initial_group = JSON.parse(JSON.stringify(group));
			var memberSelections = Object.assign({}, group.shared, group.members[0].input, group.power);
			if (group.family === 'Linear Fixture') memberSelections.fixture_template_code = group.template;
			if (group.family === 'LED Sheet') memberSelections.template = group.template;
			this.context.initial_request = {family: group.family, template: group.template, selections: memberSelections, segments: memberSelections.segments};
			this.context.selected_template = group.template;
		}
		this.selections = {};
		this.instanceId = 'ill-cfg-' + (++Base._uid);
		this.destroyed = false;
		this._requests = Object.create(null);
		this._revision = 0;
		this._idMap = Object.create(null);
		this._disposers = [];
		this._scopeIds();
		this.$root.find('select').data('illConfiguratorOwner', this);
		var self = this;
		this.$root.on('click.' + this.instanceId, '[data-configurator-mode]', function (event) {
			if (!self.exportRequest) return;
			event.preventDefault();
			var request = self.exportRequest(), id = root.crypto.randomUUID();
			try {
				root.sessionStorage.setItem('ill-config-view:' + id, JSON.stringify({request: request, schedule: self.context.schedule_name, expected_modified: self.context.expected_modified, savedAt: Date.now()}));
			} catch (_) { frappe.msgprint(__('Allow session storage to preserve selections when changing views.')); return; }
			var url = new URL(root.location.href);
			url.searchParams.set('mode', this.dataset.configuratorMode);
			url.searchParams.set('resume', id);
			if (request.template) url.searchParams.set('template', request.template);
			root.location.href = url.toString();
		});
		this.$root.on('input.' + this.instanceId + ' change.' + this.instanceId, 'input, select, textarea', function (event) {
			if (!self._applyingRestore && (event.originalEvent || event.illUserSelection)) {
				var input = this;
				Object.keys(self._restoreFields || {}).forEach(function (selector) {
					if (self.$(selector)[0] === input) delete self._restoreFields[selector];
				});
			}
			if (self.isPopulating) return;
			if (['projectSelect', 'scheduleSelect', 'lineSelect'].indexOf(this.getAttribute('data-ill-original-id') || this.id) >= 0) return;
			self.invalidateValidation();
			if (self._updateButtons) self._updateButtons();
		});
		registry.push(this);
		this.delay(function () { if (root.IllConfigurator.attachGroupEditor) root.IllConfigurator.attachGroupEditor(self); }, 0);
	}
	Base._uid = 0;

	// Scoped jQuery lookup. If $root is the document we still scope via .find()
	// so descendant-only searches behave the same in both modes.
	Base.prototype.$ = function (selector) {
		if (!selector) return this.$root;
		if (this.destroyed) return $();
		selector = this.selector(selector);
		// Allow `#id` and `[name=...]` selectors to remain scoped.
		if (this.$root[0] === document) {
			return $(selector);
		}
		return this.$root.find(selector);
	};

	Base.prototype.selector = function (selector) {
		var ids = this._idMap;
		return selector.replace(/#([A-Za-z][\w-]*)/g, function (match, id) {
			return ids[id] ? '#' + ids[id] : match;
		});
	};

	Base.prototype._scopeIds = function () {
		// Legacy full-page callers keep their global IDs; embedded forms get unique label targets.
		if (this.rootEl === document) return;
		var self = this;
		this.$root.find('[id]').each(function () {
			var original = this.getAttribute('data-ill-original-id') || this.id;
			self._idMap[original] = self.instanceId + '-' + original;
			this.setAttribute('data-ill-original-id', original);
			this.id = self._idMap[original];
		});
		this.$root.find('[for], [aria-labelledby], [aria-describedby], [aria-controls]').each(function () {
			var el = this;
			['for', 'aria-labelledby', 'aria-describedby', 'aria-controls'].forEach(function (attr) {
				var value = el.getAttribute('data-ill-original-' + attr) || el.getAttribute(attr);
				if (!value) return;
				el.setAttribute('data-ill-original-' + attr, value);
				el.setAttribute(attr, value.split(/\s+/).map(function (id) { return self._idMap[id] || id; }).join(' '));
			});
		});
	};

	Base.prototype.invalidateValidation = function () {
		this._revision++;
		this.currentResult = this.lastResult = this.lastValidation = null;
		this.$('[data-action="add-to-schedule"], [data-action="build-item"], #btnSaveToSchedule').prop('disabled', true);
		this.$('[data-action="validate"]').each(function () {
			var label = $(this).data('illCalculationLabel');
			if (label) $(this).html(label);
		});
	};

	Base.prototype.inputSignature = function () {
		return JSON.stringify(this.$root.find('input, select, textarea').toArray().map(function (el) {
			return [el.name || el.id, el.value, el.type === 'checkbox' || el.type === 'radio' ? el.checked : null];
		}));
	};

	Base.prototype.validationGuard = function () {
		var self = this, revision = this._revision, signature = this.inputSignature();
		return function () { return !self.destroyed && self._revision === revision && self.inputSignature() === signature; };
	};

	Base.prototype.request = function (options) {
		if (this.destroyed) return;
		var self = this, key = options.method;
		var token = {};
		this._requests[key] = token;
		var args = Object.assign({}, options);
		var isCurrent = args.isCurrent;
		delete args.isCurrent;
		['callback', 'error', 'always'].forEach(function (event) {
			var handler = args[event];
			if (!handler) return;
			args[event] = function () {
				if (self.destroyed || self._requests[key] !== token || (isCurrent && !isCurrent())) return;
				var result = handler.apply(this, arguments);
				if (event === 'callback') self.applyRestoreFields();
				return result;
			};
		});
		return frappe.call(args);
	};

	Base.prototype.loadPowerOptions = function (templateType, template) {
		var $select = this.$('[name="dimming_protocol_code"], [name="br_dimming_protocol_code"]');
		if (!$select.length || !template) return;
		$select.empty().append($('<option></option>').val('').text(__('Any compatible protocol')));
		return this.request({
			method: 'illumenate_lighting.illumenate_lighting.api.driver_catalog.input_protocols',
			args: { template_type: templateType, template: template },
			callback: function (r) {
				((r.message || {}).protocols || []).forEach(function (protocol) {
					$select.append($('<option></option>').val(protocol).text(protocol));
				});
			}
		});
	};

	Base.prototype.queueRestoreFields = function (fields) {
		this._restoreFields = Object.assign(this._restoreFields || {}, fields);
		this.applyRestoreFields();
	};

	Base.prototype.canCalculateRestored = function () {
		var self = this;
		var missing = Object.keys(this._restoreFields || {}).filter(function (selector) { return self.$(selector).length; });
		if (!missing.length) return true;
		frappe.msgprint(__('Some saved choices are not available yet. Wait for options to load, or select an available replacement before calculating.'));
		this.$(missing[0]).show().trigger('focus');
		return false;
	};

	Base.prototype.applyRestoreFields = function () {
		if (this.destroyed || this._applyingRestore || !this._restoreFields) return;
		this._applyingRestore = true;
		var self = this, changed = [];
		Object.keys(this._restoreFields).forEach(function (selector) {
			var value = self._restoreFields[selector];
			var $input = self.$(selector).first();
			if (!$input.length) return;
			if ($input.is('select') && !$input.find('option').toArray().some(function (o) { return String(o.value) === String(value); })) return;
			delete self._restoreFields[selector];
			if ($input.is(':checkbox')) $input.prop('checked', [true, 1, '1', 'true'].includes(value));
			else $input.val(value == null ? '' : value);
			changed.push($input);
		});
		// Apply values together before starting dependent option requests.
		changed.forEach(function ($input) { $input.trigger('change'); });
		this._applyingRestore = false;
	};

	Base.prototype.restorePower = function (selections) {
		var fields = {
			'#includePowerSupply': selections.include_power_supply == null ? true : selections.include_power_supply,
			'#overrideMaxRunCheck': !!selections.override_max_run_ft,
			'#overrideMaxRunInput': selections.override_max_run_ft || '',
			'[name="dimming_protocol_code"]': selections.dimming_protocol_code || ''
		};
		this.queueRestoreFields(fields);
	};

	Base.prototype.restoreSegment = function ($card, segment, family) {
		var values = {}, type = segment.end_type || 'Endcap';
		if (family === 'linear') {
			values = Object.assign({}, segment, {
				length_unit: 'mm', requested_length_mm: segment.requested_length_mm,
				start_leader_cable_length_in: Number(segment.start_leader_cable_length_mm || 0) / 25.4,
				end_jumper_cable_length_in: Number(segment.end_jumper_cable_length_mm || 0) / 25.4
			});
			$card.data('prevUnit', 'mm');
			$card.find('.feet-inches-row').hide();
			$card.find('[name="requested_length_mm"]').show();
		} else {
			Object.keys(segment).forEach(function (key) {
				var name = family === 'tape' && key.startsWith('tape_') ? key : family + '_' + key;
				values[name] = segment[key];
			});
			var unit = segment[family === 'tape' ? 'tape_length_unit' : 'fixture_length_unit'];
			$card.find('.tape-ft-in-row, .feet-inches-row, .neon-ft-in-row').toggle(unit === 'ft_in');
		}
		Object.keys(values).forEach(function (key) {
			$card.find('[name="' + key + '"]').val(values[key] == null ? '' : values[key]);
		});
		$card.find('.jumper-fields').toggle(type === 'Jumper');
		$card.find('.endcap-fields').toggle(type !== 'Jumper');
		$card.find('[data-type], [data-end-type]').each(function () {
			var active = (this.dataset.type || this.dataset.endType) === type;
			$(this).toggleClass('active btn-primary', active).toggleClass('btn-outline-secondary', !active);
		});
		$card[0].dataset.inheritedFeedDirection = segment.start_feed_direction || '';
		$card[0].dataset.inheritedPowerFeedType = segment.start_power_feed_type || '';
		$card[0].dataset.inheritedCableLength = family === 'linear' ? (segment.start_leader_cable_length_mm || 0) : (segment.start_lead_length_inches || 0);
	};

	Base.prototype.debounce = function (callback, wait) {
		var self = this;

		var wrapped = debounce(function () { if (!self.destroyed) callback.apply(this, arguments); }, wait);
		this._disposers.push(wrapped.cancel);
		return wrapped;
	};

	Base.prototype.delay = function (callback, wait) {
		var self = this;
		var timer = setTimeout(function () { if (!self.destroyed) callback(); }, wait);
		this._disposers.push(function () { clearTimeout(timer); });
		return timer;
	};

	Base.prototype.listen = function (target, event, callback, options) {
		target.addEventListener(event, callback, options);
		this._disposers.push(function () { target.removeEventListener(event, callback, options); });
	};

	Base.prototype.setScheduleSnapshot = function (snapshot) {
		this.scheduleSnapshot = snapshot || null;
	};

	Base.prototype.saveScheduleConfiguration = function (data, callbacks) {
		if (this.destroyed || this._saving) return;
		var self = this, snapshot = this.scheduleSnapshot || {};
		var schedule = data.schedule_name || this.$('#scheduleSelect').val() || this.context.schedule_name;
		var selected = data.line_idx !== undefined ? data.line_idx : this.$('#lineSelect').val();
		if (data.line_idx === undefined && !selected) {
			frappe.msgprint(__('Select an existing line or choose New Line before saving.'));
			return;
		}
		if (selected === '__new__' || selected === '') selected = null;
		var line = (snapshot.lines || []).find(function (row) { return String(row.idx) === String(selected); });
		var args = Object.assign({}, data, {
			schedule_name: schedule, line_key: line ? line.line_key : null,
			line_idx: line ? null : selected, expected_modified: snapshot.modified || (schedule === this.context.schedule_name ? this.context.expected_modified : null),
			metadata: JSON.stringify(data.metadata || this.context.draft || {})
		});
		if (line && this.context.initial_request && line.line_key === this.context.line_key && schedule === this.context.schedule_name) {
			args.expected_modified = this.context.expected_modified;
		}
		if (!schedule || !args.expected_modified) {
			frappe.msgprint(__('Select a schedule and wait for its lines to load before saving.'));
			return;
		}
		var signature = JSON.stringify(args);
		if (!this._saveAttempt || this._saveAttempt.signature !== signature) {
			this._saveAttempt = { signature: signature, key: root.crypto.randomUUID() };
		}
		args.idempotency_key = this._saveAttempt.key;
		if (typeof args.selections !== 'string') args.selections = JSON.stringify(args.selections);
		if (args.segments && typeof args.segments !== 'string') args.segments = JSON.stringify(args.segments);
		this._saving = true;
		callbacks = callbacks || {};
		return this.request({
			method: 'illumenate_lighting.illumenate_lighting.portal.configuration.save', args: args,
			freeze: true, freeze_message: __('Saving configuration...'),
			callback: function (r) {
				if (r.message && r.message.success) {
					if (self.context.draft_id) root.sessionStorage.removeItem('ill-line-draft:' + self.context.draft_id);
					if (self.context.resume_id) root.sessionStorage.removeItem('ill-config-view:' + self.context.resume_id);
					if (callbacks.success) callbacks.success(r.message);
					else root.location.href = '/portal/schedules/' + encodeURIComponent(schedule);
				} else frappe.msgprint((r.message || {}).error || __('The configuration could not be saved.'));
			},
			error: function () { if (callbacks.error) callbacks.error(); },
			always: function () { self._saving = false; if (self._updateButtons) self._updateButtons(); }
		});
	};

	// Convenience: find a control by `name` attribute within scope.
	Base.prototype.$name = function (name) {
		return this.$('[name="' + name + '"]');
	};

	Base.prototype.destroy = function () {
		var self = this;
		this.destroyed = true;
		this._requests = Object.create(null);
		this.$root.off('.' + this.instanceId).find('*').off('.' + this.instanceId);
		this._disposers.forEach(function (dispose) { dispose(); });
		this.$root.find('.ill-template-picker').each(function () {
			var picker = $(this).data('illTemplatePicker');
			if (picker && picker.owner === self) picker.destroy();
		});
		var idx = registry.indexOf(this);
		if (idx !== -1) registry.splice(idx, 1);
		if (defaultFixture === this) defaultFixture = null;
		if (defaultTapeNeon === this) defaultTapeNeon = null;
	};

	// ───────────────────────────────────────────────────────────────────
	// Shared utilities
	// ───────────────────────────────────────────────────────────────────
	function debounce(func, wait) {
		var timeout;
		var wrapped = function () {
			var ctx = this, args = arguments;
			clearTimeout(timeout);
			timeout = setTimeout(function () { func.apply(ctx, args); }, wait);
		};
		wrapped.cancel = function () { clearTimeout(timeout); };
		return wrapped;
	}

	function selectRequest($select, options) {
		var token = {}, callback = options.callback;
		$select.data('illLoadToken', token);
		options.callback = function (r) {
			var owner = $select.data('illConfiguratorOwner');
			if ($select.data('illLoadToken') !== token || (owner && owner.destroyed)) return;
			callback(r);
		};
		return frappe.call(options);
	}

	/**
	 * Load user projects into a <select>. Returns the frappe.call promise.
	 * Used by both fixture and tape/neon configurators.
	 */
	function loadUserProjects($select, preSelect) {
		if (!$select || !$select.length) return;
		return selectRequest($select, {
			method: 'illumenate_lighting.illumenate_lighting.api.portal.get_user_projects_for_configurator',
			callback: function (r) {
				var msg = r.message || {};
				if (!msg.success) return;
				$select.find('option:not(:first)').remove();
				(msg.projects || []).forEach(function (p) {
					$select.append(
						$('<option></option>').val(p.value).text(p.label || p.value)
					);
				});
				if (preSelect) {
					$select.val(preSelect).trigger('change');
				}
			}
		});
	}

	function loadSchedulesForProject(projectName, $scheduleSelect, preSelect) {
		if (!$scheduleSelect || !$scheduleSelect.length) return;
		return selectRequest($scheduleSelect, {
			method: 'illumenate_lighting.illumenate_lighting.api.portal.get_schedules_for_project',
			args: { project_name: projectName },
			callback: function (r) {
				var msg = r.message || {};
				$scheduleSelect.find('option:not(:first)').remove();
				(msg.schedules || []).forEach(function (s) {
					$scheduleSelect.append(
						$('<option></option>').val(s.value).text(s.label || s.value)
					);
				});
				$scheduleSelect.prop('disabled', false);
				if (preSelect) {
					$scheduleSelect.val(preSelect).trigger('change');
				}
			}
		});
	}

	function loadSchedulesForUser($scheduleSelect, preSelect) {
		return selectRequest($scheduleSelect, {
			method: 'illumenate_lighting.illumenate_lighting.api.webflow_schedule.get_user_schedules',
			callback: function (r) {
				if (!(r.message && r.message.success)) return;
				var schedules = r.message.schedules || [];
				$scheduleSelect.find('option:not(:first)').remove();
				schedules.forEach(function (s) {
					$scheduleSelect.append(
						$('<option></option>').val(s.name).text(
							(s.schedule_name || s.name) + (s.project_name ? ' (' + s.project_name + ')' : '')
						)
					);
				});
				$scheduleSelect.prop('disabled', false);
				if (preSelect) $scheduleSelect.val(preSelect);
			}
		});
	}

	function loadLinesForSchedule(scheduleName, $lineSelect, preSelect) {
		return selectRequest($lineSelect, {
			method: 'illumenate_lighting.illumenate_lighting.api.portal.get_schedule_lines_for_configurator',
			args: { schedule_name: scheduleName },
			callback: function (r) {
				var msg = r.message || {};
				var lines = Array.isArray(msg) ? msg : (msg.lines || []);
				var owner = $lineSelect.data('illConfiguratorOwner');
				if (owner) owner.setScheduleSnapshot(msg);
				$lineSelect.find('option:not(:first):not([value="__new__"])').remove();
				lines.forEach(function (l) {
					var idx = (l.idx !== undefined ? l.idx : l.value);
					var label = (l.label || l.line_id || ('Row ' + idx)) + (l.configured_fixture ? ' \u2713' : '');
					$lineSelect.append($('<option></option>').val(idx).text(label));
				});
				$lineSelect.prop('disabled', false);
				if (preSelect !== null && preSelect !== undefined) {
					$lineSelect.val(preSelect);
				}
			}
		});
	}

	// ───────────────────────────────────────────────────────────────────
	// Pill-selector renderer (lightweight; subclasses may use their own)
	// ───────────────────────────────────────────────────────────────────
	/**
	 * Render a pill selector inside `$container` (a `.pill-selector` element)
	 * with optional `<select>` fallback for mobile.
	 */
	function renderPillSelector(opts) {
		var $container = opts.$container;
		var $select = opts.$select;
		var items = opts.items || [];
		var valueKey = opts.valueKey || 'value';
		var labelKey = opts.labelKey || 'label';
		var pillClass = opts.pillClass || 'pill';
		var useButton = opts.useButton !== false;
		var onClick = opts.onClick;

		$container.empty();
		if ($select) {
			$select.empty().append('<option value="">Select...</option>');
		}

		if (!items.length) {
			$container.append('<span class="text-muted">No options available</span>');
			return;
		}

		items.forEach(function (item) {
			var val = item[valueKey];
			var label = item[labelKey] || val;
			var $pill = useButton
				? $('<button type="button"></button>').addClass(pillClass)
				: $('<span></span>').addClass(pillClass);
			$pill.attr('data-value', val);
			if (item.code !== undefined) $pill.attr('data-code', item.code);
			$pill.text(label);
			if (item.is_default) $pill.addClass('default');
			if (onClick) {
				$pill.on('click', function (e) {
					if (e && e.preventDefault) e.preventDefault();
					$container.find('.' + pillClass).removeClass('active');
					$pill.addClass('active');
					if ($select) $select.val(val);
					onClick(val, item, $pill);
				});
			}
			$container.append($pill);

			if ($select) {
				var $opt = $('<option></option>').val(val).text(label);
				if (item.is_default) $opt.attr('selected', true);
				$select.append($opt);
			}
		});

		if ($select) {
			$select.off('change.illShared').on('change.illShared', function () {
				var v = $(this).val();
				$container.find('.' + pillClass).removeClass('active');
				$container.find('.' + pillClass + '[data-value="' + v + '"]').addClass('active');
				if (onClick) {
					var matched = items.find(function (i) { return i[valueKey] === v; });
					onClick(v, matched, $container.find('.' + pillClass + '.active'));
				}
			});
		}
	}

	// ───────────────────────────────────────────────────────────────────
	// Template / product-family card picker
	// ───────────────────────────────────────────────────────────────────
	function escapeHtml(value) {
		return String(value == null ? '' : value)
			.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
			.replace(/"/g, '&quot;').replace(/'/g, '&#39;');
	}

	/**
	 * Render the visual template picker (image cards + search) that drives a
	 * hidden `<select name="fixture_template_code">`.
	 *
	 * The <select> stays the single source of truth: cards call
	 * `$select.val(code).trigger('change')`, and any external change to the
	 * select (mobile fallback, quiz hand-off, reset) re-syncs the cards.
	 *
	 * opts:
	 *   $container  – element that receives the picker markup
	 *   $select     – the hidden <select>; options carry data-name,
	 *                 data-image, data-gallery, data-description
	 *   templates   – optional explicit list; defaults to the select's options
	 *   labels      – optional i18n overrides
	 */
	function renderTemplateCards(opts) {
		var $container = opts.$container;
		var $select = opts.$select;
		if (!$container || !$container.length || !$select || !$select.length) return null;
		var previousPicker = $container.data('illTemplatePicker');
		if (previousPicker) previousPicker.destroy();
		var namespace = '.illTemplateCards' + (++Base._uid);

		var labels = $.extend({
			search: __('Search templates…'),
			change: __('Change'),
			empty: __('No templates match your search.'),
			count: function (n, total) { return n === total ? __('{0} templates', [total]) : __('{0} of {1} templates', [n, total]); }
		}, opts.labels || {});

		var templates = opts.templates || $select.find('option').toArray()
			.filter(function (o) { return o.value; })
			.map(function (o) {
				var $o = $(o);
				var gallery = [];
				try { gallery = JSON.parse($o.attr('data-gallery') || '[]'); } catch (_) { gallery = []; }
				return {
					template_code: o.value,
					template_name: $o.attr('data-name') || $o.text().replace(/\s*\([^)]*\)\s*$/, '').trim(),
					image: $o.attr('data-image') || (gallery[0] && gallery[0].image) || '',
					gallery: gallery,
					description: $o.attr('data-description') || ''
				};
			});

		var html = '<div class="ill-template-picker-toolbar">'
			+ '<input type="search" class="ill-template-search" placeholder="' + escapeHtml(labels.search) + '" aria-label="' + escapeHtml(labels.search) + '">'
			+ '<span class="ill-template-picker-count" role="status" aria-live="polite"></span>'
			+ '</div>'
			+ '<div class="ill-template-selected" style="display:none;"></div>'
			+ '<div class="ill-template-grid" role="listbox"></div>';
		$container.addClass('ill-template-picker').html(html);
		$select.addClass('ill-template-select-driven');

		var $grid = $container.find('.ill-template-grid');
		var $search = $container.find('.ill-template-search');
		var $count = $container.find('.ill-template-picker-count');
		var $selected = $container.find('.ill-template-selected');

		function cardHtml(t, isSelected) {
			var media = t.image
				? '<img src="' + escapeHtml(t.image) + '" alt="' + escapeHtml(t.template_name) + '" loading="lazy">'
				: '<span class="ill-template-card-placeholder"><i class="fa fa-lightbulb-o"></i></span>';
			return '<button type="button" class="ill-template-card' + (isSelected ? ' selected' : '')
				+ '" role="option" aria-selected="' + (isSelected ? 'true' : 'false')
				+ '" data-value="' + escapeHtml(t.template_code) + '">'
				+ '<div class="ill-template-card-media">' + media
				+ '<span class="ill-template-card-check"><i class="fa fa-check"></i></span></div>'
				+ '<div class="ill-template-card-body">'
				+ '<div class="ill-template-card-name">' + escapeHtml(t.template_name) + '</div>'
				+ '<div class="ill-template-card-code">' + escapeHtml(t.template_code) + '</div>'
				+ (t.description ? '<div class="ill-template-card-desc">' + escapeHtml(t.description) + '</div>' : '')
				+ '</div></button>';
		}

		function renderGrid() {
			var q = ($search.val() || '').toLowerCase().trim();
			var current = $select.val();
			var shown = templates.filter(function (t) {
				if (!q) return true;
				return (t.template_name + ' ' + t.template_code + ' ' + (t.description || '')).toLowerCase().indexOf(q) !== -1;
			});
			$count.text(labels.count(shown.length, templates.length));
			if (!shown.length) {
				$grid.html('<div class="ill-template-picker-empty">' + escapeHtml(labels.empty) + '</div>');
				return;
			}
			$grid.html(shown.map(function (t) { return cardHtml(t, t.template_code === current); }).join(''));
		}

		function renderSelected() {
			var code = $select.val();
			var t = templates.find(function (x) { return x.template_code === code; });
			if (!t) {
				$selected.hide().empty();
				$grid.show();
				$container.find('.ill-template-picker-toolbar').show();
				return;
			}
			$selected.html(
				(t.image ? '<img src="' + escapeHtml(t.image) + '" alt="">' : '')
				+ '<div><div class="ill-template-selected-name">' + escapeHtml(t.template_name) + '</div>'
				+ '<div class="ill-template-selected-code">' + escapeHtml(t.template_code) + '</div></div>'
				+ '<button type="button" class="ill-template-change">' + escapeHtml(labels.change) + '</button>'
			).show();
			$grid.hide();
			$container.find('.ill-template-picker-toolbar').hide();
		}

		function sync() { renderGrid(); renderSelected(); }

		$grid.on('click' + namespace, '.ill-template-card', function () {
			var code = $(this).attr('data-value');
			if ($select.val() !== code) {
				$select.val(code).trigger($.Event('change', {illUserSelection: true}));
			} else {
				sync();
			}
		});
		$grid.on('keydown' + namespace, '.ill-template-card', function (event) {
			var $cards = $grid.find('.ill-template-card');
			var index = $cards.index(this);
			if (['ArrowRight', 'ArrowDown'].indexOf(event.key) >= 0) index = (index + 1) % $cards.length;
			else if (['ArrowLeft', 'ArrowUp'].indexOf(event.key) >= 0) index = (index + $cards.length - 1) % $cards.length;
			else if (event.key === 'Home') index = 0;
			else if (event.key === 'End') index = $cards.length - 1;
			else return;
			event.preventDefault();
			$cards.eq(index).trigger('focus');
		});
		$selected.on('click' + namespace, '.ill-template-change', function () {
			$selected.hide();
			$grid.show();
			$container.find('.ill-template-picker-toolbar').show();
			$search.trigger('focus');
		});
		$search.on('input' + namespace, renderGrid);
		$select.on('change' + namespace, sync);
		function imageError(event) {
			if (event.target.tagName === 'IMG') $(event.target).replaceWith('<span class="ill-template-card-placeholder" aria-hidden="true"><i class="fa fa-lightbulb-o"></i></span>');
		}
		$container[0].addEventListener('error', imageError, true);

		sync();
		var picker = { owner: $select.data('illConfiguratorOwner'), refresh: sync, templates: templates, destroy: function () {
			$container[0].removeEventListener('error', imageError, true);
			$select.off(namespace);
			$container.off(namespace).find('*').off(namespace);
			$container.removeData('illTemplatePicker');
		} };
		$container.data('illTemplatePicker', picker);
		return picker;
	}

	// ───────────────────────────────────────────────────────────────────
	// Schedule target picker (portal page: #projectSelect / #scheduleSelect /
	// #lineSelect). Shared by the Fixture and LedSheet classes; the desk dialog
	// owns persistence through context.saveHandler and never calls this.
	// ───────────────────────────────────────────────────────────────────
	/**
	 * opts: { instance, context: {project_name, schedule_name, line_idx},
	 *         onChange(): called after any picker change }
	 * Returns { lines, canSave, hasTarget(), scheduleName(), lineValue() }
	 * or null when the pickers are not in the DOM.
	 */
	function bindScheduleContext(opts) {
		var inst = opts.instance;
		var context = opts.context || {};
		var onChange = opts.onChange || function () {};
		var $project = inst.$('#projectSelect');
		var $schedule = inst.$('#scheduleSelect');
		var $line = inst.$('#lineSelect');
		if (!$project.length || !$schedule.length || !$line.length) return null;

		var state = {
			lines: [],
			canSave: !!context.can_save,
			hasTarget: function () { return !!$schedule.val() && !!$line.val(); },
			scheduleName: function () { return $schedule.val() || null; },
			lineValue: function () { return $line.val() || null; },
			lineAt: function (idx) { return state.lines.find(function (l) { return l.idx === idx; }) || null; }
		};

		var pendingSchedule = context.schedule_name || null;
		function resetLines() {
			inst.setScheduleSnapshot(null);
			state.lines = [];
			$line.removeData('illLoadToken');
			$line.prop('disabled', true).find('option:not(:first):not([value="__new__"])').remove();
			inst.$('#linePreview').hide();
		}

		$project.on('change.' + inst.instanceId, function () {
			$schedule.removeData('illLoadToken');
			$schedule.prop('disabled', true).find('option:not(:first)').remove();
			resetLines();
			onChange();
			if (!$(this).val()) return;
			var pre = pendingSchedule;
			pendingSchedule = null;
			loadSchedulesForProject($(this).val(), $schedule, pre);
		});
		$schedule.on('change.' + inst.instanceId, function () {
			var name = $(this).val() || null;
			resetLines();
			onChange();
			if (!name) return;
			inst.request({
				method: 'illumenate_lighting.illumenate_lighting.api.portal.get_schedule_lines_for_configurator',
				isCurrent: function () { return $schedule.val() === name; },
				args: { schedule_name: name },
				callback: function (r) {
					var msg = r.message || {};
					if (!msg.success) return;
					state.lines = msg.lines || [];
					inst.setScheduleSnapshot(msg);
					state.canSave = !!msg.can_save;
					$line.find('option:not(:first)').remove();
					state.lines.forEach(function (l) {
						var tag = l.manufacturer_type === 'OTHER' ? __('Other Mfg')
							: (l.manufacturer_type === 'ACCESSORY' ? __('Accessory')
								: (l.configuration_status === 'Configured' ? __('Configured') : __('Pending')));
						$line.append($('<option></option>').val(l.idx).text(l.line_id + ' [' + tag + ']'));
					});
					$line.append('<option value="__new__">' + __('+ New Line') + '</option>').prop('disabled', false);
					var pre = context.line_idx;
					if (context.line_key && name === context.schedule_name) {
						var saved = state.lines.find(function (row) { return row.line_key === context.line_key; });
						pre = saved ? saved.idx : null;
					} else if (context.draft_id) pre = '__new__';
					context.line_idx = null;
					if (pre !== null && pre !== undefined && pre !== '') $line.val(String(pre)).trigger('change');
					onChange();
				}
			});
		});
		$line.on('change.' + inst.instanceId, function () {
			var val = $(this).val();
			var $preview = inst.$('#linePreview');
			$preview.hide();
			if (val && val !== '__new__') {
				var line = state.lineAt(parseInt(val, 10));
				if (line && (line.configured_fixture || line.configured_tape_neon || line.configured_led_sheet
					|| line.manufacturer_name || line.fixture_model_number)) {
					inst.$('#linePreviewText').text(line.summary || '');
					$preview.show();
				}
			}
			onChange();
		});

		loadUserProjects($project, context.project_name || null);
		return state;
	}

	// ───────────────────────────────────────────────────────────────────
	// Public API
	// ───────────────────────────────────────────────────────────────────
	root.IllConfigurator = {
		Base: Base,
		_registry: registry,
		debounce: debounce,
		escapeHtml: escapeHtml,
		renderPillSelector: renderPillSelector,
		renderTemplateCards: renderTemplateCards,
		bindScheduleContext: bindScheduleContext,
		loadUserProjects: loadUserProjects,
		loadSchedulesForProject: loadSchedulesForProject,
		loadSchedulesForUser: loadSchedulesForUser,
		loadLinesForSchedule: loadLinesForSchedule,

		registerDefaultFixture: function (instance) { defaultFixture = instance; },
		getDefaultFixture: function () { return defaultFixture; },
		registerDefaultTapeNeon: function (instance) { defaultTapeNeon = instance; },
		getDefaultTapeNeon: function () { return defaultTapeNeon; },
	};

	// ───────────────────────────────────────────────────────────────────
	// Back-compat globals.
	// Legacy callers (product_detail.js and inline onclick handlers in the
	// portal templates) expect these globals. They delegate to whichever
	// fixture instance was most recently mounted via initWebflowConfigurator.
	// ───────────────────────────────────────────────────────────────────
	root.WebflowConfigurator = root.WebflowConfigurator || {
		// Property shims read from the default fixture instance.
		get context() { return defaultFixture ? defaultFixture.context : {}; },
		get selections() { return defaultFixture ? defaultFixture.selections : {}; },
		set selections(v) { if (defaultFixture) defaultFixture.selections = v; },
		get productSlug() { return defaultFixture ? defaultFixture.productSlug : null; },
		set productSlug(v) { if (defaultFixture) defaultFixture.productSlug = v; },
		get options() { return defaultFixture ? defaultFixture.options : {}; },
		get seriesInfo() { return defaultFixture ? defaultFixture.seriesInfo : null; },
		get isInitialized() { return defaultFixture ? defaultFixture.isInitialized : false; },
		get lengthConfig() { return defaultFixture ? defaultFixture.lengthConfig : {}; },
		get steps() { return defaultFixture ? defaultFixture.steps : []; },
	};

	function _delegateFixture(method, args) {
		if (!defaultFixture) {
			console.warn('IllConfigurator: no default Fixture instance for', method);
			return;
		}
		return defaultFixture[method].apply(defaultFixture, args || []);
	}

	// Legacy entry point: instantiate Fixture on the document scope.
	root.initWebflowConfigurator = function (context) {
		if (!root.IllConfigurator.Fixture) {
			console.error('IllConfigurator.Fixture not loaded');
			return;
		}
		if (defaultFixture) defaultFixture.destroy();
		var host = document.getElementById('portal-configurator') || document;
		var inst = new root.IllConfigurator.Fixture(host, context || {});
		root.IllConfigurator.registerDefaultFixture(inst);
		inst.init();
		return inst;
	};

	root.resetConfiguration = function () { return _delegateFixture('resetConfiguration'); };
	root.validateConfiguration = function () { return _delegateFixture('validateConfiguration'); };
	root.addToSchedule = function () { return _delegateFixture('addToSchedule'); };

}(window));
