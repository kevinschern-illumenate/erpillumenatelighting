// Copyright (c) 2026, ilLumenate Lighting and contributors
// For license information, please see license.txt

frappe.listview_settings['ilL-QBO-Push-Log'] = {
	get_indicator(doc) {
		const colors = {Synced: 'green', Skipped: 'blue', Queued: 'orange', Processing: 'orange', Failed: 'red'};
		return [__(doc.status), colors[doc.status] || 'gray', `status,=,${doc.status}`];
	},
};
