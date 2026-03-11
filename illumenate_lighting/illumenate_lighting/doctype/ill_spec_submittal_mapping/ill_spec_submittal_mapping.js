// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.ui.form.on("ilL-Spec-Submittal-Mapping", {
	refresh: function(frm) {
		// Clear HTML field on refresh
		frm.set_df_property('available_fields_html', 'options', '');
	},
	
	source_doctype: function(frm) {
		// Clear the fields display when doctype changes
		frm.set_df_property('available_fields_html', 'options', '');
		frm.set_value('source_field', '');
	},
	
	show_fields_button: function(frm) {
		if (!frm.doc.source_doctype) {
			frappe.msgprint(__('Please select a Source DocType first'));
			return;
		}
		
		frappe.call({
			method: 'illumenate_lighting.illumenate_lighting.doctype.ill_spec_submittal_mapping.ill_spec_submittal_mapping.get_doctype_fields',
			args: {
				doctype: frm.doc.source_doctype
			},
			callback: function(r) {
				if (r.message) {
					let fields = r.message;
					let html = build_fields_table(fields, frm);
					frm.set_df_property('available_fields_html', 'options', html);
				}
			}
		});
	}
});

function build_fields_table(fields, frm) {
	if (!fields || fields.length === 0) {
		return '<p class="text-muted">No fields found for this DocType</p>';
	}
	
	let html = `
		<div class="available-fields-container" style="max-height: 400px; overflow-y: auto; border: 1px solid var(--border-color); border-radius: var(--border-radius); margin-top: 10px;">
			<table class="table table-bordered table-sm" style="margin-bottom: 0;">
				<thead style="position: sticky; top: 0; background: var(--bg-color);">
					<tr>
						<th style="width: 40%;">Field Name</th>
						<th style="width: 35%;">Label</th>
						<th style="width: 15%;">Type</th>
						<th style="width: 10%;">Use</th>
					</tr>
				</thead>
				<tbody>
	`;
	
	for (let field of fields) {
		let linkedTo = field.options ? `<br><small class="text-muted">→ ${field.options}</small>` : '';
		html += `
			<tr>
				<td><code>${field.fieldname}</code></td>
				<td>${field.label}${linkedTo}</td>
				<td><span class="badge" style="background: var(--primary-color); color: white;">${field.fieldtype}</span></td>
				<td>
					<button class="btn btn-xs btn-primary use-field-btn" data-fieldname="${field.fieldname}">
						Use
					</button>
				</td>
			</tr>
		`;
	}
	
	html += `
				</tbody>
			</table>
		</div>
		<p class="text-muted" style="margin-top: 8px; font-size: 12px;">
			<strong>Tip:</strong> Click "Use" to populate the Source Field, or type the field name manually.
		</p>
	`;
	
	// Add click handler after render
	setTimeout(() => {
		document.querySelectorAll('.use-field-btn').forEach(btn => {
			btn.addEventListener('click', function() {
				let fieldname = this.getAttribute('data-fieldname');
				frm.set_value('source_field', fieldname);
				frappe.show_alert({
					message: __('Source Field set to: {0}', [fieldname]),
					indicator: 'green'
				}, 3);
			});
		});
	}, 100);
	
	return html;
}
