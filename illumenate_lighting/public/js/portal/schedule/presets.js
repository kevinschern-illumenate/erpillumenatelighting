// Schedule detail page (plan 3.6): "Start from a saved preset" in the Add Line dialog. The dealer's
// presets and their company's shared presets are listed when the dialog opens. Choosing one opens
// the configurator pre-filled (?preset=) with this dialog's line details as the add-line draft;
// the server re-checks the preset against what is offered now. Nothing is saved until the dealer
// adds the line. Only the dealer's own presets can be deleted here.
var SchedulePresets = (function () {
	var METHOD = 'illumenate_lighting.illumenate_lighting.portal.presets.';
	var presets = [];

	function show(text, failed) {
		$('#addLinePresetResult').text(text).toggleClass('text-danger', !!failed).toggleClass('text-muted', !failed);
	}

	function selected() {
		var name = $('#addLinePreset').val();
		return presets.filter(function (preset) { return preset.name === name; })[0] || null;
	}

	function update() {
		var preset = selected();
		$('#addLinePresetDelete').prop('disabled', !(preset && preset.mine));
	}

	function optionText(preset) {
		var notes = [];
		if (!preset.mine) notes.push(scheduleText("from your company"));
		else if (preset.shared) notes.push(scheduleText("shared"));
		if (preset.available === false) notes.push(scheduleText("no longer offered"));
		return preset.label + ' — ' + preset.family + (notes.length ? ' (' + notes.join(', ') + ')' : '');
	}

	function render() {
		var $select = $('#addLinePreset');
		$select.find('option').not(':first').remove();
		presets.forEach(function (preset) {
			$('<option>').val(preset.name).text(optionText(preset)).appendTo($select);
		});
		if (!presets.length) show(scheduleText("No saved presets yet. Save one from the configurator."), false);
		update();
	}

	function load() {
		frappe.call({
			method: METHOD + 'list_presets',
			type: 'GET',
			args: { schedule_name: schedule_name },
			callback: function (r) {
				var message = r.message || {};
				if (message.disabled) {
					$('.ill-add-from-preset').addClass('d-none');
					presets = [];
					return;
				}
				presets = message.success ? (message.presets || []) : [];
				render();
			},
			error: function () { show(scheduleText("Could not load your presets."), true); },
		});
	}

	function metadata() {
		var form = $('#addLineForm');
		var values = {};
		['line_id', 'location', 'qty', 'notes'].forEach(function (field) { values[field] = form.find('[name="' + field + '"]').val() || ''; });
		return values;
	}

	function open() {
		var preset = selected();
		if (!preset) {
			show(scheduleText("Choose a preset."), true);
			return;
		}
		var values = metadata();
		var qty = Number(values.qty || 1);
		if (!Number.isInteger(qty) || qty < 1) {
			show(scheduleText("Enter a positive whole quantity."), true);
			return;
		}
		values.qty = qty;
		var id = window.crypto && window.crypto.randomUUID ? window.crypto.randomUUID() : null;
		try {
			if (!id) throw new Error('no uuid');
			window.sessionStorage.setItem('ill-line-draft:' + id, JSON.stringify({ schedule: schedule_name, metadata: values, savedAt: Date.now() }));
			window.sessionStorage.setItem('ill-line-draft-last:' + schedule_name, id);
		} catch (_) {
			show(scheduleText("Browser storage is unavailable. Allow session storage to preserve this draft."), true);
			return;
		}
		show(scheduleText("Opening the configurator…"), false);
		var params = new URLSearchParams({ category: preset.family, schedule: schedule_name, preset: preset.name, draft: id });
		SchedulePresets.navigate('/portal/configure?' + params.toString());
	}

	function remove() {
		var preset = selected();
		if (!preset || !preset.mine) return;
		if (!SchedulePresets.confirm(scheduleText("Delete preset {0}?").replace('{0}', preset.label))) return;
		var $button = $('#addLinePresetDelete').prop('disabled', true);
		frappe.call({
			method: METHOD + 'delete_preset',
			type: 'POST',
			args: { preset: preset.name, schedule_name: schedule_name },
			callback: function (r) {
				if (r.message && r.message.success) {
					presets = presets.filter(function (row) { return row.name !== preset.name; });
					render();
					show(scheduleText("Preset deleted."), false);
				}
			},
			error: function () { show(scheduleText("Could not delete this preset."), true); },
			always: function () { $button.prop('disabled', false); update(); },
		});
	}

	if (scheduleContext.presets) {
		$(document).on('show.bs.modal', '#addLineModal', load);
		$(document).on('change', '#addLinePreset', update);
		$(document).on('click', '#addLinePresetGo', open);
		$(document).on('click', '#addLinePresetDelete', remove);
	}

	return {
		load: load,
		open: open,
		remove: remove,
		navigate: function (href) { window.location.href = href; },
		confirm: function (message) { return window.confirm(message); },
	};
})();

