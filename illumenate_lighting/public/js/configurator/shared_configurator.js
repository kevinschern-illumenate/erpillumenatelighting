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
		this.selections = {};
		this.instanceId = 'ill-cfg-' + (++Base._uid);
		registry.push(this);
	}
	Base._uid = 0;

	// Scoped jQuery lookup. If $root is the document we still scope via .find()
	// so descendant-only searches behave the same in both modes.
	Base.prototype.$ = function (selector) {
		if (!selector) return this.$root;
		// Allow `#id` and `[name=...]` selectors to remain scoped.
		if (this.$root[0] === document) {
			return $(selector);
		}
		return this.$root.find(selector);
	};

	// Convenience: find a control by `name` attribute within scope.
	Base.prototype.$name = function (name) {
		return this.$('[name="' + name + '"]');
	};

	Base.prototype.destroy = function () {
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
		return function () {
			var ctx = this, args = arguments;
			clearTimeout(timeout);
			timeout = setTimeout(function () { func.apply(ctx, args); }, wait);
		};
	}

	/**
	 * Load user projects into a <select>. Returns the frappe.call promise.
	 * Used by both fixture and tape/neon configurators.
	 */
	function loadUserProjects($select, preSelect) {
		if (!$select || !$select.length) return;
		return frappe.call({
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
		return frappe.call({
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
		return frappe.call({
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
		return frappe.call({
			method: 'illumenate_lighting.illumenate_lighting.api.portal.get_schedule_lines_for_configurator',
			args: { schedule_name: scheduleName },
			callback: function (r) {
				var msg = r.message || {};
				var lines = Array.isArray(msg) ? msg : (msg.lines || []);
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
			+ '<span class="ill-template-picker-count"></span>'
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

		$grid.on('click', '.ill-template-card', function () {
			var code = $(this).attr('data-value');
			if ($select.val() !== code) {
				$select.val(code).trigger('change');
			} else {
				sync();
			}
		});
		$selected.on('click', '.ill-template-change', function () {
			$selected.hide();
			$grid.show();
			$container.find('.ill-template-picker-toolbar').show();
			$search.trigger('focus');
		});
		$search.on('input', renderGrid);
		$select.on('change.illTemplateCards', sync);

		sync();
		return { refresh: sync, templates: templates };
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

		function resetLines() {
			state.lines = [];
			$line.prop('disabled', true).find('option:not(:first):not([value="__new__"])').remove();
			inst.$('#linePreview').hide();
		}

		$project.on('change', function () {
			$schedule.prop('disabled', true).find('option:not(:first)').remove();
			resetLines();
			onChange();
			if (!$(this).val()) return;
			var pre = context.schedule_name || null;
			context.schedule_name = null;
			loadSchedulesForProject($(this).val(), $schedule, pre);
		});
		$schedule.on('change', function () {
			var name = $(this).val() || null;
			resetLines();
			onChange();
			if (!name) return;
			frappe.call({
				method: 'illumenate_lighting.illumenate_lighting.api.portal.get_schedule_lines_for_configurator',
				args: { schedule_name: name },
				callback: function (r) {
					var msg = r.message || {};
					if (!msg.success) return;
					state.lines = msg.lines || [];
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
					context.line_idx = null;
					if (pre !== null && pre !== undefined && pre !== '') $line.val(String(pre)).trigger('change');
					onChange();
				}
			});
		});
		$line.on('change', function () {
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
		var inst = new root.IllConfigurator.Fixture(document, context || {});
		root.IllConfigurator.registerDefaultFixture(inst);
		inst.init();
		return inst;
	};

	root.resetConfiguration = function () { return _delegateFixture('resetConfiguration'); };
	root.validateConfiguration = function () { return _delegateFixture('validateConfiguration'); };
	root.addToSchedule = function () { return _delegateFixture('addToSchedule'); };

}(window));
