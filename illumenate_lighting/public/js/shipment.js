// EasyPost labels on the native Shipment (api/shipping.py, docs/SHIPPING_EASYPOST_INTEGRATION.md).
// Create Labels rates the boxes first and buys only after the user confirms the rate.
(() => {
	const API = "illumenate_lighting.illumenate_lighting.api.shipping.";
	const esc = (value) => frappe.utils.escape_html(String(value == null ? "" : value));

	frappe.ui.form.on("Shipment", {
		refresh(frm) {
			show_intro(frm);
			if (frm.doc.docstatus !== 1 || !frm.perm[0] || !frm.perm[0].submit) return;
			const status = frm.doc.ill_label_status || "Not bought";
			if (status === "Bought") {
				if (frm.doc.ill_label_url) {
					frm.add_custom_button(__("Print Labels"), () => window.open(frm.doc.ill_label_url, "_blank"));
				}
				frm.add_custom_button(__("Void Label"), () => void_labels(frm));
			} else {
				frm.add_custom_button(__("Create Labels"), () => quote_labels(frm)).addClass("btn-primary");
			}
		},
	});

	function show_intro(frm) {
		frm.set_intro("");
		if (frm.doc.docstatus === 0) {
			frm.set_intro(
				__("Dimensions are in inches and weight in pounds. A row with Count above 1 becomes one row per box when you save, so each box gets its own label. Submit, then Create Labels."),
				"blue"
			);
		} else if (frm.doc.ill_label_status === "Error" && frm.doc.ill_label_message) {
			frm.set_intro(__("Label error: {0}", [esc(frm.doc.ill_label_message)]), "red");
		}
	}

	function quote_labels(frm) {
		frappe
			.call({
				method: API + "quote_labels",
				args: { shipment: frm.doc.name },
				freeze: true,
				freeze_message: __("Getting the rate from EasyPost..."),
			})
			.then((r) => {
				const result = r.message || {};
				if (!result.ok) {
					frappe.msgprint({ title: __("Could not rate this shipment"), message: esc(result.message), indicator: "red" });
					frm.reload_doc();
					return;
				}
				confirm_purchase(frm, result);
			});
	}

	function confirm_purchase(frm, result) {
		const rate = result.rate || {};
		const address = result.address || {};
		const amount = format_currency(rate.amount, rate.currency || "USD");
		const rows = [
			[__("Service"), `${esc(rate.carrier)} ${esc(rate.service)}`],
			[__("Rate"), `<strong>${esc(amount)}</strong>`],
			[__("Boxes"), esc(result.boxes)],
			[__("Transit"), rate.delivery_days ? __("{0} business days", [esc(rate.delivery_days)]) : "-"],
			[
				__("Address"),
				address.verified
					? __("Verified") + (address.residential ? " · " + __("residential") : "")
					: `<span class="text-danger">${__("Not verified")}</span>`,
			],
		];
		let html = `<table class="table table-condensed">${rows
			.map(([label, value]) => `<tr><td class="text-muted">${label}</td><td>${value}</td></tr>`)
			.join("")}</table>`;
		const flags = result.flags || [];
		if (flags.length) {
			html += `<div class="alert alert-warning"><strong>${__("Surcharges likely")}</strong><br>${flags.map(esc).join("<br>")}</div>`;
		}
		const notes = [...(address.messages || []), ...(result.messages || [])].filter((m) => typeof m === "string");
		if (notes.length) html += `<p class="text-muted small">${notes.map(esc).join("<br>")}</p>`;

		const dialog = new frappe.ui.Dialog({
			title: __("Buy FedEx labels for {0}?", [frm.doc.name]),
			fields: [{ fieldtype: "HTML", options: html }],
			primary_action_label: __("Buy Labels ({0})", [amount]),
			primary_action() {
				dialog.disable_primary_action();
				buy_labels(frm, result, dialog);
			},
		});
		dialog.show();
	}

	function buy_labels(frm, quote, dialog) {
		frappe
			.call({
				method: API + "buy_labels",
				args: { shipment: frm.doc.name, easypost_id: quote.easypost_id, service: (quote.rate || {}).service },
				freeze: true,
				freeze_message: __("Buying labels..."),
			})
			.then((r) => {
				dialog.hide();
				const result = r.message || {};
				if (!result.ok) {
					frappe.msgprint({ title: __("Labels were not bought"), message: esc(result.message), indicator: "red" });
				} else {
					frappe.show_alert({ message: __("Labels bought. Tracking {0}", [result.tracking_number]), indicator: "green" });
					if (result.label_url) window.open(result.label_url, "_blank");
				}
				frm.reload_doc();
			})
			.catch(() => {
				dialog.hide();
				frm.reload_doc();
			});
	}

	function void_labels(frm) {
		frappe.confirm(
			__("Void the labels on {0} and ask EasyPost for a refund? The tracking numbers will be removed from the Delivery Note.", [frm.doc.name]),
			() =>
				frappe
					.call({ method: API + "void_labels", args: { shipment: frm.doc.name }, freeze: true, freeze_message: __("Voiding...") })
					.then((r) => {
						const result = r.message || {};
						if (result.ok) {
							frappe.show_alert({ message: __("Labels voided"), indicator: "orange" });
						} else {
							frappe.msgprint({ title: __("Could not void"), message: esc(result.message), indicator: "red" });
						}
						frm.reload_doc();
					})
		);
	}
})();
