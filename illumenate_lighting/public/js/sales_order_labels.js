// Labels on the Sales Order (labels plan Phase 1, api/labels.py): open the print station filtered
// to this order, or make labels for all of its work orders now. Hidden while labels are off.
(() => {
	const API = "illumenate_lighting.illumenate_lighting.api.labels.";
	const GROUP = __("Labels");

	frappe.ui.form.on("Sales Order", {
		refresh(frm) {
			if (frm.is_new() || frm.doc.docstatus !== 1) return;
			frappe
				.call({ method: API + "get_document_labels", args: { doctype: "Sales Order", name: frm.doc.name } })
				.then((r) => {
					const data = r.message;
					if (!data || !data.enabled) return;
					const queued = (data.counts || {}).Queued || 0;
					if (queued) frm.dashboard.add_indicator(__("{0} labels queued", [queued]), "blue");
					frm.add_custom_button(
						__("Open label queue"),
						() => window.open(`/command-center#mfg?labels_so=${encodeURIComponent(frm.doc.name)}`, "_blank"),
						GROUP
					);
					frm.add_custom_button(
						__("Generate labels"),
						() =>
							frappe
								.call({ method: API + "generate", args: { doctype: "Sales Order", name: frm.doc.name } })
								.then((res) => {
									const made = Object.keys((res.message || {})["Work Order"] || {}).length;
									frappe.show_alert({ message: __("Labels updated for {0} work orders", [made]), indicator: "green" });
									frm.reload_doc();
								}),
						GROUP
					);
				})
				.catch(() => {});
		},
	});
})();
