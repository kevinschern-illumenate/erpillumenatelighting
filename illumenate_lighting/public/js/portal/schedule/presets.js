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
