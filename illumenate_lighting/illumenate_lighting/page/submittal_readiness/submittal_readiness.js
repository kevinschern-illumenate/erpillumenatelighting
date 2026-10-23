// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

// Spec submittal readiness: templates missing a spec submittal template, spec sheet or field mappings,
// and a dry run that fills a sample build's submittal in memory and grades every mapping.
frappe.pages["submittal-readiness"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Spec Submittal Readiness"),
		single_column: true,
	});
	const kind = page.add_field({
		fieldname: "kind",
		label: __("Template type"),
		fieldtype: "Select",
		options: [
			"",
			"Fixture",
			"Tape/Neon",
			"LED Sheet",
			"Driver",
			"Controller",
			"Extrusion Kit",
		].join("\n"),
		change: load,
	});
	const incomplete = page.add_field({
		fieldname: "only_incomplete",
		label: __("Only incomplete"),
		fieldtype: "Check",
		default: 0,
		change: load,
	});
	page.set_primary_action(__("Refresh"), load, "refresh");
	page.set_secondary_action(__("Test all listed"), testAll);
	const container = document.createElement("div");
	container.className = "p-3";
	page.main[0].append(container);
	const status = document.createElement("p");
	status.setAttribute("role", "status");
	const table = document.createElement("div");
	table.className = "table-responsive";
	const intro = document.createElement("p");
	intro.className = "text-muted";
	intro.textContent = __(
		"Product templates that cannot produce a spec submittal yet. Fix what each row lists, then use Test to fill a sample submittal and check every mapped field.",
	);
	container.append(intro, status, table);
	const METHOD = "illumenate_lighting.illumenate_lighting.api.submittal_readiness.";
	const deskUrl = (doctype, name) =>
		`/app/${doctype.toLowerCase().replace(/[^a-z0-9]+/g, "-")}/${encodeURIComponent(name)}`;
	const statusColor = {
		ready: "green",
		incomplete: "orange",
		ok: "green",
		blank: "yellow",
		fail: "red",
	};
	const pill = (text, color) => {
		const s = document.createElement("span");
		s.className = `indicator-pill ${color || statusColor[text] || "gray"}`;
		s.textContent = text;
		return s;
	};
	let version = 0,
		rows = [],
		testing = false;
	const results = {};

	async function load() {
		const request = ++version;
		status.textContent = __("Loading…");
		try {
			const r = await frappe.call({
				method: METHOD + "get_report",
				type: "GET",
				args: {
					kind: kind.get_value() || "",
					only_incomplete: incomplete.get_value() ? 1 : 0,
				},
			});
			if (request !== version) return;
			const data = r.message;
			rows = data.rows;
			status.textContent = __(
				"{0} of {1} templates are incomplete: {2} have no spec submittal template, {3} have no spec sheet. Lines counts schedule lines that use the template.",
				[
					data.summary.incomplete,
					data.summary.total,
					data.summary.no_submittal_template,
					data.summary.no_spec_sheet,
				]
			);
			if (!rows.length) status.textContent += " " + __("Nothing to show for this filter.");
			render();
		} catch (error) {
			if (request === version) {
				table.replaceChildren();
				status.textContent = __("Readiness is unavailable. Check your role or retry.");
			}
		}
	}

	function render() {
		table.replaceChildren();
		const grid = document.createElement("table");
		grid.className = "table table-bordered table-sm";
		const head = document.createElement("tr");
		[
			__("Type"),
			__("Template"),
			__("Status"),
			__("Missing"),
			__("Notes"),
			__("Mappings"),
			__("Lines"),
			__("Dry run"),
		].forEach((text) => {
			const th = document.createElement("th");
			th.textContent = text;
			head.append(th);
		});
		const thead = document.createElement("thead");
		thead.append(head);
		grid.append(thead);
		const tbody = document.createElement("tbody");
		rows.forEach((row) => {
			const tr = document.createElement("tr");
			const cell = (text) => {
				const td = document.createElement("td");
				td.textContent = text;
				tr.append(td);
				return td;
			};
			cell(row.kind);
			const link = document.createElement("a");
			link.href = deskUrl(row.doctype, row.name);
			link.textContent = row.label;
			const record = document.createElement("td");
			record.append(link);
			tr.append(record);
			const state = document.createElement("td");
			state.append(pill(row.status));
			tr.append(state);
			cell(row.missing.join(", ") || "—");
			cell(row.notes.join("; ") || "—");
			cell(String(row.mapping_count));
			cell(String(row.lines));
			const action = document.createElement("td");
			const result = results[key(row)];
			if (result) {
				const summary = document.createElement("a");
				summary.href = "#";
				summary.append(
					result.success && !result.failures
						? pill(
								result.blanks ? __("{0} blank", [result.blanks]) : __("passed"),
								result.blanks ? "yellow" : "green"
						  )
						: pill(
								result.success
									? __("{0} failing", [result.failures])
									: __("failed"),
								"red"
						  )
				);
				summary.addEventListener("click", (event) => {
					event.preventDefault();
					show(row, result);
				});
				action.append(summary);
			} else if (row.mapping_count && (row.spec_submittal_template || row.spec_sheet)) {
				const button = document.createElement("button");
				button.className = "btn btn-xs btn-default";
				button.textContent = __("Test");
				button.addEventListener("click", async () => {
					button.disabled = true;
					button.textContent = __("Testing…");
					await test(row);
					render();
					const r = results[key(row)];
					if (r) show(row, r);
				});
				action.append(button);
			} else {
				action.textContent = "—";
			}
			tr.append(action);
			tbody.append(tr);
		});
		grid.append(tbody);
		table.append(grid);
	}

	const key = (row) => `${row.kind}::${row.name}`;

	async function test(row) {
		try {
			const r = await frappe.call({
				method: METHOD + "dry_run",
				args: { kind: row.kind, template: row.name },
			});
			results[key(row)] = r.message;
		} catch (error) {
			results[key(row)] = {
				success: false,
				message: __("The dry run could not be started"),
				failures: 0,
				blanks: 0,
				mappings: [],
				unmapped_pdf_fields: [],
				warnings: [],
			};
		}
	}

	async function testAll() {
		if (testing) return;
		testing = true;
		const testable = rows.filter(
			(row) => row.mapping_count && (row.spec_submittal_template || row.spec_sheet)
		);
		for (const [index, row] of testable.entries()) {
			status.textContent = __("Testing {0} of {1}: {2}", [
				index + 1,
				testable.length,
				row.label,
			]);
			await test(row);
			render();
		}
		const failing = testable.filter((row) => {
			const r = results[key(row)];
			return !r.success || r.failures;
		}).length;
		status.textContent = __(
			"{0} of {1} tested templates have failing mappings. Select a result for details.",
			[failing, testable.length]
		);
		testing = false;
	}

	function show(row, result) {
		const dialog = new frappe.ui.Dialog({
			title: __("Dry run: {0}", [row.label]),
			size: "extra-large",
			fields: [{ fieldname: "body", fieldtype: "HTML" }],
		});
		const body = document.createElement("div");
		const line = (text) => {
			const p = document.createElement("p");
			p.textContent = text;
			body.append(p);
			return p;
		};
		line(
			result.sample
				? __("Sample: {0}. Nothing was saved.", [result.sample])
				: __("No sample build was available.")
		);
		line(
			result.success
				? __("The submittal filled successfully.")
				: __("Generation failed: {0}", [result.message || ""])
		);
		if (result.pdf_template) line(__("PDF: {0}", [result.pdf_template]));
		const grid = document.createElement("table");
		grid.className = "table table-bordered table-sm";
		const head = document.createElement("tr");
		[__("PDF field"), __("Source"), __("Value"), __("Result"), __("Details")].forEach(
			(text) => {
				const th = document.createElement("th");
				th.textContent = text;
				head.append(th);
			}
		);
		grid.append(head);
		const order = { fail: 0, blank: 1, ok: 2 };
		[...result.mappings]
			.sort((a, b) => order[a.status] - order[b.status])
			.forEach((mapping) => {
				const tr = document.createElement("tr");
				const cell = (text) => {
					const td = document.createElement("td");
					td.textContent = text;
					tr.append(td);
					return td;
				};
				cell(mapping.pdf_field_name || "—");
				cell(mapping.source);
				cell(
					mapping.value === null || mapping.value === undefined
						? "—"
						: String(mapping.value)
				);
				const state = document.createElement("td");
				state.append(pill(mapping.status));
				tr.append(state);
				cell([...mapping.problems, ...mapping.notes].join("; ") || "—");
				grid.append(tr);
			});
		body.append(grid);
		if (result.unmapped_pdf_fields.length)
			line(
				__("PDF fields with no mapping (left blank): {0}", [
					result.unmapped_pdf_fields.join(", "),
				])
			);
		if (result.warnings.length) {
			const list = document.createElement("ul");
			result.warnings.forEach((text) => {
				const li = document.createElement("li");
				li.textContent = text;
				list.append(li);
			});
			line(__("Generator warnings:"));
			body.append(list);
		}
		dialog.fields_dict.body.$wrapper.empty().append(body);
		dialog.show();
	}

	load();
};
