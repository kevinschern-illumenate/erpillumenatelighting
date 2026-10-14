// List indicators for portal requests: who the next step waits on, until the request is finished.
(function () {
	const FINISHED = {
		'ilL-Quote-Request': ['state', ['ISSUED', 'CLOSED']],
		'ilL-Order-Intake': ['state', ['APPROVED', 'REJECTED', 'WITHDRAWN']],
		'ilL-Order-Change': ['state', ['COMPLETED', 'REJECTED']],
		'ilL-Document-Request': ['status', ['Completed', 'Closed', 'Cancelled']],
	};
	window.illumenate_portal_indicator = function (doctype, doc) {
		const [field, finished] = FINISHED[doctype];
		const value = doc[field];
		if (finished.includes(value)) {
			const label = String(value).replace(/_/g, ' ').toLowerCase().replace(/^./, c => c.toUpperCase());
			return [__(label), ['REJECTED', 'WITHDRAWN', 'Cancelled'].includes(value) ? 'red' : 'green', field + ',=,' + value];
		}
		if (doc.ill_next_action_by === 'Customer') return [__('Waiting on customer'), 'blue', 'ill_next_action_by,=,Customer'];
		if (doc.ill_next_action_by === 'None') return [__('No action needed'), 'gray', 'ill_next_action_by,=,None'];
		return [__('Waiting on staff'), 'orange', 'ill_next_action_by,=,Staff'];
	};
	Object.keys(FINISHED).forEach(doctype => {
		const settings = frappe.listview_settings[doctype] = frappe.listview_settings[doctype] || {};
		settings.add_fields = [...new Set([...(settings.add_fields || []), FINISHED[doctype][0], 'ill_next_action_by'])];
		settings.get_indicator = doc => window.illumenate_portal_indicator(doctype, doc);
	});
})();
