// Implementation plan WP 1.3 and 1.10: staff tools on a drawing import record. An Applications Engineer
// confirms an unverified scale (which lifts the quote-request gate) and support replays the import's
// preview against the schedule as it is now. Both are refused by the server for anyone else.
frappe.ui.form.on('ilL-CAD-Import', {
	refresh: function (frm) {
		var base = 'illumenate_lighting.illumenate_lighting.portal.drawing_import.';
		var engineer = frappe.user.has_role('ilL Applications Engineer') || frappe.user.has_role('System Manager');
		if (!engineer) return;
		if (frm.doc.scale_status === 'unverified' && !frm.doc.scale_confirmed_by) {
			frm.dashboard.set_headline(__('The scale of this drawing is not verified; its schedule cannot request a quote until it is confirmed.'));
			frm.add_custom_button(__('Confirm scale'), function () {
				frappe.prompt(
					{ fieldname: 'note', fieldtype: 'Small Text', label: __('How was the scale checked?'), reqd: 1 },
					function (values) {
						frappe.call({
							method: base + 'confirm_drawing_scale',
							args: { cad_import: frm.doc.name, note: values.note },
							callback: function () { frm.reload_doc(); },
						});
					},
					__('Confirm scale')
				);
			});
		}
		frm.add_custom_button(__('Replay preview'), function () {
			frappe.call({
				method: base + 'replay_drawing_import',
				type: 'GET',
				args: { cad_import: frm.doc.name },
				freeze: true,
				callback: function (r) {
					var message = r.message || {};
					var counts = message.counts || {};
					var rows = (message.rows || []).map(function (row) {
						return '<tr><td>' + frappe.utils.escape_html(row.id) + '</td><td>' + frappe.utils.escape_html(row.status) + '</td><td>' +
							frappe.utils.escape_html(row.action || '') + '</td><td>' + frappe.utils.escape_html((row.messages || []).join(' · ')) + '</td></tr>';
					}).join('');
					frappe.msgprint({
						title: __('Replay of {0}', [frm.doc.name]),
						wide: true,
						message: '<p>' + frappe.utils.escape_html(__('{0} ready, {1} need a choice, {2} with errors; {3} to add, {4} to update, {5} unchanged, {6} to remove.',
							[counts.ok || 0, counts.needs_choice || 0, counts.error || 0, counts.add || 0, counts.update || 0, counts.unchanged || 0, counts.remove || 0])) +
							'</p><table class="table table-sm table-bordered"><tbody>' + rows + '</tbody></table>',
					});
				},
			});
		});
	},
});
