// Create Shipment on a Delivery Note (api/shipping.py make_shipment).
// Opens the Shipment that already lists this note, or a new one with the defaults filled in.
frappe.ui.form.on("Delivery Note", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.docstatus === 2 || frm.doc.is_return) return;
		if (!frappe.model.can_create("Shipment")) return;
		frm.add_custom_button(__("Create Shipment"), () => ill_create_shipment(frm));
	},
});

function ill_create_shipment(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint(__("Save the Delivery Note first."));
		return;
	}
	frappe
		.call({
			method: "illumenate_lighting.illumenate_lighting.api.shipping.make_shipment",
			args: { delivery_note: frm.doc.name },
			freeze: true,
		})
		.then((r) => {
			const result = r.message || {};
			if (result.existing) {
				frappe.show_alert({ message: __("Opening {0}, which already lists this note.", [result.existing]), indicator: "blue" });
				frappe.set_route("Form", "Shipment", result.existing);
				return;
			}
			const doc = frappe.model.sync(result.doc)[0];
			frappe.set_route("Form", doc.doctype, doc.name);
		});
}
