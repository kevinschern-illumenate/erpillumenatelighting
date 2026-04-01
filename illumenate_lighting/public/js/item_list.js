frappe.listview_settings["Item"] = {
	onload: function (listview) {
		// Add "Total Stock Qty" to the fields fetched for each row
		if (!listview.fields.includes("name")) {
			listview.fields.push("name");
		}
	},

	refresh: function (listview) {
		// After the list renders, fetch stock totals from Bin and display them
		var item_codes = listview.data.map(function (d) { return d.name; });
		if (!item_codes.length) return;

		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: "Bin",
				filters: { item_code: ["in", item_codes] },
				fields: ["item_code", "sum(actual_qty) as actual_qty"],
				group_by: "item_code",
				limit_page_length: 0,
			},
			async: false,
			callback: function (r) {
				if (!r.message) return;

				var stock_map = {};
				r.message.forEach(function (d) {
					stock_map[d.item_code] = d.actual_qty;
				});

				listview.data.forEach(function (d) {
					d._stock_qty = stock_map[d.name] || 0;
				});
			},
		});
	},

	add_fields: ["item_name"],

	formatters: {
		item_name: function (val, df, doc) {
			// Append stock qty badge next to item name
			var qty = doc._stock_qty != null ? doc._stock_qty : "";
			if (qty !== "") {
				var color = qty > 0 ? "green" : "orange";
				return val + ' <span class="indicator-pill ' + color + '">' + qty + " in stock</span>";
			}
			return val;
		},
	},
};
