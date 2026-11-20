// Schedule detail page (draw-to-quote plan 2.7): import an AutoCAD drawing package (ilq/2).
// The server plans every run through the configurators (dry run); runs that leave an option open
// get a choice here, lines whose runs left the drawing are removed only when the dealer ticks the
// box, and a locked or quoted schedule imports into a new version. The server plans again on import
// and saves everything in one transaction. Every value from the package is shown as text only.
var DrawingImport = (function () {
	var BASE = 'illumenate_lighting.illumenate_lighting.portal.drawing_import.';
	var MAX_BYTES = 5 * 1024 * 1024;
	var STATUS = {
		ok: { label: function () { return scheduleText("Ready"); }, badge: 'badge-success' },
		needs_choice: { label: function () { return scheduleText("Needs a choice"); }, badge: 'badge-warning' },
		error: { label: function () { return scheduleText("Error"); }, badge: 'badge-danger' },
	};
	var ACTIONS = {
		add: function () { return scheduleText("Add"); },
		update: function () { return scheduleText("Update"); },
		unchanged: function () { return scheduleText("Unchanged"); },
		remove: function () { return scheduleText("Remove"); },
	};
	var state = { filename: null, content: null, preview: null };

	function format(text) {
		var values = Array.prototype.slice.call(arguments, 1);
		return text.replace(/\{(\d)\}/g, function (match, index) {
			return values[Number(index)] === undefined ? match : String(values[Number(index)]);
		});
	}

	function modified() {
		return typeof scheduleModified !== 'undefined' ? scheduleModified : scheduleContext.schedule_modified;
	}

	function fail(text) {
		$('#importDrawingError').text(text || '').prop('hidden', !text);
	}

	function reset() {
		state = { filename: null, content: null, preview: null };
		$('#importDrawingPreview, #importDrawingRemoveWrap, #importDrawingVersionWrap, #importDrawingWarnings, #importDrawingRefresh').prop('hidden', true);
		$('#importDrawingRows, #importDrawingWarnings').empty();
		$('#importDrawingCounts').text('');
		$('#importDrawingRemove, #importDrawingVersion').prop('checked', false);
		fail('');
		updateConfirm();
	}

	// Values typed for the options a run's style leaves open: {run id: {selection key: value}}.
	function choices() {
		var chosen = {};
		$('#importDrawingRows input[data-choice-run]').each(function () {
			var value = String(this.value || '').trim();
			if (!value) return;
			var run = this.getAttribute('data-choice-run');
			chosen[run] = chosen[run] || {};
			chosen[run][this.getAttribute('data-choice-key')] = value;
		});
		return chosen;
	}

	function cell(row, text) {
		var td = document.createElement('td');
		td.textContent = text === undefined || text === null ? '' : String(text);
		row.appendChild(td);
		return td;
	}

	function badge(td, status) {
		var span = document.createElement('span');
		span.className = 'badge ' + status.badge;
		span.textContent = status.label();
		td.appendChild(span);
	}

	function choiceInputs(td, entry, previous) {
		(entry.parts || []).forEach(function (part) {
			(part.missing || []).forEach(function (key) {
				var id = 'importDrawingChoice-' + entry.id + '-' + key;
				var label = document.createElement('label');
				label.className = 'sr-only';
				label.htmlFor = id;
				label.textContent = format(scheduleText("Choose {0}"), key);
				var input = document.createElement('input');
				input.type = 'text';
				input.className = 'form-control form-control-sm mt-1';
				input.id = id;
				input.placeholder = format(scheduleText("Choose {0}"), key);
				input.setAttribute('data-choice-run', entry.id);
				input.setAttribute('data-choice-key', key);
				input.value = ((previous[entry.id] || {})[key]) || '';
				td.appendChild(label);
				td.appendChild(input);
			});
		});
	}

	function renderRows(message) {
		var previous = choices();
		var body = document.getElementById('importDrawingRows');
		body.textContent = '';
		var rows = (message.rows || []).concat(message.other_lines || [], message.removals || []);
		rows.forEach(function (entry) {
			var tr = document.createElement('tr');
			tr.setAttribute('data-drawing-status', entry.status);
			tr.setAttribute('data-drawing-action', entry.action || '');
			cell(tr, entry.id);
			cell(tr, entry.fixture_type);
			cell(tr, entry.style || entry.summary || entry.family || '');
			cell(tr, entry.drawn_length_in);
			cell(tr, entry.server_length_in);
			cell(tr, entry.action && ACTIONS[entry.action] ? ACTIONS[entry.action]() : '');
			badge(cell(tr, ''), STATUS[entry.status] || STATUS.error);
			var details = cell(tr, (entry.messages || []).filter(Boolean).join(' · '));
			if (entry.status === 'needs_choice') choiceInputs(details, entry, previous);
			body.appendChild(tr);
		});
		var counts = message.counts || {};
		$('#importDrawingCounts').text(format(
			scheduleText("{0} runs ready, {1} need a choice, {2} with errors; {3} to add, {4} to update, {5} unchanged."),
			counts.ok || 0, counts.needs_choice || 0, counts.error || 0, counts.add || 0, counts.update || 0, counts.unchanged || 0
		));
		var removals = (message.removals || []).length;
		$('#importDrawingRemoveLabel').text(format(scheduleText("Remove {0} line(s) whose runs are no longer in the drawing"), removals));
		$('#importDrawingRemoveWrap').prop('hidden', !removals);
		$('#importDrawingVersionWrap').prop('hidden', !message.new_version_required);
		var warnings = (message.warnings || []).concat(message.blocking || []);
		var $warnings = $('#importDrawingWarnings').empty().prop('hidden', !warnings.length);
		warnings.forEach(function (text) { $warnings.append($('<div>').text(text)); });
		$('#importDrawingRefresh').prop('hidden', !counts.needs_choice);
		$('#importDrawingPreview').prop('hidden', false);
		updateConfirm();
	}

	function importable() {
		var message = state.preview;
		if (!message || !state.content) return false;
		var counts = message.counts || {};
		if (counts.error || counts.needs_choice || (message.blocking || []).length) return false;
		if ((message.removals || []).length && !$('#importDrawingRemove').prop('checked')) return false;
		if (message.new_version_required && !$('#importDrawingVersion').prop('checked')) return false;
		return true;
	}

	function updateConfirm() {
		$('#importDrawingConfirm').prop('disabled', !importable()).text(scheduleText("Import the drawing"));
	}

	function preview() {
		fail('');
		$('#importDrawingCounts').text(scheduleText("Reading the drawing…"));
		frappe.call({
			method: BASE + 'preview_drawing_import',
			type: 'POST',
			args: { schedule: schedule_name, filename: state.filename, content: state.content, choices: JSON.stringify(choices()) },
			callback: function (r) {
				var message = r.message || {};
				if (!message.success) {
					$('#importDrawingCounts').text('');
					fail(message.error || scheduleText("Could not read this drawing package."));
					return;
				}
				state.preview = message;
				renderRows(message);
			},
			error: function () {
				$('#importDrawingCounts').text('');
				fail(scheduleText("Could not read this drawing package."));
			},
		});
	}

	function choose(file) {
		reset();
		if (!file) return;
		if (!/\.(json|ilq)$/i.test(file.name || '')) {
			fail(scheduleText("Upload the .ilq.json file from ILQUOTE."));
			return;
		}
		if (file.size > MAX_BYTES) {
			fail(scheduleText("The file is larger than 5 MB."));
			return;
		}
		var reader = new FileReader();
		reader.onload = function () {
			var result = String(reader.result || '');
			state.filename = file.name;
			state.content = result.slice(result.indexOf(',') + 1);
			preview();
		};
		reader.onerror = function () { fail(scheduleText("Could not read this drawing package.")); };
		reader.readAsDataURL(file);
	}

	function saveReceipt(receipt) {
		var name = 'illumenate_receipt_' + String(receipt.import || 'drawing') + '.json';
		DrawingImport.save(new Blob([JSON.stringify(receipt, null, 1)], { type: 'application/json' }), name);
	}

	function commit() {
		if (!importable()) return;
		$('#importDrawingConfirm').prop('disabled', true);
		frappe.call({
			method: BASE + 'commit_drawing_import',
			type: 'POST',
			args: {
				schedule: schedule_name,
				filename: state.filename,
				content: state.content,
				expected_modified: modified(),
				choices: JSON.stringify(choices()),
				confirm_removals: $('#importDrawingRemove').prop('checked') ? 1 : 0,
				new_version: $('#importDrawingVersion').prop('checked') ? 1 : 0,
			},
			callback: function (r) {
				var message = r.message || {};
				if (message.success) {
					saveReceipt(message.receipt || {});
					DrawingImport.done(message);
					return;
				}
				if (message.rows) renderRows($.extend({}, state.preview, { rows: message.rows, counts: message.counts }));
				fail(message.error || scheduleText("Could not import the drawing."));
			},
			error: function () { fail(scheduleText("Could not import the drawing.")); },
			always: function () { updateConfirm(); },
		});
	}

	function receipt(event) {
		if (event) event.preventDefault();
		frappe.call({
			method: BASE + 'get_drawing_receipt',
			type: 'GET',
			args: { schedule: schedule_name },
			callback: function (r) {
				var message = r.message || {};
				if (message.success) saveReceipt(message.receipt || {});
				else fail(scheduleText("No drawing has been imported into this schedule yet."));
			},
			error: function () { fail(scheduleText("No drawing has been imported into this schedule yet.")); },
		});
	}

	if (scheduleContext.drawing_import) {
		$(document).on('change', '#importDrawingFile', function () { choose(this.files && this.files[0]); });
		$(document).on('click', '#importDrawingRefresh', function () { if (state.content) preview(); });
		$(document).on('change', '#importDrawingRemove, #importDrawingVersion', updateConfirm);
		$(document).on('click', '#importDrawingConfirm', commit);
		$(document).on('click', '#importDrawingReceipt', receipt);
		$(document).on('show.bs.modal', '#importDrawingModal', function () {
			$('#importDrawingFile').val('');
			reset();
		});
	}

	return {
		choose: choose,
		choices: choices,
		done: function (message) {
			var target = message.schedule && message.schedule !== schedule_name ? '/portal/schedules/' + encodeURIComponent(message.schedule) : null;
			if (target) window.location.assign(target);
			else window.location.reload();
		},
		save: function (blob, name) {
			var link = document.createElement('a');
			link.href = URL.createObjectURL(blob);
			link.download = name;
			document.body.appendChild(link);
			link.click();
			link.remove();
			setTimeout(function () { URL.revokeObjectURL(link.href); }, 0);
		},
	};
})();
