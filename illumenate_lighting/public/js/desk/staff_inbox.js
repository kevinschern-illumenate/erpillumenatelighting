// Staff inbox (plan 7.4): every owned work item across the portal queues in one list, overdue first,
// with quick actions that reuse the server's validated writers. Mounted by the Portal Operations page.
(function (root) {
	const QUEUES = "illumenate_lighting.illumenate_lighting.portal.queues";
	const REPLY = "illumenate_lighting.illumenate_lighting.portal.conversations.reply";
	const t = (text, args) => (root.__ ? root.__(text, args) : text);
	const VIEWS = [
		["all", "Everything"],
		["mine", "Assigned to me"],
		["unassigned", "Unassigned"],
		["overdue", "Overdue"],
	];
	const DUE = {
		overdue: ["red", "Overdue"],
		due_soon: ["orange", "Due soon"],
		ok: ["green", "On track"],
		none: ["gray", "No due date"],
	};

	function key() {
		const random = root.crypto && root.crypto.randomUUID ? root.crypto.randomUUID() : "";
		return random || `inbox-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
	}

	function mount(container, options = {}) {
		const frappe = root.frappe;
		const doc = container.ownerDocument;
		const el = (tag, className, text) => {
			const node = doc.createElement(tag);
			if (className) node.className = className;
			if (text != null) node.textContent = text;
			return node;
		};
		const me = () => (frappe.session && frappe.session.user) || "";
		let view = "all",
			version = 0,
			timer;

		const section = el("section", "ill-ops-inbox");
		const heading = el("h4", null, t("My inbox"));
		const help = el(
			"p",
			"ill-ops-detail-help",
			t(
				"Every dealer request with an owner, across quotes, orders, drawings, verification, accounts and support. Overdue items come first.",
			),
		);
		const toolbar = el("div", "ill-ops-toolbar");
		const views = el("div", "btn-group btn-group-sm");
		views.setAttribute("role", "group");
		views.setAttribute("aria-label", t("Inbox view"));
		const search = el("input", "form-control input-sm");
		search.type = "search";
		search.placeholder = t("Search by ID…");
		search.setAttribute("aria-label", t("Search the inbox"));
		toolbar.append(views, search);
		const status = el("p", "text-muted small");
		status.setAttribute("role", "status");
		const table = el("div", "table-responsive");
		section.append(heading, help, toolbar, status, table);
		container.append(section);

		function renderViews() {
			views.replaceChildren();
			VIEWS.forEach(([value, label]) => {
				const button = el(
					"button",
					`btn ${value === view ? "btn-primary" : "btn-default"}`,
					t(label),
				);
				button.type = "button";
				button.dataset.view = value;
				button.setAttribute("aria-pressed", String(value === view));
				button.addEventListener("click", () => {
					view = value;
					renderViews();
					load();
				});
				views.append(button);
			});
		}

		function date(value) {
			if (!value) return "—";
			return frappe.datetime && frappe.datetime.str_to_user
				? frappe.datetime.str_to_user(value)
				: String(value);
		}

		async function act(button, work) {
			button.disabled = true;
			try {
				await work();
				if (options.onChange) options.onChange();
				await load();
			} catch (error) {
				button.disabled = false;
				status.textContent = t("That action did not complete. Reload and try again.");
			}
		}

		function claim(row, button) {
			return act(button, async () => {
				await frappe.call({
					method: `${QUEUES}.claim`,
					args: { queue: row.queue, name: row.name, expected_modified: row.modified },
					freeze: true,
				});
				frappe.show_alert &&
					frappe.show_alert({ message: t("Assigned to you"), indicator: "green" });
			});
		}

		function waitOnDealer(row, button) {
			frappe.prompt(
				[
					{
						fieldname: "body",
						fieldtype: "Small Text",
						reqd: 1,
						label: t("What do you need from the dealer?"),
						description: t(
							"The dealer will see this message, and the request will wait on them.",
						),
					},
				],
				(values) =>
					act(button, () =>
						frappe.call({
							method: REPLY,
							args: {
								parent_type: row.doctype,
								parent_name: row.name,
								body: values.body,
								idempotency_key: key(),
								visibility: "Customer",
								action: "REQUEST_INFO",
							},
							freeze: true,
						}),
					),
				t("Wait on dealer"),
				t("Send to dealer"),
			);
		}

		function actions(row) {
			const cell = el("td", "ill-ops-inbox-actions");
			if (row.assigned_to !== me()) {
				const mine = el("button", "btn btn-xs btn-default", t("Assign to me"));
				mine.type = "button";
				mine.dataset.action = "claim";
				mine.addEventListener("click", () => claim(row, mine));
				cell.append(mine);
			}
			const reply = el("button", "btn btn-xs btn-default", t("Reply"));
			reply.type = "button";
			reply.dataset.action = "reply";
			reply.addEventListener("click", () => frappe.set_route("Form", row.doctype, row.name));
			cell.append(reply);
			if (row.can_wait && row.next_action_by !== "Customer") {
				const wait = el("button", "btn btn-xs btn-default", t("Wait on dealer"));
				wait.type = "button";
				wait.dataset.action = "wait";
				wait.addEventListener("click", () => waitOnDealer(row, wait));
				cell.append(wait);
			}
			return cell;
		}

		function render(data) {
			table.replaceChildren();
			const notes = [];
			if (data.truncated && data.truncated.length)
				notes.push(t("Some queues have more items; open their tile to page through them."));
			status.textContent = notes.join(" ");
			if (!data.rows.length) {
				table.append(
					el(
						"div",
						"ill-ops-empty",
						search.value || view !== "all"
							? t("No items match this view.")
							: t("Nothing is waiting on you."),
					),
				);
				return;
			}
			const grid = el("table", "table table-hover ill-ops-table");
			const head = el("tr");
			["ID", "Queue", "Dealer", "Assignee", "Due", "Age", "State", ""].forEach((label) =>
				head.append(el("th", null, label ? t(label) : "")),
			);
			const thead = el("thead");
			thead.append(head);
			const tbody = el("tbody");
			data.rows.forEach((row) => {
				const tr = el("tr");
				tr.dataset.name = row.name;
				const id = el("td");
				const open = el("button", "btn btn-link p-0", row.name);
				open.type = "button";
				open.addEventListener("click", () => frappe.set_route("Form", row.doctype, row.name));
				id.append(open);
				if (row.title) id.append(el("div", "text-muted small", row.title));
				tr.append(id, el("td", null, row.queue_label || row.queue));
				tr.append(
					el("td", null, row.customer_name || row.customer || row.dealer_user || "—"),
				);
				tr.append(el("td", null, row.assigned_to || t("Unassigned")));
				const due = el("td");
				const [color, label] = DUE[row.due_state] || DUE.none;
				const badge = el("span", `indicator-pill ${color}`, t(label));
				badge.dataset.due = row.due_state;
				due.append(badge);
				if (row.due) due.append(el("div", "text-muted small", date(row.due)));
				tr.append(due);
				tr.append(
					el(
						"td",
						null,
						row.age_days == null ? "—" : t("{0} d", [row.age_days]),
					),
				);
				const state = el("td");
				if (row.state) state.append(el("span", "indicator-pill gray", String(row.state)));
				tr.append(state, actions(row));
				tbody.append(tr);
			});
			grid.append(thead, tbody);
			table.append(grid);
		}

		async function load() {
			const request = ++version;
			status.textContent = t("Loading…");
			try {
				const r = await frappe.call({
					method: `${QUEUES}.inbox`,
					args: { view, search: search.value },
				});
				if (request !== version) return;
				render(r.message);
			} catch (error) {
				if (request !== version) return;
				table.replaceChildren();
				status.textContent = t("The inbox could not be loaded. Check your role or try again.");
			}
		}

		search.addEventListener("input", () => {
			clearTimeout(timer);
			timer = setTimeout(load, 250);
		});
		renderViews();
		load();
		return { load, section };
	}

	root.IllStaffInbox = { mount };
})(typeof window !== "undefined" ? window : globalThis);
