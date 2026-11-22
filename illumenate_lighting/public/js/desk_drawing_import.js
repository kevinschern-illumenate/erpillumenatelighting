// Draw-to-quote plan 2.8 and implementation plan WP 1.7: staff import a drawing (AutoCAD ilq/2 package or
// ASCII DXF) from the schedule form, for design-services jobs and dealer jobs sent in by email. Same server
// path as the portal: a dry run with open choices, DXF layer styles and Types answered here, then an
// all-or-nothing import. An import into a dealer's schedule is recorded as made on the dealer's behalf.
// The server refuses users the CAD rollout does not include; values from the package are escaped.
(function () {
	var BASE = 'illumenate_lighting.illumenate_lighting.portal.drawing_import.';

	function esc(value) {
		return frappe.utils.escape_html(value === undefined || value === null ? '' : String(value));
	}

	function choiceInputs(row) {
		return (row.parts || []).map(function (part) {
			return (part.missing || []).map(function (key) {
				return '<input type="text" class="form-control input-xs mt-1" data-choice-run="' + esc(row.id) + '" data-choice-key="' +
					esc(key) + '" placeholder="' + esc(__('Choose {0}', [key])) + '">';
			}).join('');
		}).join('');
	}

	function groups(message) {
		return (message.choice_groups || []).filter(function (group) { return (group.runs || []).length > 1; }).map(function (group) {
			return '<div class="form-inline mb-2"><span class="mr-2">' + esc(__('{0}: {1} runs', [group.style || group.template, group.runs.length])) + '</span>' +
				(group.keys || []).map(function (item) {
					var runs = esc(JSON.stringify(group.runs));
					if ((item.values || []).length) {
						return '<select class="form-control input-xs mr-2" data-group-key="' + esc(item.key) + '" data-group-runs="' + runs + '"><option value="">' +
							esc(__('Choose {0}', [item.key])) + '</option>' + item.values.map(function (value) {
								return '<option value="' + esc(value) + '">' + esc(value) + '</option>';
							}).join('') + '</select>';
					}
					return '<input type="text" class="form-control input-xs mr-2" data-group-key="' + esc(item.key) + '" data-group-runs="' + runs +
						'" placeholder="' + esc(__('Choose {0}', [item.key])) + '">';
				}).join('') + '</div>';
		}).join('');
	}

	function layers(message) {
		var rows = (message.layers || []).map(function (layer) {
			return '<tr><td>' + esc(layer.layer) + '</td><td>' + esc(layer.runs) + '</td><td>' + esc(layer.preset || layer.template || '') +
				(layer.needs_preset ? ' <span class="text-warning">' + esc(__('needs a style')) + '</span>' : '') +
				'</td><td><input type="text" class="form-control input-xs" data-layer-preset="' + esc(layer.layer) + '" placeholder="' + esc(__('Preset name')) +
				'"></td><td><input type="text" class="form-control input-xs" data-layer-type="' + esc(layer.layer) + '" placeholder="' + esc(layer.fixture_type || '') +
				'"></td></tr>';
		}).join('');
		if (!rows) return '';
		return '<h6>' + esc(__('DXF layers')) + '</h6><table class="table table-sm table-bordered"><thead><tr><th>' +
			[__('Layer'), __('Runs'), __('Resolved style'), __('Preset'), __('Type')].map(esc).join('</th><th>') + '</th></tr></thead><tbody>' + rows + '</tbody></table>';
	}

	function sheets(message) {
		var source = message.source || {};
		var line = source.tool ? '<p class="text-muted">' + esc(__('Made with {0} {1}; scale: {2}', [source.tool, source.version || '', (message.scale || {}).status || ''])) + '</p>' : '';
		var rows = (message.sheets || []).map(function (sheet) {
			return '<tr><td>' + esc(sheet.label || sheet.id) + '</td><td>' + esc(sheet.status) + '</td><td>' + esc(sheet.used ? __('Yes') : __('No')) + '</td></tr>';
		}).join('');
		return line + (rows ? '<table class="table table-sm table-bordered"><thead><tr><th>' + [__('Sheet'), __('Scale'), __('Runs on it')].map(esc).join('</th><th>') +
			'</th></tr></thead><tbody>' + rows + '</tbody></table>' : '');
	}

	function table(message) {
		var rows = (message.rows || []).concat(message.other_lines || [], message.removals || []);
		var body = rows.map(function (row) {
			return '<tr><td>' + esc(row.id) + '</td><td>' + esc(row.fixture_type) + '</td><td>' + esc(row.style || row.summary || row.family) +
				'</td><td>' + esc(row.drawn_length_in) + '</td><td>' + esc(row.server_length_in) + '</td><td>' + esc(row.action) +
				'</td><td>' + esc(row.status) + '</td><td>' + esc((row.messages || []).join(' · ')) + (row.status === 'needs_choice' ? choiceInputs(row) : '') + '</td></tr>';
		}).join('');
		var warnings = (message.warnings || []).concat(message.blocking || []).map(function (text) {
			return '<div class="alert alert-warning">' + esc(text) + '</div>';
		}).join('');
		var counts = message.counts || {};
		return warnings + sheets(message) + layers(message) + groups(message) + '<p>' + esc(__('{0} ready, {1} need a choice, {2} with errors; {3} to add, {4} to update, {5} unchanged, {6} to remove.',
			[counts.ok || 0, counts.needs_choice || 0, counts.error || 0, counts.add || 0, counts.update || 0, counts.unchanged || 0, counts.remove || 0])) +
			'</p><div class="table-responsive"><table class="table table-sm table-bordered"><thead><tr><th>' +
			[__('Run'), __('Type'), __('Style'), __('Drawn (in)'), __('Built (in)'), __('Change'), __('Status'), __('Details')].map(esc).join('</th><th>') +
			'</th></tr></thead><tbody>' + body + '</tbody></table></div>';
	}

	function collect($wrapper) {
		var chosen = {};
		$wrapper.find('[data-group-key]').each(function () {
			var value = String(this.value || '').trim();
			if (!value) return;
			var key = this.getAttribute('data-group-key');
			JSON.parse(this.getAttribute('data-group-runs') || '[]').forEach(function (run) {
				chosen[run] = chosen[run] || {};
				chosen[run][key] = value;
			});
		});
		$wrapper.find('input[data-choice-run]').each(function () {
			var value = String(this.value || '').trim();
			if (!value) return;
			var run = this.getAttribute('data-choice-run');
			chosen[run] = chosen[run] || {};
			chosen[run][this.getAttribute('data-choice-key')] = value;
		});
		var options = { presets: {}, types: {} };
		$wrapper.find('[data-layer-preset]').each(function () { if (this.value.trim()) options.presets[this.getAttribute('data-layer-preset')] = this.value.trim(); });
		$wrapper.find('[data-layer-type]').each(function () { if (this.value.trim()) options.types[this.getAttribute('data-layer-type')] = this.value.trim(); });
		return { choices: chosen, options: options };
	}

	function readFile(file, done) {
		var reader = new FileReader();
		reader.onload = function () {
			var text = String(reader.result || '');
			done(text.slice(text.indexOf(',') + 1));
		};
		reader.readAsDataURL(file);
	}

	function open(frm) {
		var state = { filename: null, content: null, preview: null, plan: '' };
		var dialog = new frappe.ui.Dialog({
			title: __('Import Drawing'),
			size: 'extra-large',
			fields: [
				{ fieldtype: 'HTML', fieldname: 'picker' },
				{ fieldtype: 'Check', fieldname: 'confirm_removals', label: __('Remove lines whose runs are no longer in the drawing') },
				{ fieldtype: 'Check', fieldname: 'new_version', label: __('Import into a new version (locked or quoted schedule)') },
				{ fieldtype: 'HTML', fieldname: 'preview' },
			],
			primary_action_label: __('Import'),
			primary_action: function (values) {
				if (!state.preview) return;
				var answers = collect(dialog.fields_dict.preview.$wrapper);
				frappe.call({
					method: BASE + 'commit_drawing_import',
					args: {
						schedule: frm.doc.name,
						filename: state.filename,
						content: state.content,
						expected_modified: frm.doc.modified,
						choices: JSON.stringify(answers.choices),
						options: JSON.stringify(answers.options),
						plan_pdf: state.plan,
						confirm_removals: values.confirm_removals ? 1 : 0,
						new_version: values.new_version ? 1 : 0,
					},
					freeze: true,
					callback: function (r) {
						var message = r.message || {};
						if (!message.success) {
							if (message.rows) {
								state.preview = Object.assign({}, state.preview, { rows: message.rows, counts: message.counts });
								dialog.fields_dict.preview.$wrapper.html(table(state.preview));
							}
							frappe.msgprint(esc(message.error || __('Could not import the drawing.')));
							return;
						}
						dialog.hide();
						frappe.show_alert({ message: __('Drawing imported ({0})', [message.import]), indicator: 'green' });
						if (message.schedule && message.schedule !== frm.doc.name) frappe.set_route('Form', frm.doctype, message.schedule);
						else frm.reload_doc();
					},
				});
			},
			secondary_action_label: __('Update preview'),
			secondary_action: function () { if (state.content) preview(); },
		});

		function preview() {
			var answers = state.preview ? collect(dialog.fields_dict.preview.$wrapper) : { choices: {}, options: {} };
			frappe.call({
				method: BASE + 'preview_drawing_import',
				args: {
					schedule: frm.doc.name,
					filename: state.filename,
					content: state.content,
					choices: JSON.stringify(answers.choices),
					options: JSON.stringify(answers.options),
				},
				freeze: true,
				callback: function (r) {
					state.preview = r.message || null;
					dialog.fields_dict.preview.$wrapper.html(state.preview ? table(state.preview) : '');
				},
			});
		}

		var input = $('<input type="file" accept=".json,.ilq,.dxf,application/json" class="form-control">');
		var plan = $('<input type="file" accept=".pdf,application/pdf" class="form-control mt-2">');
		dialog.fields_dict.picker.$wrapper.empty().append(
			$('<label>').text(__('Drawing package (.ilq.json) or ASCII DXF')), input,
			$('<label class="mt-2">').text(__('Plotted plan (PDF, optional)')), plan
		);
		input.on('change', function () {
			var file = this.files && this.files[0];
			if (!file) return;
			readFile(file, function (content) {
				state.filename = file.name;
				state.content = content;
				state.preview = null;
				preview();
			});
		});
		plan.on('change', function () {
			var file = this.files && this.files[0];
			state.plan = '';
			if (file) readFile(file, function (content) { state.plan = content; });
		});
		dialog.show();
	}

	frappe.ui.form.on('ilL-Project-Fixture-Schedule', {
		refresh: function (frm) {
			if (frm.is_new() || !frappe.user.has_role('System Manager') && !frappe.user.has_role('ilL Applications Engineer') && !frappe.user.has_role('Sales User')) return;
			frm.add_custom_button(__('Import Drawing'), function () { open(frm); }, __('CAD'));
		},
	});
})();
