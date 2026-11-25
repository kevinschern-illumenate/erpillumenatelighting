// Schedule detail page (draw-to-quote plan 2.7, implementation plan WP 1.3, 1.8, 1.10, 1.11): import a
// drawing package (ilq/2 from the AutoCAD toolkit, or an ASCII DXF). The server plans every run through
// the configurators (dry run); runs that leave an option open get a choice here (one answer can fill a
// whole group of runs), DXF layers get a style and a schedule Type, lines whose runs left the drawing are
// removed only when the dealer ticks the box, and a locked or quoted schedule imports into a new version.
// The server plans again on import and saves everything in one transaction; afterwards the dialog offers
// the quote request. Every value from the package is shown as text only.
var DrawingImport = (function () {
	var BASE = 'illumenate_lighting.illumenate_lighting.portal.drawing_import.';
	var PRESETS = 'illumenate_lighting.illumenate_lighting.portal.presets.list_presets';
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
	var SCALE = {
		verified: function () { return scheduleText("Calibrated"); },
		declared: function () { return scheduleText("Units only, not calibrated"); },
		unverified: function () { return scheduleText("Not verified"); },
	};
	var state = { filename: null, content: null, preview: null };
	var plan = null;
	var presets = null;

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
		$('#importDrawingPreview, #importDrawingRemoveWrap, #importDrawingVersionWrap, #importDrawingWarnings, #importDrawingRefresh, #importDrawingSource, #importDrawingSheets, #importDrawingLayers, #importDrawingGroups, #importDrawingDone').prop('hidden', true);
		$('#importDrawingRows, #importDrawingWarnings, #importDrawingSheetRows, #importDrawingLayerRows, #importDrawingGroupList, #importDrawingBlockers').empty();
		$('#importDrawingCounts, #importDrawingSource').text('');
		$('#importDrawingRemove, #importDrawingVersion').prop('checked', false);
		fail('');
		updateConfirm();
	}

	// Values for the options a run's style leaves open: {run id: {selection key: value}}. A group answer
	// fills every run in its group; a value typed on the run itself wins.
	function choices() {
		var chosen = {};
		$('#importDrawingGroupList [data-group-key]').each(function () {
			var value = String(this.value || '').trim();
			if (!value) return;
			var key = this.getAttribute('data-group-key');
			JSON.parse(this.getAttribute('data-group-runs') || '[]').forEach(function (run) {
				chosen[run] = chosen[run] || {};
				chosen[run][key] = value;
			});
		});
		$('#importDrawingRows input[data-choice-run]').each(function () {
			var value = String(this.value || '').trim();
			if (!value) return;
			var run = this.getAttribute('data-choice-run');
			chosen[run] = chosen[run] || {};
			chosen[run][this.getAttribute('data-choice-key')] = value;
		});
		return chosen;
	}

	// DXF uploads: the style (saved preset) and schedule Type chosen per layer.
	function layerOptions() {
		var options = { presets: {}, types: {} };
		var any = false;
		$('#importDrawingLayerRows [data-layer-preset]').each(function () {
			if (this.value) { options.presets[this.getAttribute('data-layer-preset')] = this.value; any = true; }
		});
		$('#importDrawingLayerRows [data-layer-type]').each(function () {
			var value = String(this.value || '').trim();
			if (value) { options.types[this.getAttribute('data-layer-type')] = value; any = true; }
		});
		return any ? options : null;
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

	function choiceInputs(td, entry, previous, remembered) {
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
				input.value = ((previous[entry.id] || {})[key]) || ((remembered[entry.id] || {})[key]) || '';
				td.appendChild(label);
				td.appendChild(input);
			});
		});
	}

	function renderGroups(message, previousGroups) {
		var list = document.getElementById('importDrawingGroupList');
		if (!list) return;
		list.textContent = '';
		var groups = (message.choice_groups || []).filter(function (group) { return (group.runs || []).length > 1; });
		groups.forEach(function (group, index) {
			var box = document.createElement('div');
			box.className = 'form-row align-items-end mb-2';
			var title = document.createElement('div');
			title.className = 'col-12 small';
			title.textContent = format(scheduleText("{0}: {1} runs"), group.style || group.template, group.runs.length);
			box.appendChild(title);
			(group.keys || []).forEach(function (item) {
				var id = 'importDrawingGroup-' + index + '-' + item.key;
				var col = document.createElement('div');
				col.className = 'col-auto';
				var label = document.createElement('label');
				label.htmlFor = id;
				label.className = 'small mb-0';
				label.textContent = item.key;
				var field;
				if ((item.values || []).length) {
					field = document.createElement('select');
					var blank = document.createElement('option');
					blank.value = '';
					blank.textContent = format(scheduleText("Choose {0}"), item.key);
					field.appendChild(blank);
					item.values.forEach(function (value) {
						var option = document.createElement('option');
						option.value = String(value);
						option.textContent = String(value);
						field.appendChild(option);
					});
				} else {
					field = document.createElement('input');
					field.type = 'text';
					field.placeholder = format(scheduleText("Choose {0}"), item.key);
				}
				field.className = 'form-control form-control-sm';
				field.id = id;
				field.setAttribute('data-group-key', item.key);
				field.setAttribute('data-group-runs', JSON.stringify(group.runs));
				field.value = previousGroups[id] || '';
				col.appendChild(label);
				col.appendChild(field);
				box.appendChild(col);
			});
			list.appendChild(box);
		});
		$('#importDrawingGroups').prop('hidden', !groups.length);
	}

	function presetOptions(select, layer) {
		var blank = document.createElement('option');
		blank.value = '';
		blank.textContent = layer.preset || layer.template || scheduleText("Choose a style");
		select.appendChild(blank);
		(presets || []).filter(function (preset) { return preset.available !== false; }).forEach(function (preset) {
			var option = document.createElement('option');
			option.value = preset.name;
			option.textContent = preset.label + (preset.cad_code ? ' (' + preset.cad_code + ')' : '');
			select.appendChild(option);
		});
	}

	function renderLayers(message, previous) {
		var body = document.getElementById('importDrawingLayerRows');
		if (!body) return;
		body.textContent = '';
		var layers = message.layers || [];
		layers.forEach(function (layer, index) {
			var tr = document.createElement('tr');
			cell(tr, layer.layer);
			cell(tr, layer.runs);
			var styleCell = cell(tr, '');
			var select = document.createElement('select');
			select.className = 'form-control form-control-sm';
			select.id = 'importDrawingLayerPreset-' + index;
			select.setAttribute('data-layer-preset', layer.layer);
			select.setAttribute('aria-label', format(scheduleText("Style for layer {0}"), layer.layer));
			presetOptions(select, layer);
			select.value = (previous.presets || {})[layer.layer] || '';
			styleCell.appendChild(select);
			if (layer.needs_preset) {
				var hint = document.createElement('small');
				hint.className = 'text-warning d-block';
				hint.textContent = scheduleText("Choose a style for this layer");
				styleCell.appendChild(hint);
			}
			var typeCell = cell(tr, '');
			var input = document.createElement('input');
			input.type = 'text';
			input.className = 'form-control form-control-sm';
			input.setAttribute('data-layer-type', layer.layer);
			input.setAttribute('aria-label', format(scheduleText("Type for layer {0}"), layer.layer));
			input.placeholder = layer.fixture_type || '';
			input.value = (previous.types || {})[layer.layer] || '';
			typeCell.appendChild(input);
			body.appendChild(tr);
		});
		$('#importDrawingLayers').prop('hidden', !layers.length);
		if (layers.length && presets === null) loadPresets(message, previous);
	}

	function loadPresets(message, previous) {
		presets = [];
		frappe.call({
			method: PRESETS,
			type: 'GET',
			args: { schedule_name: schedule_name },
			callback: function (r) {
				presets = ((r.message || {}).presets) || [];
				renderLayers(message, previous);
			},
		});
	}

	function renderSheets(message) {
		var source = message.source || {};
		var line = source.tool ? format(scheduleText("Made with {0} {1}"), source.tool, source.version || '') : '';
		$('#importDrawingSource').text(line).prop('hidden', !line);
		var body = document.getElementById('importDrawingSheetRows');
		if (!body) return;
		body.textContent = '';
		var sheets = message.sheets || [];
		sheets.forEach(function (sheet) {
			var tr = document.createElement('tr');
			tr.setAttribute('data-scale-status', sheet.status);
			cell(tr, sheet.label || sheet.id);
			cell(tr, (SCALE[sheet.status] || SCALE.unverified)());
			cell(tr, sheet.used ? scheduleText("Yes") : scheduleText("No"));
			body.appendChild(tr);
		});
		$('#importDrawingSheets').prop('hidden', !sheets.length);
	}

	function groupValues() {
		var values = {};
		$('#importDrawingGroupList [data-group-key]').each(function () { if (this.value) values[this.id] = this.value; });
		return values;
	}

	// A multi-run group is one schedule line; its runs (a stacked run once per copy) follow its row.
	function memberRows(body, entry) {
		(entry.members || []).forEach(function (member) {
			var tr = document.createElement('tr');
			tr.className = 'text-muted';
			tr.setAttribute('data-drawing-member', entry.id);
			cell(tr, '');
			cell(tr, member.label);
			cell(tr, member.run ? format(scheduleText("Drawn as {0}"), member.run) : '');
			cell(tr, member.drawn_length_in);
			cell(tr, member.server_length_in);
			cell(tr, '');
			cell(tr, '');
			cell(tr, format(scheduleText("{0} W on {1} circuit(s)"), member.watts, member.circuits));
			body.appendChild(tr);
		});
	}

	function renderRows(message) {
		var previous = choices();
		var remembered = message.previous_choices || {};
		var previousGroups = groupValues();
		var previousLayers = layerOptions() || {};
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
			if (entry.status === 'needs_choice') choiceInputs(details, entry, previous, remembered);
			if (entry.kind === 'group') tr.setAttribute('data-drawing-kind', 'group');
			body.appendChild(tr);
			if (entry.kind === 'group') memberRows(body, entry);
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
		renderSheets(message);
		renderGroups(message, previousGroups);
		renderLayers(message, previousLayers);
		$('#importDrawingRefresh').prop('hidden', !counts.needs_choice && !(message.layers || []).length);
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

	function requestArgs(extra) {
		var args = { schedule: schedule_name, filename: state.filename, content: state.content, choices: JSON.stringify(choices()) };
		var options = layerOptions();
		if (options) args.options = JSON.stringify(options);
		return $.extend(args, extra || {});
	}

	function preview() {
		fail('');
		$('#importDrawingCounts').text(scheduleText("Reading the drawing…"));
		frappe.call({
			method: BASE + 'preview_drawing_import',
			type: 'POST',
			args: requestArgs(),
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
		if (!/\.(json|ilq|dxf)$/i.test(file.name || '')) {
			fail(scheduleText("Upload the .ilq.json file from ILQUOTE."));
			return;
		}
		if (file.size > (/\.dxf$/i.test(file.name) ? 4 * MAX_BYTES : MAX_BYTES)) {
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

	// The optional plotted plan travels with the import (draw-to-quote 4.6).
	function choosePlan(file) {
		plan = null;
		fail('');
		if (!file) return;
		if (!/\.pdf$/i.test(file.name || '') || file.size > 20 * 1024 * 1024) {
			fail(scheduleText("Upload the plan as a PDF under 20 MB."));
			return;
		}
		var reader = new FileReader();
		reader.onload = function () {
			var result = String(reader.result || '');
			plan = result.slice(result.indexOf(',') + 1);
		};
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
			args: requestArgs({
				expected_modified: modified(),
				confirm_removals: $('#importDrawingRemove').prop('checked') ? 1 : 0,
				new_version: $('#importDrawingVersion').prop('checked') ? 1 : 0,
				plan_pdf: plan || '',
			}),
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

	// Earlier imports of this schedule, newest first (WP 1.10).
	function history() {
		var body = document.getElementById('importDrawingHistoryRows');
		if (!body) return;
		frappe.call({
			method: BASE + 'list_drawing_imports',
			type: 'GET',
			args: { schedule: schedule_name },
			callback: function (r) {
				var imports = ((r.message || {}).imports) || [];
				body.textContent = '';
				imports.forEach(function (item) {
					var tr = document.createElement('tr');
					cell(tr, item.name + (item.status === 'Superseded' ? ' ' + scheduleText("(superseded)") : ''));
					cell(tr, item.drawing_file + (item.drawing_rev ? ' rev ' + item.drawing_rev : ''));
					cell(tr, [item.source_tool, item.source_version].filter(Boolean).join(' '));
					cell(tr, item.scale_status ? (SCALE[item.scale_status] || SCALE.unverified)() + (item.scale_confirmed_by ? ' ' + scheduleText("(confirmed)") : '') : '');
					cell(tr, item.runs_added);
					cell(tr, item.runs_updated);
					cell(tr, item.lines_removed);
					cell(tr, item.imported_on);
					body.appendChild(tr);
				});
				$('#importDrawingHistory').prop('hidden', !imports.length);
			},
		});
	}

	// After an import: the summary and the quote request (WP 1.11). The server refuses a quote for an
	// unverified scale too; the reasons are shown here so the button is not a surprise.
	function finished(message) {
		var target = message.schedule && message.schedule !== schedule_name ? '/portal/schedules/' + encodeURIComponent(message.schedule) : null;
		if (!document.getElementById('importDrawingDone')) {
			if (target) window.location.assign(target);
			else window.location.reload();
			return;
		}
		$('#importDrawingPreview, #importDrawingRemoveWrap, #importDrawingVersionWrap, #importDrawingLayers, #importDrawingGroups, #importDrawingRefresh').prop('hidden', true);
		$('#importDrawingConfirm').prop('disabled', true);
		$('#importDrawingDoneText').text(target
			? format(scheduleText("Imported into the new schedule version {0}."), message.schedule)
			: format(scheduleText("Imported as {0}. The receipt was downloaded for ILRECEIPT."), message.import || ''));
		$('#importDrawingDone').prop('hidden', false);
		$('#importDrawingFinish').off('click').on('click', function () {
			if (target) window.location.assign(target);
			else window.location.reload();
		});
		var $quote = $('#importDrawingQuote').prop('disabled', true);
		frappe.call({
			method: BASE + 'get_quote_blockers',
			type: 'GET',
			args: { schedule: message.schedule || schedule_name },
			callback: function (r) {
				var blockers = ((r.message || {}).blockers) || [];
				var $list = $('#importDrawingBlockers').empty().prop('hidden', !blockers.length);
				blockers.forEach(function (text) { $list.append($('<li>').text(text)); });
				$quote.prop('disabled', !!blockers.length || typeof PortalCommercial === 'undefined');
			},
		});
		$quote.off('click').on('click', function () {
			if (target) { window.location.assign(target); return; }
			PortalCommercial.quote(schedule_name, message.modified);
		});
	}

	if (scheduleContext.drawing_import) {
		$(document).on('change', '#importDrawingFile', function () { choose(this.files && this.files[0]); });
		$(document).on('change', '#importDrawingPlan', function () { choosePlan(this.files && this.files[0]); });
		$(document).on('click', '#importDrawingRefresh', function () { if (state.content) preview(); });
		$(document).on('change', '#importDrawingRemove, #importDrawingVersion', updateConfirm);
		$(document).on('click', '#importDrawingConfirm', commit);
		$(document).on('click', '#importDrawingReceipt', receipt);
		$(document).on('show.bs.modal', '#importDrawingModal', function () {
			$('#importDrawingFile, #importDrawingPlan').val('');
			plan = null;
			reset();
			history();
		});
		// "New schedule from drawing" lands here with ?import=1 (WP 1.6).
		if (/[?&]import=1(&|$)/.test(window.location.search || '') && typeof $.fn.modal === 'function') {
			$(function () { $('#importDrawingModal').modal('show'); });
		}
	}

	return {
		choose: choose,
		choosePlan: choosePlan,
		choices: choices,
		layerOptions: layerOptions,
		history: history,
		done: finished,
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
