// Schedule detail page (actions). Extracted verbatim from templates/pages/schedule.html (plan 2.1).
// Line buttons carry their index in data attributes; one delegated listener dispatches them.
document.addEventListener('click', function(event) {
	var button = event.target.closest('[data-line-action]');
	if (!button) return;
	var action = { editLine: editLine, duplicateLine: duplicateLine, deleteLine: deleteLine }[button.dataset.lineAction];
	if (action) action(parseInt(button.dataset.lineIndex, 10));
});

var scheduleStatusClasses = scheduleContext.status_classes;
var exportStatuses = scheduleContext.export_statuses;
var statusLabels = scheduleContext.status_labels;
// An issued quote is tied to this exact revision; leaving QUOTED replaces it.
var openOffer = scheduleContext.open_offer;

function statusChangeMessage(new_status) {
	var message = __('Change schedule status to {0}?', [frappe.utils.escape_html(statusLabels[new_status] || new_status)]);
	if (openOffer && scheduleContext.schedule_status === 'QUOTED') {
		var offer = frappe.utils.escape_html(openOffer.name);
		message = openOffer.valid_until
			? __('Quote {0} (valid until {1}) will no longer be acceptable. Continue?', [offer, frappe.utils.escape_html(openOffer.valid_until)])
			: __('Quote {0} will no longer be acceptable. Continue?', [offer]);
	}
	return message;
}

function changeStatus(new_status) {
	frappe.confirm(statusChangeMessage(new_status), function() {
		frappe.call({
			method: 'illumenate_lighting.illumenate_lighting.api.portal.update_schedule_status',
			args: {
				schedule_name: schedule_name,
				new_status: new_status
			},
			callback: function(r) {
				if (r.message && r.message.success) {
					frappe.show_alert({
						message: __('Status updated to {0}', [statusLabels[r.message.new_status] || new_status]),
						indicator: 'green'
					});
					if (r.message.auto_versioned && r.message.new_schedule_name) {
						// Leaving QUOTED keeps this version as a locked snapshot;
						// continue on the new version.
						window.location.href = '/portal/schedules/' + r.message.new_schedule_name;
						return;
					}
					location.reload();
				} else {
					frappe.msgprint({
						title: 'Error',
						indicator: 'red',
						message: r.message.error || 'Error updating status'
					});
				}
			}
		});
	});
}

function requestQuote() {
    PortalCommercial.quote(schedule_name, scheduleContext.schedule_modified);
}

function createSalesOrder() {
    PortalOrderIntake.open({schedule_name: schedule_name}).catch(function (error) { frappe.msgprint(frappe.utils.escape_html(error.message)); });
}

// FLOW-2: the header's next-step buttons and the overflow menu.
var scheduleActions = {ready: function () { changeStatus('READY'); }, draft: function () { changeStatus('DRAFT'); }, quote: requestQuote, order: createSalesOrder};
document.addEventListener('click', function (event) {
    var next = event.target.closest('[data-next-action]');
    if (next && !next.disabled && scheduleActions[next.dataset.nextAction]) {
        scheduleActions[next.dataset.nextAction]();
        return;
    }
    var item = event.target.closest('[data-schedule-menu]');
    if (!item) return;
    event.preventDefault();
    if (item.dataset.scheduleMenu === 'version') createNewVersion();
    if (item.dataset.scheduleMenu === 'status') changeStatus(item.dataset.status);
});
