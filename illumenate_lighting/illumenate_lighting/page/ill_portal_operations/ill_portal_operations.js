// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

// Portal Operations: every staff work queue, grouped by the team that owns it. Pick a queue to see its
// open items, narrow them with a view or search, and open a record from its ID.
frappe.pages["ill-portal-operations"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Portal Operations"),
		single_column: true,
	});

	// Team sections in display order. Keys match the queue capability returned by queues.summary.
	const GROUPS = [
		[
			"sales",
			__("Sales"),
			__(
				"Quotes, orders and product questions from dealers that are waiting on a sales response.",
			),
		],
		[
			"accounts",
			__("Accounts & Finance"),
			__(
				"New dealer accounts, customers to finish setting up, and bills to sync to QuickBooks.",
			),
		],
		[
			"engineering",
			__("Engineering"),
			__("Drawings to produce or re-approve, and schedule exports that did not finish."),
		],
		[
			"operations",
			__("Operations"),
			__("Production held for drawing approval and materials that still need ordering."),
		],
		["support", __("Support"), __("Dealer support tickets waiting on a reply.")],
		[
			"integration",
			__("Integrations"),
			__("Website publishing and portal emails that failed and need a retry."),
		],
		[
			"inbox",
			__("Sales Inbox"),
			__("Emails to the sales address that are not linked to a record yet."),
		],
	];
	const QUEUE_HELP = {
		verification: __("Dealers asking us to confirm a product can be built as configured."),
		quotes: __("Dealers asking for pricing on a project schedule."),
		expiring_offers: __("Issued quote offers that expire soon. Follow up before they lapse."),
		orders: __("Orders dealers submitted for review before they become sales orders."),
		order_changes: __("Requests to change or cancel an order already placed."),
		accounts: __("Dealer sign-ups and account changes awaiting approval."),
		new_customers: __("Customers created from CRM deals that still need payment terms."),
		bills: __("Submitted purchase invoices that are not in QuickBooks yet."),
		drawings: __("Drawing and document requests that are still open."),
		reapproval: __(
			"Drawings a dealer asked to change, or that need approval again after a change.",
		),
		exports: __("Schedule exports that failed or finished incomplete."),
		production: __("Drawings required for manufacturing that are not approved yet."),
		materials: __("Purchase material requests that are not fully ordered."),
		support: __("Open support issues."),
		publication: __("Product publish jobs to the website that failed."),
		email: __("Portal emails that failed to send."),
		inbox: __("Received emails at the sales address with no linked record."),
	};
	const VIEW_LABELS = {
		all: __("Everything"),
		mine: __("Assigned to me"),
		unassigned: __("Unassigned"),
		overdue: __("Overdue"),
	};

	const el = (tag, className, text) => {
		const node = document.createElement(tag);
		if (className) node.className = className;
		if (text != null) node.textContent = text;
		return node;
	};
	const humanize = (key) =>
		key
			.replace(/^_/, "")
			.replaceAll("_", " ")
			.replace(/\b\w/g, (c) => c.toUpperCase());

	const style = el("style");
	style.textContent = `
		.ill-ops { padding: var(--padding-md, 15px); max-width: 1200px; }
		.ill-ops [hidden] { display: none !important; }
		.ill-ops-intro { background: var(--subtle-fg, var(--card-bg)); border: 1px solid var(--border-color); border-radius: var(--border-radius-md, 8px); padding: 16px 20px; margin-bottom: 24px; }
		.ill-ops-intro h4 { margin: 0 0 4px; }
		.ill-ops-steps { display: flex; flex-wrap: wrap; gap: 8px 24px; margin: 10px 0 0; padding: 0; list-style: none; color: var(--text-muted); font-size: var(--text-sm, 13px); }
		.ill-ops-steps b { color: var(--text-color); margin-right: 4px; }
		.ill-ops-group { margin-bottom: 24px; }
		.ill-ops-group h5 { margin: 0 0 2px; font-weight: 600; }
		.ill-ops-group > p { color: var(--text-muted); font-size: var(--text-sm, 13px); margin: 0 0 10px; }
		.ill-ops-tiles { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 10px; }
		.ill-ops-tile { display: flex; flex-direction: column; gap: 4px; text-align: left; background: var(--card-bg); border: 1px solid var(--border-color); border-radius: var(--border-radius-md, 8px); padding: 12px 14px; cursor: pointer; transition: border-color .15s, box-shadow .15s; color: var(--text-color); }
		.ill-ops-tile:hover:not(:disabled) { border-color: var(--primary, #2490ef); }
		.ill-ops-tile:focus-visible { outline: 2px solid var(--primary, #2490ef); outline-offset: 2px; }
		.ill-ops-tile.is-active { border-color: var(--primary, #2490ef); box-shadow: 0 0 0 1px var(--primary, #2490ef); }
		.ill-ops-tile:disabled { cursor: not-allowed; opacity: .6; }
		.ill-ops-tile-top { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
		.ill-ops-tile-name { font-weight: 600; }
		.ill-ops-count { font-size: 1.4em; font-weight: 600; line-height: 1; }
		.ill-ops-count.is-zero { color: var(--text-muted); font-weight: 400; }
		.ill-ops-tile-help { color: var(--text-muted); font-size: var(--text-xs, 12px); }
		.ill-ops-detail { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: var(--border-radius-md, 8px); padding: 16px 20px; margin-top: 8px; scroll-margin-top: 80px; }
		.ill-ops-detail h4 { margin: 0; }
		.ill-ops-detail-help { color: var(--text-muted); margin: 2px 0 14px; }
		.ill-ops-toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: space-between; margin-bottom: 12px; }
		.ill-ops-toolbar input { max-width: 260px; }
		.ill-ops-empty { text-align: center; color: var(--text-muted); padding: 32px 0; }
		.ill-ops-pager { display: flex; justify-content: space-between; align-items: center; gap: 8px; color: var(--text-muted); font-size: var(--text-sm, 13px); }
		.ill-ops-table th { white-space: nowrap; color: var(--text-muted); font-weight: 500; }
	`;

	const root = el("div", "ill-ops");
	page.main[0].append(style, root);

	const intro = el("div", "ill-ops-intro");
	intro.append(
		el("h4", null, __("Requests waiting on our team")),
		el(
			"div",
			"text-muted",
			__(
				"Each tile below is a work queue. The number shows how many items are waiting. Queues are grouped by the team that usually handles them, and you only see the ones your role can work.",
			),
		),
	);
	const steps = el("ol", "ill-ops-steps");
	[
		[1, __("Choose a queue")],
		[2, __("Narrow it by view or search")],
		[3, __("Click an ID to open and work the record")],
	].forEach(([n, text]) => {
		const li = el("li");
		li.append(el("b", null, `${n}.`), document.createTextNode(text));
		steps.append(li);
	});
	intro.append(steps);

	const groupsEl = el("div");
	const summaryStatus = el("p", "text-muted");
	summaryStatus.setAttribute("role", "status");

	const detail = el("section", "ill-ops-detail");
	detail.hidden = true;
	detail.setAttribute("aria-live", "polite");
	const detailTitle = el("h4");
	const detailHelp = el("p", "ill-ops-detail-help");
	const toolbar = el("div", "ill-ops-toolbar");
	const views = el("div", "btn-group btn-group-sm");
	views.setAttribute("role", "group");
	views.setAttribute("aria-label", __("Queue view"));
	const search = el("input", "form-control input-sm");
	search.type = "search";
	search.placeholder = __("Search by ID…");
	search.setAttribute("aria-label", __("Search this queue"));
	toolbar.append(views, search);
	const status = el("p", "text-muted small");
	status.setAttribute("role", "status");
	const table = el("div", "table-responsive");
	const pager = el("nav", "ill-ops-pager");
	pager.setAttribute("aria-label", __("Queue pages"));
	const pagerText = el("span");
	const pagerButtons = el("div", "btn-group btn-group-sm");
	const prev = el("button", "btn btn-default", __("Previous"));
	const next = el("button", "btn btn-default", __("Next"));
	pagerButtons.append(prev, next);
	pager.append(pagerText, pagerButtons);
	detail.append(detailTitle, detailHelp, toolbar, status, table, pager);

	root.append(intro, summaryStatus, groupsEl, detail);

	let selected,
		view = "all",
		currentPage = 1,
		version = 0,
		timer;
	const tiles = {};

	function renderViews() {
		views.replaceChildren();
		selected.views.forEach((value) => {
			const button = el(
				"button",
				`btn ${value === view ? "btn-primary" : "btn-default"}`,
				VIEW_LABELS[value] || __(value),
			);
			button.setAttribute("aria-pressed", String(value === view));
			button.addEventListener("click", () => {
				view = value;
				currentPage = 1;
				renderViews();
				load();
			});
			views.append(button);
		});
	}

	function select(queue, scroll) {
		selected = queue;
		view = "all";
		currentPage = 1;
		search.value = "";
		Object.entries(tiles).forEach(([key, tile]) =>
			tile.classList.toggle("is-active", key === queue.key),
		);
		detail.hidden = false;
		detailTitle.textContent = queue.label;
		detailHelp.textContent = QUEUE_HELP[queue.key] || "";
		search.placeholder =
			queue.key === "inbox"
				? __("Search by subject…")
				: queue.key === "new_customers"
					? __("Search by customer name…")
					: __("Search by ID…");
		renderViews();
		load();
		if (scroll) detail.scrollIntoView({ behavior: "smooth", block: "start" });
	}

	function cellValue(value) {
		if (value == null || value === "") return "—";
		// Dates and datetimes arrive as ISO strings; show them in the user's date format.
		if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}/.test(value))
			return frappe.datetime.str_to_user(value);
		return String(value);
	}

	async function load() {
		if (!selected) return;
		const request = ++version;
		status.textContent = __("Loading…");
		try {
			const r = await frappe.call({
				method: "illumenate_lighting.illumenate_lighting.portal.queues.items",
				args: { queue: selected.key, view, search: search.value, page: currentPage },
			});
			if (request !== version) return;
			const data = r.message;
			table.replaceChildren();
			status.textContent = "";
			const start = data.total ? (data.page - 1) * data.page_size + 1 : 0;
			const end = Math.min(data.page * data.page_size, data.total);
			pagerText.textContent = data.total
				? __("Showing {0}–{1} of {2}", [start, end, data.total])
				: "";
			prev.disabled = currentPage <= 1;
			next.disabled = currentPage * data.page_size >= data.total;
			pager.hidden = !data.total;
			pagerButtons.hidden = data.total <= data.page_size;
			if (!data.rows.length) {
				table.append(
					el(
						"div",
						"ill-ops-empty",
						search.value || view !== "all"
							? __("No items match this view.")
							: __("Nothing is waiting in this queue."),
					),
				);
				return;
			}
			const grid = el("table", "table table-hover ill-ops-table");
			const columns = Object.keys(data.rows[0]);
			const head = el("tr");
			columns.forEach((key) =>
				head.append(el("th", null, key === "name" ? __("ID") : humanize(key))),
			);
			const thead = el("thead");
			thead.append(head);
			grid.append(thead);
			const tbody = el("tbody");
			data.rows.forEach((row) => {
				const tr = el("tr");
				columns.forEach((key) => {
					const td = el("td");
					if (key === "name") {
						const link = el("button", "btn btn-link p-0", row[key]);
						link.addEventListener("click", () =>
							frappe.set_route("Form", data.doctype, row.name),
						);
						td.append(link);
					} else if ((key === "state" || key === "status") && row[key]) {
						td.append(el("span", "indicator-pill gray", String(row[key])));
					} else td.textContent = cellValue(row[key]);
					tr.append(td);
				});
				tbody.append(tr);
			});
			grid.append(tbody);
			table.append(grid);
		} catch (error) {
			if (request === version) {
				table.replaceChildren();
				pager.hidden = true;
				status.textContent = __(
					"This queue could not be loaded. Check your role or try again.",
				);
			}
		}
	}

	async function refresh() {
		summaryStatus.textContent = __("Loading queues…");
		try {
			const r = await frappe.call({
				method: "illumenate_lighting.illumenate_lighting.portal.queues.summary",
			});
			const queues = r.message.queues;
			groupsEl.replaceChildren();
			Object.keys(tiles).forEach((key) => delete tiles[key]);
			summaryStatus.textContent = queues.length
				? ""
				: __(
						"No portal operations role is assigned to this account. Ask an administrator to add the role for your team.",
					);
			const known = new Set(GROUPS.map(([key]) => key));
			const sections = [
				...GROUPS,
				...[...new Set(queues.map((q) => q.group))]
					.filter((g) => !known.has(g))
					.map((g) => [g, humanize(g || "other"), ""]),
			];
			sections.forEach(([key, title, help]) => {
				const members = queues.filter((q) => q.group === key);
				if (!members.length) return;
				const section = el("section", "ill-ops-group");
				const waiting = members.reduce((sum, q) => sum + (q.available ? q.total : 0), 0);
				const heading = el("h5", null, title);
				heading.append(
					el("span", "text-muted small", ` · ${__("{0} waiting", [waiting])}`),
				);
				section.append(heading, el("p", null, help));
				const grid = el("div", "ill-ops-tiles");
				members.forEach((queue) => {
					const tile = el("button", "ill-ops-tile");
					tile.type = "button";
					tile.disabled = !queue.available;
					const top = el("div", "ill-ops-tile-top");
					top.append(
						el("span", "ill-ops-tile-name", queue.label),
						el(
							"span",
							`ill-ops-count${queue.total ? "" : " is-zero"}`,
							queue.available ? String(queue.total) : "—",
						),
					);
					tile.append(
						top,
						el(
							"span",
							"ill-ops-tile-help",
							queue.available
								? QUEUE_HELP[queue.key] || ""
								: __("You need read access to this document type."),
						),
					);
					tile.addEventListener("click", () => select(queue, true));
					tiles[queue.key] = tile;
					grid.append(tile);
				});
				section.append(grid);
				groupsEl.append(section);
			});
			const keep = selected && queues.find((q) => q.key === selected.key && q.available);
			const first =
				keep ||
				queues.find((q) => q.available && q.total) ||
				queues.find((q) => q.available);
			if (keep) {
				selected = keep;
				tiles[keep.key].classList.add("is-active");
				detailTitle.textContent = keep.label;
				load();
			} else if (first) select(first, false);
			else detail.hidden = true;
		} catch (error) {
			summaryStatus.textContent = __("Could not load queue counts. Try Refresh.");
		}
	}

	search.addEventListener("input", () => {
		clearTimeout(timer);
		timer = setTimeout(() => {
			currentPage = 1;
			load();
		}, 250);
	});
	prev.addEventListener("click", () => {
		currentPage--;
		load();
	});
	next.addEventListener("click", () => {
		currentPage++;
		load();
	});
	page.set_primary_action(__("Refresh"), refresh, "refresh");
	refresh();
};
