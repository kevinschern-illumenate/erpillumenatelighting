// Labels on the Work Order (labels plan Phase 1, api/labels.py): print this work order's packet,
// regenerate it, or preview a template. Two printers: the Dymo keeps 1.5 x 2.5 loaded and the
// Rollo keeps 4 x 6, so each roll prints as its own batch. Hidden while labels are off.
(() => {
	const API = "illumenate_lighting.illumenate_lighting.api.labels.";
	const GROUP = __("Labels");

	const call = (method, args) => frappe.call({ method: API + method, args }).then((r) => r.message);

	function printPdf(url) {
		// A hidden iframe keeps the operator on the form; a blocked print falls back to a tab.
		const frame = document.createElement("iframe");
		frame.style.cssText = "position:fixed;width:0;height:0;border:0;right:0;bottom:0;";
		frame.onload = () => {
			try {
				frame.contentWindow.focus();
				frame.contentWindow.print();
			} catch (e) {
				window.open(url, "_blank");
				frappe.show_alert({ message: __("Press Ctrl+P to print"), indicator: "orange" });
			}
			setTimeout(() => frame.remove(), 60000);
		};
		frame.src = url;
		document.body.appendChild(frame);
	}

	function confirmBatch(frm, batch, jobs) {
		const d = new frappe.ui.Dialog({
			title: __("Did every label print correctly?"),
			fields: [
				{
					fieldname: "reprint",
					fieldtype: "MultiCheck",
					label: __("Tick only the labels that need reprinting"),
					options: jobs.map((j) => ({ label: j.summary || j.name, value: j.name })),
					columns: 1,
				},
			],
			primary_action_label: __("Confirm"),
			primary_action(values) {
				const reprint = values.reprint || [];
				call("confirm_batch", { batch, reprint_jobs: JSON.stringify(reprint) }).then((r) => {
					d.hide();
					frappe.show_alert({
						message: __("{0} printed, {1} back in the queue", [r.printed, r.requeued]),
						indicator: "green",
					});
					frm.reload_doc();
				});
			},
		});
		d.show();
	}

	function printGroup(frm, stock, jobs) {
		call("create_batch", { label_stock: stock.name, job_names: JSON.stringify(jobs.map((j) => j.name)) }).then((r) => {
			const paper = r.driver_paper_name || stock.name;
			frappe.msgprint({
				title: __("Printing {0} labels", [r.count]),
				indicator: "blue",
				message: __("Printer: <b>{0}</b>. Paper: <b>{1}</b>. Margins: none. Scale: 100%.", [
					frappe.utils.escape_html(r.printer_name || stock.printer_name || ""),
					frappe.utils.escape_html(paper),
				]),
				primary_action: {
					label: __("Printed: confirm"),
					action() {
						frappe.hide_msgprint();
						confirmBatch(frm, r.batch, jobs);
					},
				},
			});
			printPdf(r.pdf_url);
		});
	}

	function showDialog(frm, data) {
		const queued = data.jobs.filter((j) => j.status === "Queued");
		const byStock = {};
		queued.forEach((j) => (byStock[j.label_stock] = byStock[j.label_stock] || []).push(j));
		const stocks = Object.keys(byStock).sort((a, b) => (data.stocks[a].print_order || 0) - (data.stocks[b].print_order || 0));
		const rows = stocks
			.map(
				(s) =>
					`<div class="flex justify-between align-center" style="padding:8px 0;border-bottom:1px solid var(--border-color)">
						<div><b>${frappe.utils.escape_html(data.stocks[s].printer_name || s)}</b> · ${frappe.utils.escape_html(s)}
						<div class="text-muted small">${byStock[s].length} ${__("labels queued")}</div></div>
						<button class="btn btn-primary btn-sm" data-stock="${frappe.utils.escape_html(s)}">${__("Print")}</button></div>`
			)
			.join("");
		const d = new frappe.ui.Dialog({
			title: __("Labels for {0}", [frm.doc.name]),
			fields: [{ fieldtype: "HTML", fieldname: "body" }],
		});
		d.fields_dict.body.$wrapper.html(
			rows ||
				`<p class="text-muted">${__("Nothing queued for this work order.")} ${__(
					"Use Regenerate, or Reprint from the label list."
				)}</p>`
		);
		d.fields_dict.body.$wrapper.find("button[data-stock]").on("click", (e) => {
			const s = e.currentTarget.dataset.stock;
			d.hide();
			printGroup(frm, { name: s, ...data.stocks[s] }, byStock[s]);
		});
		d.show();
	}

	function previewTemplate(frm) {
		frappe.db.get_list("ilL-Label-Template", { filters: { enabled: 1, source_doctype: "Work Order" }, pluck: "name" }).then((names) => {
			frappe.prompt(
				[{ fieldname: "template", fieldtype: "Select", label: __("Template"), options: names, reqd: 1 }],
				(v) =>
					window.open(
						`/api/method/${API}preview?template=${encodeURIComponent(v.template)}&name=${encodeURIComponent(frm.doc.name)}`,
						"_blank"
					),
				__("Preview a label"),
				__("Open PDF")
			);
		});
	}

	frappe.ui.form.on("Work Order", {
		refresh(frm) {
			if (frm.is_new() || frm.doc.docstatus === 2) return;
			call("get_document_labels", { doctype: "Work Order", name: frm.doc.name })
				.then((data) => {
					if (!data || !data.enabled) return;
					const c = data.counts || {};
					if (c.Queued) frm.dashboard.add_indicator(__("{0} labels queued", [c.Queued]), "blue");
					else if (c.Printed) frm.dashboard.add_indicator(__("All labels printed"), "green");
					if (data.jobs.some((j) => j.is_stale && j.status === "Printed"))
						frm.dashboard.add_indicator(__("Labels changed since printing"), "orange");
					frm.add_custom_button(__("Print labels"), () => showDialog(frm, data), GROUP);
					frm.add_custom_button(
						__("Regenerate"),
						() =>
							call("generate", { doctype: "Work Order", name: frm.doc.name }).then(() => {
								frappe.show_alert({ message: __("Labels updated"), indicator: "green" });
								frm.reload_doc();
							}),
						GROUP
					);
					frm.add_custom_button(__("Preview"), () => previewTemplate(frm), GROUP);
					frm.add_custom_button(__("Label list"), () => frappe.set_route("List", "ilL-Label-Print-Job", { work_order: frm.doc.name }), GROUP);
				})
				.catch(() => {});
		},
	});
})();
