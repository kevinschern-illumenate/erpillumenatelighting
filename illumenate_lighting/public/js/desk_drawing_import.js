// Draw-to-quote plan 2.8: staff import an AutoCAD drawing package (ilq/2) from the schedule form,
// for design-services jobs. Same server path as the portal: a dry run, then an all-or-nothing import.
// The server refuses users the CAD rollout does not include; values from the package are escaped.
(function () {
	var BASE = 'illumenate_lighting.illumenate_lighting.portal.drawing_import.';

	function esc(value) {
		return frappe.utils.escape_html(value === undefined || value === null ? '' : String(value));
	}

	function table(message) {
		var rows = (message.rows || []).concat(message.other_lines || [], message.removals || []);
		var body = rows.map(function (row) {
			return '<tr><td>' + esc(row.id) + '</td><td>' + esc(row.fixture_type) + '</td><td>' + esc(row.style || row.summary || row.family) +
				'</td><td>' + esc(row.drawn_length_in) + '</td><td>' + esc(row.server_length_in) + '</td><td>' + esc(row.action) +
				'</td><td>' + esc(row.status) + '</td><td>' + esc((row.messages || []).join(' · ')) + '</td></tr>';
		}).join('');
		var warnings = (message.warnings || []).concat(message.blocking || []).map(function (text) {
			return '<div class="alert alert-warning">' + esc(text) + '</div>';
		}).join('');
		var counts = message.counts || {};
		return warnings + '<p>' + esc(__('{0} ready, {1} need a choice, {2} with errors; {3} to add, {4} to update, {5} unchanged, {6} to remove.',
			[counts.ok || 0, counts.needs_choice || 0, counts.error || 0, counts.add || 0, counts.update || 0, counts.unchanged || 0, counts.remove || 0])) +
			'</p><div class="table-responsive"><table class="table table-sm table-bordered"><thead><tr><th>' +
			[__('Run'), __('Type'), __('Style'), __('Drawn (in)'), __('Built (in)'), __('Change'), __('Status'), __('Details')].map(esc).join('</th><th>') +
			'</th></tr></thead><tbody>' + body + '</tbody></table></div>';
	}

	function open(frm) {
		var state = { filename: null, content: null, preview: null };
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
				frappe.call({
					method: BASE + 'commit_drawing_import',
					args: {
						schedule: frm.doc.name,
						filename: state.filename,
						content: state.content,
						expected_modified: frm.doc.modified,
						confirm_removals: values.confirm_removals ? 1 : 0,
						new_version: values.new_version ? 1 : 0,
					},
					freeze: true,
					callback: function (r) {
						var message = r.message || {};
						if (!message.success) {
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
		});
		var input = $('<input type="file" accept=".json,.ilq,application/json" class="form-control">');
		dialog.fields_dict.picker.$wrapper.empty().append(input);
		input.on('change', function () {
			var file = this.files && this.files[0];
			if (!file) return;
			var reader = new FileReader();
			reader.onload = function () {
				var text = String(reader.result || '');
				state.filename = file.name;
				state.content = text.slice(text.indexOf(',') + 1);
				frappe.call({
					method: BASE + 'preview_drawing_import',
					args: { schedule: frm.doc.name, filename: state.filename, content: state.content },
					freeze: true,
					callback: function (r) {
						state.preview = r.message || null;
						dialog.fields_dict.preview.$wrapper.html(state.preview ? table(state.preview) : '');
					},
				});
			};
			reader.readAsDataURL(file);
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
