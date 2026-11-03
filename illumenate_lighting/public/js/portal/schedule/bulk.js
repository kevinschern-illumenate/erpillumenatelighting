// Schedule detail page (plan 3.3): select lines, then edit, delete, move, copy or request
// drawings for all of them at once. Each change is one POST to portal.bulk_lines.bulk_update_lines,
// which runs every line through the row editor's validator and saves all or nothing.
var ScheduleBulk = (function () {
	var METHOD = 'illumenate_lighting.illumenate_lighting.portal.bulk_lines.bulk_update_lines';
	var TARGETS = 'illumenate_lighting.illumenate_lighting.portal.line_copy.copy_targets';
	var INPUTS = { qty: 'bulkEditQty', location: 'bulkEditLocation', line_id: 'bulkEditLineId', notes: 'bulkEditNotes' };
	var mode = null;
	var targets = {};

	function format(text) {
		var values = Array.prototype.slice.call(arguments, 1);
		return text.replace(/\{(\d)\}/g, function (match, index) {
			return values[index] === undefined ? match : String(values[index]);
		});
	}

	function title(action) {
		switch (action) {
			case 'qty': return scheduleText("Set quantity");
			case 'location': return scheduleText("Set location");
			case 'line_id': return scheduleText("Set type");
			case 'notes': return scheduleText("Set notes");
			case 'move': return scheduleText("Move to another schedule");
			default: return '';
		}
	}

	function boxes() {
		return Array.prototype.slice.call(document.querySelectorAll('.line-select'));
	}

	function chosen() {
		return boxes().filter(function (box) { return box.checked && box.getAttribute('data-line-key'); });
	}

	function keys() {
		return chosen().map(function (box) { return box.getAttribute('data-line-key'); });
	}

	function labels() {
		return chosen().map(function (box) {
			var row = box.closest('tr');
			var cell = row && row.querySelector('.col-line-id');
			return ((cell && cell.textContent) || '').trim() || box.getAttribute('data-line-key');
		});
	}

	function modified() {
		return typeof scheduleModified !== 'undefined' ? scheduleModified : scheduleContext.schedule_modified;
	}

	function refresh() {
		var all = boxes();
		var count = keys().length;
		var bar = document.getElementById('bulkActionBar');
		if (bar) bar.hidden = !count;
		var counter = document.getElementById('bulkSelectionCount');
		if (counter) counter.textContent = format(scheduleText("{0} selected"), count);
		var selectAll = document.getElementById('lineSelectAll');
		if (selectAll) {
			selectAll.checked = count > 0 && count === all.length;
			selectAll.indeterminate = count > 0 && count < all.length;
		}
		all.forEach(function (box) {
			var row = box.closest('tr');
			if (row) row.classList.toggle('table-active', box.checked);
		});
	}

	function clear() {
		boxes().forEach(function (box) { box.checked = false; });
		refresh();
	}

	function showErrors(message) {
		var $list = $('<ul class="mb-0"></ul>');
		(message.errors || []).forEach(function (error) {
			$list.append($('<li></li>').text((error.line ? error.line + ': ' : '') + (error.error || '')));
		});
		var $content = $('<div></div>').append(
			$('<p class="mb-1"></p>').text(message.error || scheduleText("Nothing was changed.")),
			$list
		);
		var box = document.getElementById('bulkEditErrors');
		if (mode && box) {
			$(box).empty().append($content.contents()).prop('hidden', false);
		} else {
			frappe.msgprint($content.prop('outerHTML'));
		}
	}

	function submit(changes, $button) {
		var selected = keys();
		if (!selected.length) return;
		if ($button) $button.prop('disabled', true);
		frappe.call({
			method: METHOD,
			type: 'POST',
			args: {
				schedule: schedule_name,
				line_keys: JSON.stringify(selected),
				changes: JSON.stringify(changes),
				expected_modified: modified(),
			},
			callback: function (r) {
				var message = r.message || {};
				if (message.success) {
					if (window.ScheduleUndo) ScheduleUndo.offer(message.undo);
					ScheduleBulk.reload();
					return;
				}
				showErrors(message);
			},
			always: function () { if ($button) $button.prop('disabled', false); },
		});
	}

	function setTargets(schedules) {
		var $select = $('#bulkEditTarget').empty();
		targets = {};
		if (!schedules.length) {
			$select.append($('<option></option>').val('').text(scheduleText("No other Draft or Ready schedules you can edit.")));
			$select.prop('disabled', true);
			return;
		}
		$select.append($('<option></option>').val('').text(scheduleText("Choose a target schedule…")));
		schedules.forEach(function (row) {
			targets[row.value] = row;
			$select.append($('<option></option>').val(row.value).text(row.label + (row.project ? ' (' + row.project + ')' : '')));
		});
		$select.prop('disabled', false);
	}

	function openEdit(action) {
		var count = keys().length;
		if (!count) return;
		mode = action;
		$('#bulkEditTitle').text(title(action));
		$('#bulkEditSummary').text(format(scheduleText("Applies to {0} selected line(s). Nothing changes unless every line can be updated."), count));
		$('#bulkEditErrors').empty().prop('hidden', true);
		$('#bulkEditModal [data-bulk-field]').each(function () {
			this.hidden = this.getAttribute('data-bulk-field') !== action;
		});
		if (INPUTS[action]) $('#' + INPUTS[action]).val('');
		if (action === 'move') {
			$('#bulkEditTarget').prop('disabled', true).empty().append($('<option></option>').val('').text(scheduleText("Loading...")));
			frappe.call({
				method: TARGETS,
				args: { source_schedule: schedule_name },
				callback: function (r) { setTargets((r.message && r.message.schedules) || []); },
				error: function () {
					$('#bulkEditTarget').empty().append($('<option></option>').val('').text(scheduleText("Could not load your schedules.")));
				},
			});
		}
		$('#bulkEditModal').modal('show');
	}

	function confirmEdit() {
		var changes = {};
		if (mode === 'move') {
			var target = $('#bulkEditTarget').val();
			if (!target) {
				showErrors({ error: scheduleText("Choose a target schedule…") });
				return;
			}
			changes = { action: 'move', target_schedule: target, target_modified: (targets[target] || {}).modified || null };
		} else if (INPUTS[mode]) {
			var value = $('#' + INPUTS[mode]).val();
			if (mode === 'qty' && !(parseInt(value, 10) >= 1 && String(parseInt(value, 10)) === String(value).trim())) {
				showErrors({ error: scheduleText("Quantity must be a whole number of at least 1") });
				return;
			}
			changes[mode] = value;
		} else {
			return;
		}
		submit(changes, $('#bulkEditConfirm'));
	}

	function remove() {
		var count = keys().length;
		if (!count) return;
		mode = null;
		var question = scheduleContext.undo
			? scheduleText("Delete {0} selected line(s)? You can undo this for a few seconds.")
			: scheduleText("Delete {0} selected line(s)? This cannot be undone.");
		frappe.confirm(format(question, count), function () {
			submit({ action: 'delete' });
		});
	}

	function requestDrawings() {
		var names = labels();
		if (!names.length) return;
		var reference = format(scheduleText("Schedule {0}: {1}"), schedule_name, names.join(', ')).slice(0, 500);
		var params = new URLSearchParams({ fixture_reference: reference });
		if (scheduleContext.project_name) params.set('project', scheduleContext.project_name);
		ScheduleBulk.navigate('/portal/drawings?' + params.toString());
	}

	function act(action) {
		if (action === 'clear') clear();
		else if (action === 'delete') remove();
		else if (action === 'drawings') requestDrawings();
		else if (action === 'copy') { if (window.ScheduleCopy) window.ScheduleCopy.open(keys()); }
		else openEdit(action);
	}

	if (scheduleContext.bulk_edit) {
		document.addEventListener('change', function (event) {
			if (event.target.id === 'lineSelectAll') {
				var checked = event.target.checked;
				boxes().forEach(function (box) { box.checked = checked; });
				refresh();
			} else if (event.target.classList && event.target.classList.contains('line-select')) {
				refresh();
			}
		});
		document.addEventListener('click', function (event) {
			var button = event.target.closest('[data-bulk-action]');
			if (button) act(button.getAttribute('data-bulk-action'));
		});
		$(document).on('click', '#bulkEditConfirm', confirmEdit);
		refresh();
	}

	return {
		keys: keys,
		refresh: refresh,
		reload: function () { window.location.reload(); },
		navigate: function (href) { window.location.href = href; },
	};
})();
