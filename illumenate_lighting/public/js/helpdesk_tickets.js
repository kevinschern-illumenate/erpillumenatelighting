// ilLumenate Lighting - link Helpdesk tickets to a Quotation, Sales Order or Sales Invoice.
// The link is stored on the ticket (ill_quotation / ill_sales_order / ill_sales_invoice)
// so Helpdesk email templates can read it; linked tickets show under Connections.

(function () {
	const FIELDS = {
		"Quotation": "ill_quotation",
		"Sales Order": "ill_sales_order",
		"Sales Invoice": "ill_sales_invoice",
	};

	function helpdesk_installed() {
		return (frappe.boot.versions || {}).helpdesk !== undefined;
	}

	function pick_tickets(frm) {
		const fieldname = FIELDS[frm.doctype];
		new frappe.ui.form.MultiSelectDialog({
			doctype: "HD Ticket",
			target: frm,
			setters: { status: null },
			add_filters_group: 1,
			columns: ["subject", "raised_by", "status"],
			get_query() {
				return { filters: [["HD Ticket", fieldname, "!=", frm.doc.name]] };
			},
			action(selections) {
				if (!selections || !selections.length) {
					frappe.msgprint(__("Select at least one ticket."));
					return;
				}
				frappe.call({
					method: "illumenate_lighting.illumenate_lighting.helpdesk_links.link_tickets",
					args: { doctype: frm.doctype, name: frm.doc.name, tickets: selections },
					freeze: true,
					callback(r) {
						cur_dialog && cur_dialog.hide();
						frappe.show_alert({
							message: __("Linked {0} ticket(s)", [(r.message || []).length]),
							indicator: "green",
						});
						frm.reload_doc();
					},
				});
			},
		});
	}

	const handlers = {
		refresh(frm) {
			if (frm.is_new() || !helpdesk_installed()) return;
			frm.add_custom_button(__("Link Helpdesk Tickets"), () => pick_tickets(frm), __("Support"));
		},
	};

	Object.keys(FIELDS).forEach((doctype) => frappe.ui.form.on(doctype, handlers));
})();
