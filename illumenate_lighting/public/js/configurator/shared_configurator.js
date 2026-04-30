/**
 * Shared Configurator (Phase 4)
 *
 * Provides:
 *   - window.IllConfigurator namespace + registry
 *   - IllConfigurator.Base class with rootEl-scoped DOM helpers
 *   - Shared schedule-context loaders (project / schedule / line dropdowns)
 *   - Backwards-compatibility globals for legacy callers (product_detail.js,
 *     inline onclick handlers in configure_webflow.html etc.).
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
		return frappe.call({
			method: 'illumenate_lighting.illumenate_lighting.api.portal.get_user_projects',
			callback: function (r) {
				if (!r.message) return;
				$select.find('option:not(:first)').remove();
				(r.message || []).forEach(function (p) {
					$select.append(
						$('<option></option>').val(p.name).text(p.project_name || p.name)
					);
				});
				if (preSelect) {
					$select.val(preSelect).trigger('change');
				}
			}
		});
	}

	function loadSchedulesForProject(projectName, $scheduleSelect, preSelect) {
		return frappe.call({
			method: 'illumenate_lighting.illumenate_lighting.api.portal.get_schedules_for_project',
			args: { project_name: projectName },
			callback: function (r) {
				$scheduleSelect.find('option:not(:first)').remove();
				(r.message || []).forEach(function (s) {
					$scheduleSelect.append(
						$('<option></option>').val(s.name).text(s.schedule_name || s.name)
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
				$lineSelect.find('option:not(:first):not([value="__new__"])').remove();
				(r.message || []).forEach(function (l) {
					var label = (l.line_id || ('Row ' + l.idx)) + (l.configured_fixture ? ' \u2713' : '');
					$lineSelect.append($('<option></option>').val(l.idx).text(label));
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
	// Public API
	// ───────────────────────────────────────────────────────────────────
	root.IllConfigurator = {
		Base: Base,
		_registry: registry,
		debounce: debounce,
		renderPillSelector: renderPillSelector,
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
