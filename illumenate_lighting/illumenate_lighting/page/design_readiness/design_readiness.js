// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

// System Designer readiness (WP-1.7): catalog records the designer cannot use yet, the ERP fields to
// fill, and how many recent schedule lines use each one.
frappe.pages['design-readiness'].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({parent: wrapper, title: __('Design Readiness'), single_column: true});
	const type = page.add_field({fieldname: 'product_type', label: __('Product type'), fieldtype: 'Select',
		options: ['', 'Tape', 'Driver', 'Controller', 'Wire'].join('\n'), change: load});
	const incomplete = page.add_field({fieldname: 'only_incomplete', label: __('Only incomplete'), fieldtype: 'Check', default: 1, change: load});
	page.set_primary_action(__('Refresh'), load, 'refresh');
	const container = document.createElement('div'); container.className = 'p-3'; page.main[0].append(container);
	const status = document.createElement('p'); status.setAttribute('role', 'status');
	const table = document.createElement('div'); table.className = 'table-responsive';
	container.append(status, table);
	let version = 0;
	const deskUrl = (doctype, name) => `/app/${doctype.toLowerCase().replace(/[^a-z0-9]+/g, '-')}/${encodeURIComponent(name)}`;
	const statusColor = {'ready': 'green', 'incomplete': 'orange', 'not modelled': 'gray'};

	async function load() {
		const request = ++version; status.textContent = __('Loading…');
		try {
			const r = await frappe.call({method: 'illumenate_lighting.illumenate_lighting.system_design.readiness.get_report', type: 'GET',
				args: {product_type: type.get_value() || '', only_incomplete: incomplete.get_value() ? 1 : 0}});
			if (request !== version) return;
			const data = r.message; table.replaceChildren();
			status.textContent = __('{0} of {1} records are incomplete. Volume counts schedule lines from the last {2} days.',
				[data.summary.incomplete, data.summary.total, data.volume_days]);
			const grid = document.createElement('table'); grid.className = 'table table-bordered table-sm';
			const head = document.createElement('tr');
			[__('Type'), __('Record'), __('Status'), __('Fields to fill'), __('Notes'), __('Volume')].forEach(text => {
				const th = document.createElement('th'); th.textContent = text; head.append(th);
			});
			const thead = document.createElement('thead'); thead.append(head); grid.append(thead);
			const tbody = document.createElement('tbody');
			data.rows.forEach(row => {
				const tr = document.createElement('tr');
				const cell = (text) => { const td = document.createElement('td'); td.textContent = text; tr.append(td); return td; };
				cell(row.product_type);
				const link = document.createElement('a'); link.href = deskUrl(row.doctype, row.name); link.textContent = row.label;
				const record = document.createElement('td'); record.append(link); tr.append(record);
				const pill = document.createElement('span'); pill.className = `indicator-pill ${statusColor[row.status] || 'gray'}`; pill.textContent = row.status;
				const state = document.createElement('td'); state.append(pill); tr.append(state);
				cell(row.missing.join(', ') || '—');
				cell(row.notes.join('; ') || '—');
				cell(String(row.volume));
				tbody.append(tr);
			});
			grid.append(tbody); table.append(grid);
			if (!data.rows.length) status.textContent += ' ' + __('Nothing to show for this filter.');
		} catch (error) {
			if (request === version) { table.replaceChildren(); status.textContent = __('Readiness is unavailable. Check your role or retry.'); }
		}
	}
	load();
};
