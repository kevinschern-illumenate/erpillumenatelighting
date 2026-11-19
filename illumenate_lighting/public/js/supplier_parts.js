// ilLumenate Lighting - supplier part numbers and descriptions on Purchase Orders and RFQs.
// The values live on the Item (Supplier Items table, one row per supplier); see
// api/supplier_parts.py. Each line shows Supplier Part Number and Supplier Description:
// picking an item or a supplier fills them from the Item, and saving the document writes
// changed values back to the Item. The "Supplier Parts" button edits every line at once,
// and on an RFQ with several suppliers it is how the values are set, one supplier at a time.

const ILL_SUPPLIER_PARTS_API = 'illumenate_lighting.illumenate_lighting.api.supplier_parts';
const ILL_LINE_DESCRIPTION = 'ill_supplier_description';

// The suppliers this document deals with: the PO's supplier, or the RFQ's suppliers.
function ill_parts_suppliers(frm) {
	if (frm.doctype === 'Request for Quotation') {
		return [...new Set((frm.doc.suppliers || []).map(row => row.supplier).filter(Boolean))];
	}
	return frm.doc.supplier ? [frm.doc.supplier] : [];
}

// The one supplier the lines carry values for, or null (an RFQ with several suppliers).
function ill_line_supplier(frm) {
	const suppliers = ill_parts_suppliers(frm);
	return suppliers.length === 1 ? suppliers[0] : null;
}

function ill_supplier_label(frm, supplier) {
	if (frm.doctype === 'Purchase Order') return frm.doc.supplier_name || supplier;
	const row = (frm.doc.suppliers || []).find(r => r.supplier === supplier);
	return (row && row.supplier_name) || supplier;
}

async function ill_fetch_supplier_parts(frm, supplier, codes) {
	const response = await frappe.call({
		method: `${ILL_SUPPLIER_PARTS_API}.get_supplier_part_info`,
		args: {supplier, item_codes: codes, doctype: frm.doctype},
	});
	return response.message || {items: {}};
}

// Fill lines from the Item for the line supplier. With overwrite, every line takes the
// supplier's values (after the supplier changed); without it, only blank values are filled.
async function ill_fill_lines(frm, rows, overwrite) {
	const supplier = ill_line_supplier(frm);
	rows = (rows || []).filter(row => row.item_code);
	if (frm.doc.docstatus !== 0 || !supplier || !rows.length) return;
	const info = await ill_fetch_supplier_parts(frm, supplier, [...new Set(rows.map(row => row.item_code))]);
	if (ill_line_supplier(frm) !== supplier) return; // the supplier changed while we waited
	for (const row of rows) {
		const saved = info.items[row.item_code];
		if (!saved) continue;
		if (overwrite || !row.supplier_part_no) {
			if ((row.supplier_part_no || '') !== saved.supplier_part_no) {
				frappe.model.set_value(row.doctype, row.name, 'supplier_part_no', saved.supplier_part_no);
			}
		}
		if (info.has_description && (overwrite || !row[ILL_LINE_DESCRIPTION])) {
			if ((row[ILL_LINE_DESCRIPTION] || '') !== saved.supplier_description) {
				frappe.model.set_value(row.doctype, row.name, ILL_LINE_DESCRIPTION, saved.supplier_description);
			}
		}
	}
}

// When the line supplier changes, the lines take the new supplier's values.
function ill_line_supplier_changed(frm) {
	const supplier = ill_line_supplier(frm);
	frm.refresh_field('items'); // RFQ lines turn read-only with several suppliers
	if (supplier === frm.__ill_parts_supplier) return;
	frm.__ill_parts_supplier = supplier;
	if (supplier) ill_fill_lines(frm, frm.doc.items, true);
}

function ill_item_lines(frm) {
	const lines = {};
	for (const row of frm.doc.items || []) {
		if (row.item_code && !lines[row.item_code]) lines[row.item_code] = row;
	}
	return lines;
}

async function ill_choose_parts_supplier(frm) {
	const suppliers = ill_parts_suppliers(frm);
	if (suppliers.length <= 1) return suppliers[0] || null;
	return new Promise(resolve => {
		frappe.prompt(
			{fieldname: 'supplier', fieldtype: 'Select', label: __('Supplier'), reqd: 1,
				options: suppliers, default: suppliers[0]},
			values => resolve(values.supplier),
			__('Supplier Parts for which supplier?'),
			__('Next'),
		);
	});
}