// Schedule detail page (CAD plan WP 1.2): "Drawing styles" in the Import drawing dialog. Lists the
// dealer's presets (and their company's shared ones, read-only) as the CAD catalog's run styles, each
// with its short drawing code (drawn on ILM-STYLE-<code> layers) and an "in CAD" switch. Editing a
// code or the switch saves it with set_preset_cad; the server checks the code and its uniqueness.
// The panel is built here (schedule.html is not changed) and only when both drawing import and
// presets are on for the page. Every value is set as text, never parsed as HTML. Strings the Add Line
// picker already registers in the page's i18n block use scheduleText(); the panel's own use __().
var ScheduleDrawingStyles = (function () {
	var METHOD = 'illumenate_lighting.illumenate_lighting.portal.presets.';
	var CODE = /^[A-Z0-9][A-Z0-9-]{0,23}$/;
	var presets = [];
	var $panel = null;

	function show(text, failed) {
		if (!$panel) return;
		$panel.find('#drawingStylesResult').text(text).toggleClass('text-danger', !!failed).toggleClass('text-muted', !failed);
	}

	function build() {
		var $body = $('#importDrawingModal .modal-body').first();
		if (!$body.length) return null;
		var $details = $('<details class="ill-drawing-styles mt-3" id="drawingStyles">');
		$('<summary class="font-weight-bold">').text(__("Drawing styles")).appendTo($details);
		$('<p class="text-muted small mb-2">').text(__("Your saved presets are the CAD catalog's run styles. Give one a short code to draw it on an ILM-STYLE-<code> layer; switch a style off to leave it out of the CAD catalog.")).appendTo($details);
		var $table = $('<table class="table table-sm mb-1">');
		var $head = $('<tr>');
		["Preset", "Family", "Template", "Code", "In CAD", "Status"].forEach(function (label) {
			$('<th scope="col">').text(__(label)).appendTo($head);
		});
		$('<thead>').append($head).appendTo($table);
		$('<tbody id="drawingStylesRows">').appendTo($table);
		$('<div class="table-responsive">').append($table).appendTo($details);
		$('<small id="drawingStylesResult" role="status" class="text-muted">').appendTo($details);
		$body.append($details);
		return $details;
	}

	function find(name) {
		return presets.filter(function (preset) { return preset.name === name; })[0] || null;
	}

	function row(preset) {
		var $tr = $('<tr>').attr('data-preset', preset.name);
		var $label = $('<td>').text(preset.label);
		if (!preset.mine) $('<small class="d-block text-muted">').text(scheduleText("from your company")).appendTo($label);
		$tr.append($label, $('<td>').text(preset.family || ''), $('<td>').text(preset.template || ''));
		var $code = $('<input type="text" class="form-control form-control-sm ill-style-code" maxlength="24" autocomplete="off" spellcheck="false">')
			.val(preset.cad_code || '')
			.attr('aria-label', __("Drawing code for {0}").replace('{0}', preset.label))
			.prop('disabled', !preset.mine);
		$('<td>').append($code).appendTo($tr);
		var $enabled = $('<input type="checkbox" class="ill-style-enabled">')
			.prop('checked', preset.cad_enabled !== false)
			.attr('aria-label', __("Offer {0} in the CAD catalog").replace('{0}', preset.label))
			.prop('disabled', !preset.mine);
		$('<td>').append($enabled).appendTo($tr);
		var available = preset.available !== false;
		$('<td>').append(
			$('<span class="badge">').addClass(available ? 'badge-success' : 'badge-secondary')
				.text(available ? __("Available") : __("No longer offered"))
		).appendTo($tr);
		return $tr;
	}

	function render() {
		var $rows = $panel.find('#drawingStylesRows').empty();
		presets.forEach(function (preset) { $rows.append(row(preset)); });
		if (!presets.length) show(scheduleText("No saved presets yet. Save one from the configurator."), false);
	}

	function load() {
		if (!$panel) return;
		frappe.call({
			method: METHOD + 'list_presets',
			type: 'GET',
			args: { schedule_name: schedule_name },
			callback: function (r) {
				var message = r.message || {};
				if (message.disabled) {
					$panel.remove();
					$panel = null;
					presets = [];
					return;
				}
				presets = message.success ? (message.presets || []) : [];
				render();
			},
			error: function () { show(scheduleText("Could not load your presets."), true); },
		});
	}

	// A failed save re-renders the row from the last saved values, which reverts the edit.
	function save(name, args) {
		var preset = find(name);
		if (!preset || !preset.mine) return;
		var $inputs = $panel.find('tr[data-preset]').filter(function () { return $(this).attr('data-preset') === name; }).find('input');
		$inputs.prop('disabled', true);
		frappe.call({
			method: METHOD + 'set_preset_cad',
			type: 'POST',
			args: $.extend({ preset: name, schedule_name: schedule_name }, args),
			callback: function (r) {
				var message = r.message || {};
				if (!message.success || !message.preset) {
					show(__("Could not save the drawing style."), true);
					return;
				}
				preset.cad_code = message.preset.cad_code || '';
				preset.cad_enabled = message.preset.cad_enabled !== false;
				show(__("Drawing style saved."), false);
			},
			error: function () { show(__("Could not save the drawing style."), true); },
			always: function () { if ($panel) render(); },
		});
	}

	function changeCode() {
		var name = $(this).closest('tr').attr('data-preset');
		var preset = find(name);
		if (!preset) return;
		var code = String($(this).val() || '').trim().toUpperCase();
		$(this).val(code);
		if (code === (preset.cad_code || '')) return;
		if (code && !CODE.test(code)) {
			show(__("Drawing codes use letters, digits and dashes (up to 24 characters) and start with a letter or digit."), true);
			$(this).val(preset.cad_code || '');
			return;
		}
		save(name, { cad_code: code });
	}

	function changeEnabled() {
		var name = $(this).closest('tr').attr('data-preset');
		save(name, { cad_enabled: $(this).prop('checked') ? 1 : 0 });
	}

	if (scheduleContext.drawing_import && scheduleContext.presets) {
		$panel = build();
		if ($panel) {
			$(document).on('show.bs.modal', '#importDrawingModal', load);
			$panel.on('change', '.ill-style-code', changeCode);
			$panel.on('change', '.ill-style-enabled', changeEnabled);
		}
	}

	return { load: load };
})();
