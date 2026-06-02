/**
 * Shim for window.illumenate_lighting.quote_order_configurator.
 *
 * The old simple "Configure Product" Tools dialog (existing-record picker
 * only) has been replaced by the embedded "Configure & Add Fixture" dialog
 * in public/js/desk/desk_dialog.js, which mounts the scoped portal
 * configurator classes inside a Quotation / Sales Order modal.
 *
 * That module is loaded globally via hooks.py (app_include_js). This shim
 * preserves the old API surface so quotation.js / sales_order.js can keep
 * calling configurator.add_buttons(frm) / configurator.show_dialog(frm)
 * without changes.
 */
(function () {
	var ns = window.illumenate_lighting = window.illumenate_lighting || {};

	function add_buttons(frm) {
		if (window.IllDesk && typeof window.IllDesk.addConfiguratorButton === 'function') {
			window.IllDesk.addConfiguratorButton(frm);
		} else {
			console.warn('[illumenate_lighting] IllDesk.addConfiguratorButton not loaded; check hooks.py app_include_js order.');
		}
	}

	function show_dialog(frm) {
		if (window.IllDesk && typeof window.IllDesk.openConfiguratorDialog === 'function') {
			window.IllDesk.openConfiguratorDialog(frm);
		} else {
			console.warn('[illumenate_lighting] IllDesk.openConfiguratorDialog not loaded; check hooks.py app_include_js order.');
		}
	}

	ns.quote_order_configurator = {
		add_buttons: add_buttons,
		show_dialog: show_dialog
	};
})();
