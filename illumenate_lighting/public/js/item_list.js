frappe.listview_settings["Item"] = {
	refresh: function (listview) {
		var item_codes = listview.data.map(function (d) { return d.name; });
		if (!item_codes.length) return;

		// Remove any badges from a previous render to avoid duplicates
		listview.wrapper.find(".ilL-stock-badge").remove();

		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "Bin",
				filters: { item_code: ["in", item_codes] },
				fields: ["item_code", "actual_qty"],
				limit_page_length: 0,
			},
			callback: function (r) {
				if (!r.message) return;

				// Sum actual_qty across all warehouses per item in JS
				var stock_map = {};
				r.message.forEach(function (d) {
					stock_map[d.item_code] = (stock_map[d.item_code] || 0) + (d.actual_qty || 0);
				});

				// Inject a badge into each list row via the DOM
				item_codes.forEach(function (item_code) {
					var qty = stock_map[item_code] || 0;
					var color = qty > 0 ? "green" : "orange";
					var badge = '<span class="indicator-pill ' + color + ' ilL-stock-badge" style="margin-left:8px; font-size:11px">'
						+ qty + " in stock</span>";
					listview.wrapper
						.find('[data-name="' + CSS.escape(item_code) + '"]')
						.find(".list-row-col.ellipsis")
						.first()
						.append(badge);
				});
			},
		});
	},
};
