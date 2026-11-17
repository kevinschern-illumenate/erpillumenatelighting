// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

// New Product wizard (hardening plan 5.5). It only orchestrates existing records and APIs:
// frappe.client, product_clone.duplicate, product_readiness and publication. All text is rendered as text.
frappe.pages["new-product-wizard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("New Product Wizard"), single_column: true });
	window.NewProductWizard.mount(page.main[0]);
};

window.NewProductWizard = (function () {
	const API = "illumenate_lighting.illumenate_lighting.api.";
	const PRODUCT = "ilL-Webflow-Product";
	// Product type -> [template link field, template DocType]; mirrors web_listing_schema.
	const FAMILIES = {
		"Fixture Template": ["fixture_template", "ilL-Fixture-Template"],
		"LED Tape": ["tape_neon_template", "ilL-Tape-Neon-Template"],
		"COB Tape": ["tape_neon_template", "ilL-Tape-Neon-Template"],
		"LED Neon": ["tape_neon_template", "ilL-Tape-Neon-Template"],
		"LED Sheet": ["led_sheet_template", "ilL-LED-Sheet-Template"],
		"Extrusion Kit": ["kit_template", "ilL-Extrusion-Kit-Template"],
		"Driver": ["driver_template", "ilL-Driver-Template"],
		"Controller": ["controller_template", "ilL-Controller-Template"],
		"Component": [null, null],
		"Accessory": [null, null],
	};
	const STEPS = ["Family", "Start", "Identity", "Source template", "Media", "Documents", "Readiness", "Finish"];

	function el(tag, attrs, children) {
		const node = document.createElement(tag);
		Object.entries(attrs || {}).forEach(([key, value]) => {
			if (value === undefined || value === null || value === false) return;
			if (key === "text") node.textContent = String(value);
			else if (key === "className") node.className = value;
			else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
			else node.setAttribute(key, value === true ? "" : String(value));
		});
		[].concat(children || []).forEach(child => child != null && node.append(child));
		return node;
	}

	function slugify(text) {
		return String(text || "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 120);
	}

	function input(label, value, attrs) {
		const control = el("input", { type: "text", className: "form-control", ...(attrs || {}) });
		control.value = value || "";
		return [el("label", { className: "control-label", text: label }, control), control];
	}

	function select(label, options, value) {
		const control = el("select", { className: "form-control" });
		options.forEach(option => {
			const [optionValue, optionLabel] = Array.isArray(option) ? option : [option, option];
			control.append(el("option", { value: optionValue, text: optionLabel }));
		});
		control.value = value || "";
		return [el("label", { className: "control-label", text: label }, control), control];
	}

	async function call(method, args, type) {
		const response = await frappe.call({ method, args, type: type || "POST" });
		return response.message;
	}

	function issueList(report) {
		const list = el("ul");
		(report.issues || []).forEach(row => list.append(el("li", { text: `${row.record} / ${row.field}: ${row.message}` })));
		(report.warnings || []).forEach(row => list.append(el("li", { className: "text-warning", text: `${__("Warning")}: ${row.field}: ${row.message}` })));
		return list.children.length ? list : el("p", { className: "text-success", text: __("No issues found.") });
	}

	function mount(root) {
		const state = { step: 0, family: "", mode: "blank", source: "", name: "", slug: "", short_description: "", sublabel: "",
			template: "", template_code: "", include_media: true, product: null, template_created: null };
		const steps = el("ol", { className: "ill-wizard__steps list-inline small text-muted" });
		const body = el("div", { className: "ill-wizard__body my-3" });
		const feedback = el("div", { role: "status", "aria-live": "polite", className: "small my-2" });
		const back = el("button", { type: "button", className: "btn btn-default btn-sm", text: __("Back") });
		const next = el("button", { type: "button", className: "btn btn-primary btn-sm ml-2", text: __("Next") });
		root.append(el("div", { className: "p-3 ill-wizard" }, [steps, body, feedback, el("div", {}, [back, next])]));

		const template = () => FAMILIES[state.family] || [null, null];
		const say = text => { feedback.textContent = text || ""; };

		async function create() {
			if (state.mode === "clone") {
				const result = await call(API + "product_clone.duplicate", {
					doctype: PRODUCT, name: state.source, new_name: state.name, new_slug: state.slug,
					include_media: state.include_media ? 1 : 0, template_code: state.template_code || "",
				});
				state.product = result.name;
				state.template_created = result.template || null;
				if (result.template) state.template = result.template.name;
				return;
			}
			const [field] = template();
			const doc = { doctype: PRODUCT, product_name: state.name, product_slug: state.slug, product_type: state.family,
				short_description: state.short_description, sublabel: state.sublabel, is_active: 0 };
			if (field && state.template) doc[field] = state.template;
			const saved = await call("frappe.client.insert", { doc });
			state.product = saved.name;
		}

		// Each step returns its form and an optional validator that runs before Next.
		const views = [
			() => {
				const [label, control] = select(__("Product family"), [["", __("Choose a family")], ...Object.keys(FAMILIES)], state.family);
				return [label, () => { if (!control.value) return __("Choose a family."); state.family = control.value; }];
			},
			() => {
				const [modeLabel, mode] = select(__("Start from"), [["blank", __("A blank product")], ["clone", __("A copy of an existing product")]], state.mode);
				const [sourceLabel, source] = input(__("Existing product to copy (slug)"), state.source, { list: "ill-wizard-products" });
				const options = el("datalist", { id: "ill-wizard-products" });
				const [media, keep] = [el("label", { text: " " + __("Reuse images and documents") }), el("input", { type: "checkbox" })];
				keep.checked = state.include_media;
				media.prepend(keep);
				call("frappe.client.get_list", { doctype: PRODUCT, filters: { product_type: state.family }, fields: ["name", "product_name"], limit_page_length: 200, order_by: "product_name asc" }, "GET")
					.then(rows => (rows || []).forEach(row => options.append(el("option", { value: row.name, text: row.product_name || row.name }))))
					.catch(() => {});
				return [el("div", {}, [modeLabel, sourceLabel, options, media]), () => {
					state.mode = mode.value;
					state.source = source.value.trim();
					state.include_media = keep.checked;
					if (state.mode === "clone" && !state.source) return __("Choose the product to copy.");
				}];
			},
			() => {
				const [nameLabel, name] = input(__("Product name"), state.name, { maxlength: "140" });
				const [slugLabel, slug] = input(__("Slug"), state.slug, { maxlength: "120" });
				name.addEventListener("input", () => { if (!slug.dataset.edited) slug.value = slugify(name.value); });
				slug.addEventListener("input", () => { slug.dataset.edited = "1"; });
				const fields = [nameLabel, slugLabel];
				let description, sublabel;
				if (state.mode === "blank") {
					let label;
					[label, description] = input(__("Short description"), state.short_description);
					fields.push(label);
					[label, sublabel] = input(__("Sublabel"), state.sublabel);
					fields.push(label);
				} else {
					fields.push(el("p", { className: "text-muted", text: __("Marketing copy is copied from the source product; edit it on the product form.") }));
				}
				return [el("div", {}, fields), () => {
					state.name = name.value.trim();
					state.slug = slugify(slug.value || name.value);
					if (description) state.short_description = description.value.trim();
					if (sublabel) state.sublabel = sublabel.value.trim();
					if (!state.name || !state.slug) return __("Enter a product name and slug.");
				}];
			},
			() => {
				const [field, doctype] = template();
				if (!field) return [el("p", { text: __("This family has no source template. Link a sales Item on the product form if it is sold through the portal.") }), async () => { await create(); }];
				if (state.mode === "clone") {
					const [label, code] = input(__("Copy the source product's template as (new template code)"), state.template_code);
					return [el("div", {}, [label, el("p", { className: "small text-muted", text: __("Leave blank to link a template later. A template belongs to one product, so the copy never shares the original's template.") })]), async () => {
						state.template_code = code.value.trim();
						await create();
					}];
				}
				const [label, name] = input(__("Existing {0} (template code)", [doctype]), state.template);
				const check = el("button", { type: "button", className: "btn btn-default btn-sm mt-2", text: __("Engineering preflight") });
				const result = el("div", { className: "mt-2" });
				check.addEventListener("click", async () => {
					if (!name.value.trim()) return;
					check.disabled = true;
					try { result.replaceChildren(issueList(await call(API + "product_readiness.authoring_preview", { doctype, name: name.value.trim() }, "GET"))); }
					catch (error) { result.replaceChildren(el("p", { className: "text-danger", text: __("Preflight is unavailable for that template.") })); }
					finally { check.disabled = false; }
				});
				const create_new = el("a", { href: `/app/${frappe.router.slug(doctype)}/new`, target: "_blank", rel: "noopener", className: "btn btn-link btn-sm mt-2", text: __("Create a new template") });
				return [el("div", {}, [label, check, create_new, result]), async () => {
					state.template = name.value.trim();
					if (state.template) {
						const linked = await call("frappe.client.get_value", { doctype, filters: { name: state.template }, fieldname: "webflow_product" }, "GET");
						if (!linked) return __("Template {0} was not found.", [state.template]);
						if (linked.webflow_product) return __("Template {0} already belongs to {1}. Copy it instead, or leave this blank.", [state.template, linked.webflow_product]);
					}
					await create();
				}];
			},
			() => {
				const [, doctype] = template();
				const links = [el("button", { type: "button", className: "btn btn-default btn-sm", text: __("Open the product gallery"), onclick: () => frappe.set_route("Form", PRODUCT, state.product) })];
				if (doctype && state.template) links.push(el("button", { type: "button", className: "btn btn-default btn-sm ml-2", text: __("Set the main image on the template"), onclick: () => frappe.set_route("Form", doctype, state.template) }));
				return [el("div", {}, [el("p", { text: __("The template's main image (hero image) is what dealers and Webflow show first. Add gallery images and alt text on the product.") }), ...links]), null];
			},
			() => {
				const [, doctype] = template();
				const links = [el("button", { type: "button", className: "btn btn-default btn-sm", text: __("Add product documents"), onclick: () => frappe.set_route("Form", PRODUCT, state.product) })];
				if (doctype && state.template) links.push(el("button", { type: "button", className: "btn btn-default btn-sm ml-2", text: __("Attach the template spec sheet"), onclick: () => frappe.set_route("Form", doctype, state.template) }));
				return [el("div", {}, [el("p", { text: __("Attach public literature on the product and the spec sheet on its template.") }), ...links]), null];
			},
			() => {
				const result = el("div", {}, el("p", { text: __("Checking…") }));
				call(API + "product_readiness.preview", { product: state.product, channel: "cms" }, "GET")
					.then(report => result.replaceChildren(issueList(report)))
					.catch(() => result.replaceChildren(el("p", { className: "text-danger", text: __("Readiness is unavailable. Check your role or retry.") })));
				return [result, null];
			},
			() => {
				const [label, brand] = input(__("Brand to publish to"), "");
				const inspect = el("button", { type: "button", className: "btn btn-default btn-sm mt-2", text: __("Inspect publication") });
				const stage = el("button", { type: "button", className: "btn btn-primary btn-sm mt-2 ml-2", text: __("Request staging"), hidden: true });
				const result = el("div", { className: "mt-2" });
				let receipt = null;
				inspect.addEventListener("click", async () => {
					if (!brand.value.trim()) return;
					inspect.disabled = true;
					try {
						receipt = await call(API + "publication.inspect", { product: state.product, brand: brand.value.trim() });
						result.replaceChildren(el("p", { text: `${receipt.state} · ${String(receipt.current_hash || "").slice(0, 12)}` }), issueList(receipt.readiness || {}));
						stage.hidden = !(receipt.readiness && receipt.readiness.ready);
					} catch (error) { result.replaceChildren(el("p", { className: "text-danger", text: __("Inspection failed.") })); }
					finally { inspect.disabled = false; }
				});
				stage.addEventListener("click", async () => {
					stage.disabled = true;
					try {
						const job = await call(API + "publication.request", { product: state.product, brand: receipt.brand, operation: "STAGE", expected_hash: receipt.current_hash });
						say(__("Staging requested: {0}", [job.job]));
					} catch (error) { say(__("Activate the product and resolve readiness before staging.")); }
					finally { stage.disabled = false; }
				});
				return [el("div", {}, [
					el("p", { text: __("{0} is saved as an inactive draft. Activate it on the product form when it is ready, then request staging.", [state.product]) }),
					label, inspect, stage, result,
				]), null];
			},
		];

		let validate = null;
		function show() {
			steps.replaceChildren(...STEPS.map((name, index) => el("li", { className: index === state.step ? "list-inline-item font-weight-bold" : "list-inline-item", "aria-current": index === state.step ? "step" : null, text: `${index + 1}. ${__(name)}` })));
			const [view, check] = views[state.step]();
			validate = check;
			body.replaceChildren(view);
			// Once the draft exists, the earlier steps cannot change it.
			back.disabled = state.step === 0 || (state.product && state.step === 4);
			next.textContent = state.step === 3 ? __("Create draft") : state.step === STEPS.length - 1 ? __("Open product") : __("Next");
		}

		next.addEventListener("click", async () => {
			if (state.step === STEPS.length - 1) { frappe.set_route("Form", PRODUCT, state.product); return; }
			next.disabled = true;
			say("");
			try {
				const problem = validate ? await validate() : null;
				if (problem) { say(problem); return; }
				state.step += 1;
				show();
			} catch (error) {
				say(error && error.message ? error.message : __("That did not work. Check the details and retry."));
			} finally {
				next.disabled = false;
			}
		});
		back.addEventListener("click", () => { if (state.step > 0) { state.step -= 1; show(); } });
		show();
		return { state, show };
	}

	return { mount, slugify, FAMILIES, STEPS };
})();
