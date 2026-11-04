// Schedule detail page (plan 3.2): "Configure similar" and "Copy to another schedule".
// Configure similar opens the configurator pre-filled from a line (?similar_to=) with the line's
// details as the add-line draft; nothing is saved until the dealer adds the new line.
// Copy sends line keys to portal.line_copy.copy_lines, which recomputes engineering and prices.
var ScheduleCopy = (function () {
	var METHOD = 'illumenate_lighting.illumenate_lighting.portal.line_copy.';
	var pending = [];
	var targets = {};

	function format(text, value) {
		return text.replace('{0}', value);
	}

	function lineKey(index) {
		var row = document.querySelector('tr[data-line-idx="' + index + '"]');
		var line = (scheduleContext.lines || [])[index] || {};
		return (row && row.getAttribute('data-line-key')) || line.line_key || null;
	}

	function configureSimilar(index) {
		var line = (scheduleContext.lines || [])[index];
		var key = lineKey(index);
		if (!line || !key) return;
		var metadata = {
			line_id: line.line_id ? String(line.line_id) + ' ' + scheduleText("(similar)") : '',
			location: line.location || '',
			qty: line.qty || 1,
			notes: '',
		};
		var id = window.crypto && window.crypto.randomUUID ? window.crypto.randomUUID() : null;
		try {
			if (!id) throw new Error('no uuid');
			window.sessionStorage.setItem('ill-line-draft:' + id, JSON.stringify({ schedule: schedule_name, metadata: metadata, savedAt: Date.now() }));
		} catch (_) {
			frappe.msgprint(scheduleText("Browser storage is unavailable. Allow session storage to preserve this draft."));
			return;
		}
		var params = new URLSearchParams({ schedule: schedule_name, similar_to: key, draft: id });
		ScheduleCopy.navigate('/portal/configure?' + params.toString());
	}

	function setOptions($select, schedules) {
		$select.empty();
		if (!schedules.length) {
			$select.append($('<option></option>').val('').text(scheduleText("No other Draft or Ready schedules you can edit.")));
			return;
		}
		$select.append($('<option></option>').val('').text(scheduleText("Choose a target schedule…")));
		schedules.forEach(function (row) {
			var label = row.label + (row.project ? ' (' + row.project + ')' : '');
			$select.append($('<option></option>').val(row.value).text(label));
		});
	}

	function open(keys) {
		pending = (keys || []).filter(Boolean);
		if (!pending.length) return;
		var $modal = $('#copyLinesModal');
		var $select = $('#copyLinesTarget');
		$('#copyLinesSummary').text(format(scheduleText("Copy {0} line(s) from this schedule."), pending.length));
		$select.prop('disabled', true).empty().append($('<option></option>').val('').text(scheduleText("Loading...")));
		$('#copyLinesConfirm').prop('disabled', true);
		$modal.modal('show');
		frappe.call({
			method: METHOD + 'copy_targets',
			args: { source_schedule: schedule_name },
			callback: function (r) {
				var schedules = (r.message && r.message.schedules) || [];
				targets = {};
				schedules.forEach(function (row) { targets[row.value] = row; });
				setOptions($select, schedules);
				$select.prop('disabled', !schedules.length);
			},
			error: function () {
				$select.empty().append($('<option></option>').val('').text(scheduleText("Could not load your schedules.")));
			},
		});
	}

	function copy() {
		var target = $('#copyLinesTarget').val();
		if (!target || !pending.length) return;
		var $button = $('#copyLinesConfirm').prop('disabled', true);
		frappe.call({
			method: METHOD + 'copy_lines',
			type: 'POST',
			args: {
				source_schedule: schedule_name,
				line_keys: JSON.stringify(pending),
				target_schedule: target,
				expected_modified: (targets[target] || {}).modified || null,
			},
			callback: function (r) {
				var message = r.message || {};
				if (!message.success) {
					frappe.msgprint(scheduleText("Could not copy the lines."));
					return;
				}
				$('#copyLinesModal').modal('hide');
				var href = '/portal/schedules/' + encodeURIComponent(message.schedule);
				var $alert = $('<span></span>').text(format(scheduleText("Copied {0} line(s)."), message.copied) + ' ');
				$alert.append($('<a></a>').attr('href', href).text(scheduleText("Open target schedule")));
				frappe.msgprint($alert.prop('outerHTML'));
			},
			always: function () { $button.prop('disabled', !$('#copyLinesTarget').val()); },
		});
	}

	$(document).on('change', '#copyLinesTarget', function () {
		$('#copyLinesConfirm').prop('disabled', !this.value);
	});
	$(document).on('click', '#copyLinesConfirm', copy);
	document.addEventListener('click', function (event) {
		var button = event.target.closest('[data-copy-action]');
		if (!button) return;
		var index = parseInt(button.dataset.lineIndex, 10);
		if (button.dataset.copyAction === 'similar') configureSimilar(index);
		else if (button.dataset.copyAction === 'copy') open([lineKey(index)]);
	});

	return {
		open: open,
		configureSimilar: configureSimilar,
		navigate: function (href) { window.location.href = href; },
	};
})();
