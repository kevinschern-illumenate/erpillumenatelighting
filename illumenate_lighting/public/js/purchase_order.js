// ilLumenate Lighting - Purchase Order customizations
// "Supplier Parts": edit each item's supplier part number and supplier description for
// this PO's supplier. The values are saved on the Item (Supplier Items table), which is
// where the ilL Purchase Order print format reads them from.

const ILL_PO_PARTS_API = 'illumenate_lighting.illumenate_lighting.api.purchase_order';

function ill_po_item_lines(frm) {
	const lines = {};
	for (const row of frm.doc.items || []) {
		if (row.item_code && !lines[row.item_code]) lines[row.item_code] = row;
	}
	return lines;
}

async function ill_edit_supplier_parts(frm) {
	if (!frm.doc.supplier) {
		frappe.msgprint(__('Choose a supplier first.'));
		return;
	}
	const lines = ill_po_item_lines(frm);
	const codes = Object.keys(lines);
	if (!codes.length) {
		frappe.msgprint(__('Add items to the purchase order first.'));
		return;
	}
	const response = await frappe.call({
		method: `${ILL_PO_PARTS_API}.get_supplier_part_info`,
		args: {supplier: frm.doc.supplier, item_codes: codes},
		freeze: true,
	});
	const info = response.message || {items: {}};
	const esc = frappe.utils.escape_html;

	const fields = [{
		fieldtype: 'HTML',
		fieldname: 'intro',
		options: `<p class="text-muted">${esc(__('Saved on each item for {0}, and used on the purchase order print.', [frm.doc.supplier_name || frm.doc.supplier]))}</p>`,
	}];
	codes.forEach((code, i) => {
		const line = lines[code];
		const saved = info.items[code] || {};
		const name = line.item_name && line.item_name !== code ? ` · ${line.item_name}` : '';
		fields.push(
			{fieldtype: 'Section Break', label: `${code}${name}`},
			{fieldtype: 'Data', fieldname: `part_${i}`, label: __('Supplier Part Number'),
				default: saved.found ? saved.supplier_part_no : (line.supplier_part_no || '')},
		);
		if (info.has_description) {
			fields.push(
				{fieldtype: 'Column Break'},
				{fieldtype: 'Small Text', fieldname: `desc_${i}`, label: __('Supplier Description'),
					default: saved.supplier_description || ''},
			);
		}
	});

	const dialog = new frappe.ui.Dialog({
		title: __('Supplier Parts for {0}', [frm.doc.supplier_name || frm.doc.supplier]),
		size: 'large',
		fields,
		primary_action_label: __('Save to Items'),
		async primary_action(values) {
			const rows = codes.map((code, i) => ({
				item_code: code,
				supplier_part_no: values[`part_${i}`] || '',
				supplier_description: values[`desc_${i}`] || '',
			}));
			const result = await frappe.call({
				method: `${ILL_PO_PARTS_API}.update_supplier_part_info`,
				args: {supplier: frm.doc.supplier, rows, purchase_order: frm.is_new() ? null : frm.doc.name},
				freeze: true,
				freeze_message: __('Saving supplier parts'),
			});
			dialog.hide();
			const saved = (result.message && result.message.updated) || [];
			if (frm.doc.docstatus === 0) {
				// Draft lines carry the part number too; it saves with the PO.
				const parts = Object.fromEntries(rows.map(row => [row.item_code, row.supplier_part_no]));
				let touched = false;
				for (const row of frm.doc.items || []) {
					if (row.item_code in parts && (row.supplier_part_no || '') !== parts[row.item_code]) {
						frappe.model.set_value(row.doctype, row.name, 'supplier_part_no', parts[row.item_code]);
						touched = true;
					}
				}
				frm.refresh_field('items');
				if (touched) {
					frappe.show_alert({message: __('Items updated. Save the purchase order to keep the part numbers on its lines.'), indicator: 'blue'}, 7);
					return;
				}
			} else if ((result.message?.lines || []).length) {
				frm.reload_doc();
			}
			frappe.show_alert({
				message: saved.length ? __('Updated {0} item(s).', [saved.length]) : __('No changes.'),
				indicator: saved.length ? 'green' : 'blue',
			});
		},
	});
	dialog.show();
}

frappe.ui.form.on('Purchase Order', {
	refresh(frm) {
		// Saving writes to the Items, so it needs edit rights on both.
		if (frm.doc.docstatus === 2 || !frappe.model.can_write('Purchase Order') || !frappe.model.can_write('Item')) return;
		frm.add_custom_button(__('Supplier Parts'), () => ill_edit_supplier_parts(frm));
	},
});