async function ill_edit_supplier_parts(frm) {
	if (!ill_parts_suppliers(frm).length) {
		frappe.msgprint(__('Choose a supplier first.'));
		return;
	}
	const lines = ill_item_lines(frm);
	const codes = Object.keys(lines);
	if (!codes.length) {
		frappe.msgprint(__('Add items first.'));
		return;
	}
	const supplier = await ill_choose_parts_supplier(frm);
	if (!supplier) return;
	const lineSupplier = ill_line_supplier(frm) === supplier;
	const info = await ill_fetch_supplier_parts(frm, supplier, codes);
	const esc = frappe.utils.escape_html;
	const label = ill_supplier_label(frm, supplier);

	const fields = [{
		fieldtype: 'HTML',
		fieldname: 'intro',
		options: `<p class="text-muted">${esc(__('Saved on each item for {0}, and used on purchase orders and RFQs to them.', [label]))}</p>`,
	}];
	codes.forEach((code, i) => {
		const line = lines[code];
		const saved = info.items[code] || {};
		const name = line.item_name && line.item_name !== code ? ` · ${line.item_name}` : '';
		// The line's unsaved edits lead when the lines carry this supplier's values.
		const part = lineSupplier && line.supplier_part_no ? line.supplier_part_no : saved.supplier_part_no;
		const desc = lineSupplier && line[ILL_LINE_DESCRIPTION] ? line[ILL_LINE_DESCRIPTION] : saved.supplier_description;
		fields.push(
			{fieldtype: 'Section Break', label: `${code}${name}`},
			{fieldtype: 'Data', fieldname: `part_${i}`, label: __('Supplier Part Number'), default: part || ''},
		);
		if (info.has_description) {
			fields.push(
				{fieldtype: 'Column Break'},
				{fieldtype: 'Small Text', fieldname: `desc_${i}`, label: __('Supplier Description'), default: desc || ''},
			);
		}
	});

	const dialog = new frappe.ui.Dialog({
		title: __('Supplier Parts for {0}', [label]),
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
				method: `${ILL_SUPPLIER_PARTS_API}.update_supplier_part_info`,
				args: {supplier, rows, doctype: frm.doctype, name: frm.is_new() ? null : frm.doc.name},
				freeze: true,
				freeze_message: __('Saving supplier parts'),
			});
			dialog.hide();
			const message = result.message || {};
			const saved = message.updated || [];
			if (frm.doc.docstatus === 0 && lineSupplier) {
				// Draft lines carry the values too; they save with the document.
				const byCode = Object.fromEntries(rows.map(row => [row.item_code, row]));
				let touched = false;
				for (const row of frm.doc.items || []) {
					const want = byCode[row.item_code];
					if (!want) continue;
					if ((row.supplier_part_no || '') !== want.supplier_part_no) {
						frappe.model.set_value(row.doctype, row.name, 'supplier_part_no', want.supplier_part_no);
						touched = true;
					}
					if (info.has_description && (row[ILL_LINE_DESCRIPTION] || '') !== want.supplier_description) {
						frappe.model.set_value(row.doctype, row.name, ILL_LINE_DESCRIPTION, want.supplier_description);
						touched = true;
					}
				}
				frm.refresh_field('items');
				if (touched) {
					frappe.show_alert({message: __('Items updated. Save to keep the values on the lines.'), indicator: 'blue'}, 7);
					return;
				}
			} else if ((message.lines || []).length) {
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

function ill_supplier_parts_refresh(frm) {
	frm.__ill_parts_supplier = ill_line_supplier(frm);
	// Saving writes to the Items, so it needs edit rights on both.
	if (frm.doc.docstatus === 2 || !frappe.model.can_write(frm.doctype) || !frappe.model.can_write('Item')) return;
	frm.add_custom_button(__('Supplier Parts'), () => ill_edit_supplier_parts(frm));
}

function ill_line_item_changed(frm, cdt, cdn) {
	// ERPNext fills the line's item details first; fill whatever it left blank.
	setTimeout(() => ill_fill_lines(frm, [locals[cdt][cdn]], false), 300);
}

frappe.ui.form.on('Purchase Order', {
	refresh: ill_supplier_parts_refresh,
	supplier: ill_line_supplier_changed,
});
frappe.ui.form.on('Purchase Order Item', {item_code: ill_line_item_changed});

frappe.ui.form.on('Request for Quotation', {
	refresh: ill_supplier_parts_refresh,
	suppliers_remove: ill_line_supplier_changed,
});
frappe.ui.form.on('Request for Quotation Supplier', {supplier: frm => ill_line_supplier_changed(frm)});
frappe.ui.form.on('Request for Quotation Item', {item_code: ill_line_item_changed});
