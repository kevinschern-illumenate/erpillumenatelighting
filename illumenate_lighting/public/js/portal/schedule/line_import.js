// Schedule detail page (plan 3.4): import lines from a CSV/Excel sheet. The server reads the
// sheet, maps its columns and plans every row (dry run); the dealer can change the mapping and
// then imports. The server plans the sheet again on import and adds everything in one save.
// Every value from the sheet is shown as text only.
var ScheduleImport = (function () {
	var BASE = 'illumenate_lighting.illumenate_lighting.portal.schedule_import.';
	var MAX_BYTES = 1024 * 1024;
	var STATUS = {
		ok: { label: function () { return scheduleText("Ready"); }, badge: 'badge-success' },
		needs_configuration: { label: function () { return scheduleText("Needs configuration"); }, badge: 'badge-warning' },
		error: { label: function () { return scheduleText("Error"); }, badge: 'badge-danger' },
	};
	var state = { filename: null, content: null, counts: null };

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
		$('#importLinesError').text(text || '').prop('hidden', !text);
	}

	function reset() {
		state = { filename: null, content: null, counts: null };
		$('#importLinesMapping, #importLinesPreview, #importLinesSkipWrap').prop('hidden', true);
		$('#importLinesMappingFields, #importLinesRows').empty();
		$('#importLinesCounts').text('');
		$('#importLinesSkip').prop('checked', false);
		fail('');
		updateConfirm();
	}

	function mapping() {
		var chosen = {};
		$('#importLinesMappingFields select[data-import-field]').each(function () {
			if (this.value !== '') chosen[this.getAttribute('data-import-field')] = Number(this.value);
		});
		return chosen;
	}

	function renderMapping(columns, fields, chosen) {
		var container = document.getElementById('importLinesMappingFields');
		container.textContent = '';
		fields.forEach(function (field) {
			var id = 'importLinesField-' + field.field;
			var group = document.createElement('div');
			group.className = 'form-group col-sm-6 col-lg-4';
			var label = document.createElement('label');
			label.htmlFor = id;
			label.textContent = field.label;
			var select = document.createElement('select');
			select.className = 'form-control form-control-sm';
			select.id = id;
			select.setAttribute('data-import-field', field.field);
			select.appendChild(new Option(scheduleText("Not imported"), ''));
			columns.forEach(function (column, index) {
				select.appendChild(new Option(column || format(scheduleText("Column {0}"), index + 1), String(index)));
			});
			select.value = Object.prototype.hasOwnProperty.call(chosen, field.field) ? String(chosen[field.field]) : '';
			group.appendChild(label);
			group.appendChild(select);
			container.appendChild(group);
		});
		$('#importLinesMapping').prop('hidden', false);
	}

	function cell(row, text) {
		var td = document.createElement('td');
		td.textContent = text === undefined || text === null ? '' : String(text);
		row.appendChild(td);
		return td;
	}

	function renderRows(rows, counts) {
		var body = document.getElementById('importLinesRows');
		body.textContent = '';
		rows.forEach(function (entry) {
			var tr = document.createElement('tr');
			tr.setAttribute('data-import-status', entry.status);
			cell(tr, entry.row);
			cell(tr, entry.line_id);
			cell(tr, entry.qty);
			cell(tr, entry.location);
			var status = STATUS[entry.status] || STATUS.error;
			var badge = document.createElement('span');
			badge.className = 'badge ' + status.badge;
			badge.textContent = status.label();
			cell(tr, '').appendChild(badge);
			cell(tr, [entry.summary].concat(entry.messages || []).filter(Boolean).join(' · '));
			body.appendChild(tr);
		});
		if (counts) {
			state.counts = counts;
			$('#importLinesCounts').text(format(
				scheduleText("{0} ready, {1} need configuration, {2} with errors."),
				counts.ok, counts.needs_configuration, counts.error
			));
			$('#importLinesSkipWrap').prop('hidden', !counts.error);
		}
		$('#importLinesPreview').prop('hidden', false);
		updateConfirm();
	}

	function importable() {
		var counts = state.counts;
		if (!counts || !state.content) return 0;
		if (counts.error && !$('#importLinesSkip').prop('checked')) return 0;
		return counts.ok + counts.needs_configuration;
	}

	function updateConfirm() {
		var count = importable();
		$('#importLinesConfirm')
			.prop('disabled', !count)
			.text(count ? format(scheduleText("Import {0} line(s)"), count) : scheduleText("Import"));
	}

	function preview(chosen) {
		fail('');
		$('#importLinesCounts').text(scheduleText("Reading the sheet…"));
		frappe.call({
			method: BASE + 'preview_schedule_import',
			type: 'POST',
			args: {
				schedule: schedule_name,
				filename: state.filename,
				content: state.content,
				mapping: chosen ? JSON.stringify(chosen) : '',
			},
			callback: function (r) {
				var message = r.message || {};
				if (!message.success) {
					$('#importLinesCounts').text('');
					fail(message.error || scheduleText("Could not read this sheet."));
					return;
				}
				renderMapping(message.columns || [], message.fields || [], message.mapping || {});
				renderRows(message.rows || [], message.counts);
			},
			error: function () {
				$('#importLinesCounts').text('');
				fail(scheduleText("Could not read this sheet."));
			},
		});
	}

	function choose(file) {
		reset();
		if (!file) return;
		if (!/\.(csv|xlsx)$/i.test(file.name || '')) {
			fail(scheduleText("Upload a .csv or .xlsx file."));
			return;
		}
		if (file.size > MAX_BYTES) {
			fail(scheduleText("The file is larger than 1 MB."));
			return;
		}
		var reader = new FileReader();
		reader.onload = function () {
			var result = String(reader.result || '');
			state.filename = file.name;
			state.content = result.slice(result.indexOf(',') + 1);
			preview(null);
		};
		reader.onerror = function () { fail(scheduleText("Could not read this sheet.")); };
		reader.readAsDataURL(file);
	}

	function commit() {
		var $button = $('#importLinesConfirm');
		if (!importable()) return;
		$button.prop('disabled', true);
		frappe.call({
			method: BASE + 'commit_schedule_import',
			type: 'POST',
			args: {
				schedule: schedule_name,
				filename: state.filename,
				content: state.content,
				mapping: JSON.stringify(mapping()),
				expected_modified: modified(),
				skip_errors: $('#importLinesSkip').prop('checked') ? 1 : 0,
			},
			callback: function (r) {
				var message = r.message || {};
				if (message.success) {
					ScheduleImport.reload();
					return;
				}
				if (message.rows) renderRows(message.rows, message.counts);
				fail(message.error || scheduleText("Could not import the lines."));
			},
			error: function () { fail(scheduleText("Could not import the lines.")); },
			always: function () { updateConfirm(); },
		});
	}

	// The header, then guidance and example rows. Those start with "#", which the import skips,
	// so the file can be filled in under them and uploaded unchanged.
	function template() {
		var rows = [scheduleContext.import_columns || []].concat(scheduleContext.import_template_rows || []);
		var text = rows.map(function (row) {
			return row.map(function (cell) { return '"' + String(cell == null ? '' : cell).replace(/"/g, '""') + '"'; }).join(',');
		}).join('\r\n');
		// The byte-order mark makes Excel open the file as UTF-8.
		ScheduleImport.save(new Blob(['\ufeff' + text + '\r\n'], { type: 'text/csv' }), 'schedule-import-template.csv');
	}

	if (scheduleContext.schedule_import) {
		$(document).on('change', '#importLinesFile', function () { choose(this.files && this.files[0]); });
		$(document).on('click', '#importLinesRefresh', function () { if (state.content) preview(mapping()); });
		$(document).on('change', '#importLinesSkip', updateConfirm);
		$(document).on('click', '#importLinesConfirm', commit);
		$(document).on('click', '#importLinesTemplate', function (event) {
			event.preventDefault();
			template();
		});
		$(document).on('show.bs.modal', '#importLinesModal', function () {
			$('#importLinesFile').val('');
			reset();
		});
	}

	return {
		choose: choose,
		reload: function () { window.location.reload(); },
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
