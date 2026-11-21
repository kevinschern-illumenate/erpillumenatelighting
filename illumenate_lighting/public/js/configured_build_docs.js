// "Configure & Add Fixture" on purchasing and manufacturing documents.
//
// Purchase Order, Request for Quotation and Material Request get the same
// dialog as Quotation / Sales Order, document-only (no fixture schedule): the
// build's Item, BOM or Product Bundle are created and the Item is added as a
// row. A Work Order gets "Configure Production Item", which sets its
// production Item, BOM and quantity. The dialog itself is
// public/js/desk/dialog/*.js (illumenate_desk.bundle.js, loaded on every Desk page).
(function () {
	['Purchase Order', 'Request for Quotation', 'Material Request', 'Work Order'].forEach(function (doctype) {
		frappe.ui.form.on(doctype, {
			refresh: function (frm) {
				if (window.IllDesk && typeof window.IllDesk.addConfiguratorButton === 'function') {
					window.IllDesk.addConfiguratorButton(frm);
				}
			}
		});
	});
})();
