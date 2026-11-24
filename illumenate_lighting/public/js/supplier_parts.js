// ilLumenate Lighting - supplier part numbers and descriptions on Purchase Orders and RFQs.
// The values live on the Item (Supplier Items table, one row per supplier); see
// api/supplier_parts.py. Each line shows Supplier Part Number and Supplier Description:
// picking an item or a supplier fills them from the Item, and saving the document writes
// changed values back to the Item. The "Supplier Parts" button edits every line at once,
// and on an RFQ with several suppliers it is how the values are set, one supplier at a time.
//
// The same button is on Material Requests, Quotations, Sales Orders and the other documents in
// ILL_ITEM_ONLY_DOCTYPES. Their lines carry no supplier values, so the dialog edits the Items
// only: for the document's own supplier when it has one, or else for a supplier the user picks
// (the suppliers already set on those items are suggested).

const ILL_SUPPLIER_PARTS_API = 'illumenate_lighting.illumenate_lighting.api.supplier_parts';
const ILL_LINE_DESCRIPTION = 'ill_supplier_description';
// Keep in step with ITEM_ONLY_DOCTYPES in api/supplier_parts.py and the list in hooks.py.
const ILL_ITEM_ONLY_DOCTYPES = [
	'Material Request', 'Quotation', 'Sales Order',
	'Supplier Quotation', 'Purchase Receipt', 'Purchase Invoice',
];

function ill_item_only(frm) {
	return ILL_ITEM_ONLY_DOCTYPES.includes(frm.doctype);
}

// The suppliers this document deals with: the PO's supplier, or the RFQ's suppliers.
function ill_parts_suppliers(frm) {
	if (frm.doctype === 'Request for Quotation') {
		return [...new Set((frm.doc.suppliers || []).map(row => row.supplier).filter(Boolean))];
	}
	return frm.doc.supplier ? [frm.doc.supplier] : [];
}

// The one supplier the lines carry values for, or null (an RFQ with several suppliers, or a
// document whose lines carry no supplier values).
function ill_line_supplier(frm) {
	if (ill_item_only(frm)) return null;
	const suppliers = ill_parts_suppliers(frm);
	return suppliers.length === 1 ? suppliers[0] : null;
}

function ill_supplier_label(frm, supplier, info) {
	if (frm.doc.supplier === supplier && frm.doc.supplier_name) return frm.doc.supplier_name;
	const row = (frm.doc.suppliers || []).find(r => r.supplier === supplier);
	return (row && row.supplier_name) || (info && info.supplier_name) || supplier;
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

// A document without a supplier of its own (Sales Order, Quotation, Material Request): ask
// for one, offering the suppliers already set on its items. A Sales Order's drop-ship
// supplier, when its lines name exactly one, comes first.
async function ill_choose_any_supplier(frm, codes) {
	const response = await frappe.call({
		method: `${ILL_SUPPLIER_PARTS_API}.get_item_suppliers`,
		args: {item_codes: codes, doctype: frm.doctype},
	});
	const known = response.message || [];
	const dropShip = [...new Set((frm.doc.items || []).map(row => row.supplier).filter(Boolean))];
	const suggested = dropShip.length === 1 ? dropShip[0] : (known[0] && known[0].supplier);
	const esc = frappe.utils.escape_html;
	const hint = known.length
		? __('Already set on these items: {0}', [known.slice(0, 8).map(entry =>
			`${esc(entry.supplier_name)} (${entry.items})`).join(', ')])
		: __('None of these items has a supplier yet. Pick one to add it.');
	return new Promise(resolve => {
		const dialog = new frappe.ui.Dialog({
			title: __('Supplier Parts for which supplier?'),
			fields: [
				{fieldtype: 'Link', fieldname: 'supplier', options: 'Supplier', label: __('Supplier'),
					reqd: 1, default: suggested || '', description: hint},
				...(known.length > 1 ? [{fieldtype: 'HTML', fieldname: 'known'}] : []),
			],
			primary_action_label: __('Next'),
			primary_action(values) {
				dialog.__ill_chosen = true;
				dialog.hide();
				resolve(values.supplier);
			},
		});
		dialog.onhide = () => { if (!dialog.__ill_chosen) resolve(null); };
		if (known.length > 1) {
			// One click picks a supplier already on these items.
			const wrapper = dialog.fields_dict.known.$wrapper;
			wrapper.html(known.slice(0, 8).map(entry =>
				`<button type="button" class="btn btn-xs btn-default" style="margin: 0 6px 6px 0"
					data-supplier="${esc(entry.supplier)}">${esc(entry.supplier_name)}</button>`).join(''));
			wrapper.on('click', 'button[data-supplier]', event => {
				dialog.set_value('supplier', event.currentTarget.dataset.supplier);
			});
		}
		dialog.show();
	});
}

async function ill_choose_parts_supplier(frm, codes) {
	const suppliers = ill_parts_suppliers(frm);
	if (!suppliers.length && ill_item_only(frm)) return ill_choose_any_supplier(frm, codes);
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
	if (!ill_item_only(frm) && !ill_parts_suppliers(frm).length) {
		frappe.msgprint(__('Choose a supplier first.'));
		return;
	}
	const lines = ill_item_lines(frm);
	const codes = Object.keys(lines);
	if (!codes.length) {
		frappe.msgprint(__('Add items first.'));
		return;
	}
	const supplier = await ill_choose_parts_supplier(frm, codes);
	if (!supplier) return;
	const lineSupplier = ill_line_supplier(frm) === supplier;
	const info = await ill_fetch_supplier_parts(frm, supplier, codes);
	const esc = frappe.utils.escape_html;
	const label = ill_supplier_label(frm, supplier, info);

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
	// Saving writes to the Items, so it needs edit rights on them, and on a PO / RFQ (whose
	// lines it also sets) on the document too.
	if (frm.doc.docstatus === 2 || !frappe.model.can_write('Item')) return;
	if (!ill_item_only(frm) && !frappe.model.can_write(frm.doctype)) return;
	frm.add_custom_button(__('Supplier Parts'), () => ill_edit_supplier_parts(frm));
}

function ill_line_item_changed(frm, cdt, cdn) {
	// ERPNext fills the line's item details first; fill whatever it left blank.
	setTimeout(() => ill_fill_lines(frm, [locals[cdt][cdn]], false), 300);
}

// Loaded as the form script of every doctype above; register the handlers once.
if (!window.illumenate_supplier_parts_loaded) {
	window.illumenate_supplier_parts_loaded = true;
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

	for (const doctype of ILL_ITEM_ONLY_DOCTYPES) {
		frappe.ui.form.on(doctype, {refresh: ill_supplier_parts_refresh});
	}
}
