// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

// Product readiness dashboard (hardening plan 5.6): one traffic-light row per Webflow Product.
// Every value is rendered as text; each cell opens the record and field that needs attention.
frappe.pages["product-readiness"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Product Readiness"), single_column: true });
	window.ProductReadinessBoard.mount(page, page.main[0]);
};

window.ProductReadinessBoard = (function () {
	const METHOD = "illumenate_lighting.illumenate_lighting.api.readiness_dashboard.dashboard";
	const PREVIEW = "illumenate_lighting.illumenate_lighting.api.product_readiness.preview";
	const COLUMNS = [
		["identity", "Identity"], ["source", "Source"], ["specs", "Specs"], ["images", "Images"], ["alt_text", "Alt text"],
		["docs", "Docs"], ["spec_sheet", "Spec sheet"], ["publication", "Publication"], ["webflow_sync", "Webflow sync"],
	];
	const COLORS = { ok: "green", warn: "orange", fail: "red", na: "gray" };
	const LABELS = { ok: "OK", warn: "Check", fail: "Fix", na: "N/A" };
	const FAMILIES = ["", "Fixture Template", "LED Tape", "COB Tape", "LED Neon", "LED Sheet", "Extrusion Kit", "Driver", "Controller", "Component", "Accessory"];

	function el(tag, className, text) {
		const node = document.createElement(tag);
		if (className) node.className = className;
		if (text !== undefined && text !== null) node.textContent = String(text);
		return node;
	}

	async function open(target) {
		await frappe.set_route("Form", target.doctype, target.name);
		if (target.field) setTimeout(() => window.cur_frm?.scroll_to_field?.(target.field), 400);
	}

	function cellNode(value) {
		const td = el("td");
		const pill = el(value.name ? "a" : "span", `indicator-pill ${COLORS[value.status] || "gray"}`, __(LABELS[value.status] || value.status));
		pill.title = value.message || "";
		if (value.name) {
			pill.href = "#";
			pill.setAttribute("aria-label", __("{0}: open {1}", [value.message || "", value.name]));
			pill.addEventListener("click", event => { event.preventDefault(); open(value); });
		}
		td.append(pill, el("div", "small text-muted", value.message || ""));
		return td;
	}

	async function preflight(product, button) {
		button.disabled = true;
		try {
			const response = await frappe.call({ method: PREVIEW, args: { product, channel: "cms" } });
			const result = response.message || {};
			const body = el("div");
			if (result.ready) body.append(el("p", "", __("The saved product passes the CMS channel preflight.")));
			const list = el("ul");
			(result.issues || []).forEach(row => list.append(el("li", "", `${row.record} / ${row.field}: ${row.message}`)));
			(result.warnings || []).forEach(row => list.append(el("li", "text-warning", `${__("Warning")}: ${row.field}: ${row.message}`)));
			if (list.children.length) body.append(list);
			frappe.msgprint({ title: __("Preflight: {0}", [product]), message: body.outerHTML, wide: true });
		} finally {
			button.disabled = false;
		}
	}

	function rowNode(row) {
		const tr = el("tr");
		const name = el("td");
		const link = el("a", "", row.product_name || row.product);
		link.href = `/app/ill-webflow-product/${encodeURIComponent(row.product)}`;
		name.append(link, el("div", "small text-muted", [row.product_type, row.is_active ? __("Active") : __("Inactive")].filter(Boolean).join(" · ")));
		tr.append(name);
		COLUMNS.forEach(([column]) => tr.append(cellNode(row.cells[column] || { status: "na", message: "" })));
		const action = el("td");
		const button = el("button", "btn btn-xs btn-default", __("Preflight"));
		button.type = "button";
		button.addEventListener("click", () => preflight(row.product, button));
		action.append(button);
		tr.append(action);
		return tr;
	}

	function mount(page, root) {
		const state = { rows: [], cursor: null, version: 0 };
		const filters = {
			family: page.add_field({ fieldname: "family", label: __("Family"), fieldtype: "Select", options: FAMILIES.join("\n"), change: () => load() }),
			brand: page.add_field({ fieldname: "brand", label: __("Brand"), fieldtype: "Link", options: "ilL-Webflow-Brand", change: () => load() }),
			incomplete: page.add_field({ fieldname: "only_incomplete", label: __("Only incomplete"), fieldtype: "Check", default: 0, change: () => load() }),
		};
		page.set_primary_action(__("Refresh"), () => load(), "refresh");
		const container = el("div", "p-3");
		const intro = el("p", "text-muted", __("Each product's authoring checks at a glance. Select a status to open the record and field that needs attention; Preflight runs the full CMS check."));
		const status = el("p");
		status.setAttribute("role", "status");
		const table = el("div", "table-responsive");
		const more = el("button", "btn btn-sm btn-default", __("Load more"));
		more.type = "button";
		more.hidden = true;
		more.addEventListener("click", () => load(true));
		container.append(intro, status, table, more);
		root.append(container);

		function render() {
			const grid = el("table", "table table-bordered table-sm");
			const head = el("tr");
			[__("Product"), ...COLUMNS.map(([, label]) => __(label)), ""].forEach(text => head.append(el("th", "", text)));
			const thead = el("thead");
			thead.append(head);
			const tbody = el("tbody");
			state.rows.forEach(row => tbody.append(rowNode(row)));
			grid.append(thead, tbody);
			table.replaceChildren(grid);
			const ready = state.rows.filter(row => row.ready).length;
			status.textContent = state.rows.length
				? __("{0} products shown, {1} ready.", [state.rows.length, ready])
				: __("Nothing to show for this filter.");
			more.hidden = !state.cursor;
		}

		async function load(append = false) {
			const request = ++state.version;
			status.textContent = __("Loading…");
			try {
				const response = await frappe.call({
					method: METHOD,
					type: "GET",
					args: {
						family: filters.family.get_value() || "",
						brand: filters.brand.get_value() || "",
						only_incomplete: filters.incomplete.get_value() ? 1 : 0,
						after: append ? state.cursor : "",
					},
				});
				if (request !== state.version) return;
				const data = response.message || {};
				state.rows = append ? state.rows.concat(data.rows || []) : data.rows || [];
				state.cursor = data.next_cursor || null;
				render();
			} catch (error) {
				if (request !== state.version) return;
				table.replaceChildren();
				more.hidden = true;
				status.textContent = __("Readiness is unavailable. Check your role or retry.");
			}
		}

		load();
		return { load, state };
	}

	return { mount, open, cellNode, rowNode, COLUMNS };
})();
