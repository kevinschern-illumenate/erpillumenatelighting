// ilLumenate Lighting - spec and load under catalog LED Tape / Neon / Sheet rows.
//
// The server stamps ill_lp_* on every save (api/line_power.py). This script previews the
// same values while rows are edited, and draws the "Tape / Neon / Sheet Power" panel
// under the Items grid from the row values.

(function () {
	// Loaded as a form script for both doctypes; register the handlers once.
	if (window.illumenate_line_power_loaded) {
		return;
	}
	window.illumenate_line_power_loaded = true;
	const CHILD ={ 'Quotation': 'Quotation Item', 'Sales Order': 'Sales Order Item' };
	const PREVIEW = 'illumenate_lighting.illumenate_lighting.api.line_power.preview';
	const MISSING = 'illumenate_lighting.illumenate_lighting.api.line_power.missing_specs';
	const SENT = [
		'item_code', 'qty', 'uom', 'conversion_factor', 'stock_uom', 'is_alternative',
		'ill_is_power_supply_line', 'ill_configured_fixture', 'ill_configured_tape_neon',
		'ill_configured_led_sheet', 'ill_configured_group', 'ill_configured_product'
	];
	const timers = {};

	function esc(value) {
		return frappe.utils.escape_html(value === undefined || value === null ? '' : String(value));
	}

	// 864 → "864", 2.74 → "2.74"; with digits, fixed (72 → "72.00").
	function num(value, digits) {
		if (value === undefined || value === null || value === '') {
			return '';
		}
		const n = Number(value);
		return digits === undefined ? String(Math.round(n * 10000) / 10000) : n.toFixed(digits);
	}

	function payload(frm) {
		return (frm.doc.items || []).filter(row => row.item_code).map(row => {
			const out = { key: row.name };
			SENT.forEach(field => { out[field] = row[field]; });
			return out;
		});
	}

	function apply(frm, result) {
		const values = (result && result.rows) || {};
		let changed = false;
		(frm.doc.items || []).forEach(row => {
			const next = values[row.name];
			if (!next) {
				return;
			}
			Object.keys(next).forEach(field => {
				if ((row[field] || null) !== (next[field] || null)) {
					row[field] = next[field];
					changed = true;
				}
			});
		});
		if (changed) {
			frm.refresh_field('items');
		}
		render_panel(frm);
	}

	// Debounced per form: ERPNext sets conversion_factor a moment after a UOM change.
	function refresh_preview(frm) {
		if (!frm || frm.doc.docstatus !== 0) {
			return;
		}
		clearTimeout(timers[frm.doc.name]);
		timers[frm.doc.name] = setTimeout(() => {
			const rows = payload(frm);
			if (!rows.length) {
				render_panel(frm);
				return;
			}
			frappe.call({ method: PREVIEW, args: { rows: rows }, type: 'POST' })
				.then(r => apply(frm, r && r.message));
		}, 400);
	}

	function render_panel(frm) {
		const field = frm.fields_dict && frm.fields_dict.ill_lp_panel;
		if (!field) {
			return;
		}
		const rows = (frm.doc.items || []).filter(row => row.ill_lp_summary || row.ill_lp_note);
		frm.toggle_display('ill_lp_panel', rows.length > 0);
		if (!rows.length) {
			field.$wrapper.empty();
			return;
		}
		let total = 0;
		const body = rows.map(row => {
			if (!row.is_alternative) {
				total += flt(row.ill_lp_watts);
			}
			const size = row.ill_lp_family === 'Sheet'
				? (row.ill_lp_area_sqft ? `${num(row.ill_lp_area_sqft, 2)} sq ft` : '')
				: (row.ill_lp_length_ft ? `${num(row.ill_lp_length_ft, 2)} ft` : '');
			const rate = row.ill_lp_family === 'Sheet'
				? (row.ill_lp_watts_per_sqft ? `${num(row.ill_lp_watts_per_sqft)} W/sq ft` : '')
				: (row.ill_lp_watts_per_ft ? `${num(row.ill_lp_watts_per_ft)} W/ft` : '');
			const note = row.ill_lp_note
				? `<div class="text-muted small"><span class="indicator-pill orange">${esc(row.ill_lp_note)}</span></div>` : '';
			return `<tr>
				<td>${esc(row.idx)}</td>
				<td>${esc(row.ill_fixture_type || '')}</td>
				<td>${esc(row.item_code)}${note}</td>
				<td class="text-right">${esc(num(row.qty))} ${esc(row.uom || '')}</td>
				<td>${esc(row.ill_lp_input_voltage || '')}</td>
				<td class="text-right">${esc(size)}</td>
				<td class="text-right">${esc(rate)}</td>
				<td class="text-right">${esc(row.ill_lp_max_run_ft ? num(row.ill_lp_max_run_ft) + ' ft' : '')}</td>
				<td class="text-right">${row.ill_lp_watts || row.ill_lp_watts === 0 ? esc(num(row.ill_lp_watts, 1)) + ' W' : ''}</td>
			</tr>`;
		}).join('');
		field.$wrapper.html(`
			<div class="ill-lp-panel" style="margin-top: var(--margin-sm, 8px);">
				<div class="text-muted small" style="margin-bottom: 4px;">${__('Tape / Neon / Sheet Power')}</div>
				<table class="table table-bordered table-sm" style="margin-bottom: 0; font-size: var(--text-sm, 12px);">
					<thead><tr>
						<th>#</th><th>${__('Fixture Type')}</th><th>${__('Item')}</th>
						<th class="text-right">${__('Qty')}</th><th>${__('Voltage')}</th>
						<th class="text-right">${__('Length / Area')}</th><th class="text-right">${__('Rating')}</th>
						<th class="text-right">${__('Max Run')}</th><th class="text-right">${__('Load')}</th>
					</tr></thead>
					<tbody>${body}</tbody>
					<tfoot><tr>
						<td colspan="8" class="text-right"><b>${__('Total connected load')}</b></td>
						<td class="text-right"><b>${esc(num(total, 1))} W</b></td>
					</tr></tfoot>
				</table>
			</div>`);
	}

	function show_missing_specs() {
		frappe.call({ method: MISSING, freeze: true }).then(r => {
			const items = (r && r.message) || [];
			const rows = items.map(item => `<tr>
				<td><a href="/app/item/${encodeURIComponent(item.name)}">${esc(item.name)}</a></td>
				<td>${esc(item.item_name)}</td><td>${esc(item.item_group)}</td><td>${esc(item.variant_of || '')}</td>
			</tr>`).join('');
			frappe.msgprint({
				title: __('{0} LED Item(s) Missing a Spec', [items.length]),
				wide: true,
				message: items.length
					? `<p class="text-muted">${__('These sellable Items have no ilL-Spec-LED Tape or ilL-Spec-LED-Sheet record, on themselves or their template, so quotes show no voltage, run length or load for them.')}</p>
						<table class="table table-bordered table-sm"><thead><tr><th>${__('Item')}</th><th>${__('Name')}</th>
						<th>${__('Group')}</th><th>${__('Template')}</th></tr></thead><tbody>${rows}</tbody></table>`
					: __('Every sellable LED Tape, Neon and Sheet Item has a spec.')
			});
		});
	}

	Object.keys(CHILD).forEach(parent => {
		frappe.ui.form.on(parent, {
			refresh(frm) {
				render_panel(frm);
				if (parent === 'Quotation' && frappe.user.has_role('System Manager')) {
					frm.add_custom_button(__('Tape Items Missing Spec'), show_missing_specs, __('Tools'));
				}
			},
			items_remove(frm) { refresh_preview(frm); }
		});
		frappe.ui.form.on(CHILD[parent], {
			item_code(frm) { refresh_preview(frm); },
			qty(frm) { refresh_preview(frm); },
			uom(frm) { refresh_preview(frm); },
			conversion_factor(frm) { refresh_preview(frm); },
			items_remove(frm) { refresh_preview(frm); }
		});
	});
})();
