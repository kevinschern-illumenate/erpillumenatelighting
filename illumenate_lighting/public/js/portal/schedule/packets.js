// Schedule detail page (packets). Extracted verbatim from templates/pages/schedule.html (plan 2.1).

// Export functionality
function watchPacket(job, attempt) {
    attempt = attempt || 0;
    frappe.call({method: 'illumenate_lighting.illumenate_lighting.portal.packet_jobs.status', args: {job_name: job}, callback: function (r) {
        var value = r.message || {};
        loadExportHistory();
        if (value.status === 'COMPLETE') {
            frappe.show_alert({message: __('Packet complete. Download it from export history.'), indicator: 'green'});
        } else if (value.status === 'FAILED') {
            frappe.msgprint({title: __('Packet could not be generated'), message: '<p>' + frappe.utils.escape_html(value.error || __('Review the failed attempt and retry.')) + '</p>', indicator: 'red'});
        } else if (attempt < 30) {
            window.setTimeout(function () { watchPacket(job, attempt + 1); }, 3000);
        }
    }});
}
function generateSpecSubmittal(exportType) {
    frappe.call({method: 'illumenate_lighting.illumenate_lighting.api.spec_submittal.generate_spec_submittal_packet',
        args: {schedule_name: schedule_name, export_type: exportType, include_cover: true},
        callback: function (r) {
            if (!r.message || !r.message.success) { frappe.msgprint(__('Packet request failed. Retry when the connection is restored.')); return; }
            frappe.show_alert({message: __('Packet queued. You can leave this page and retrieve it from export history.'), indicator: 'blue'});
            watchPacket(r.message.export_job);
        }
    });
}
function retryPacket(job) {
    frappe.call({method: 'illumenate_lighting.illumenate_lighting.portal.packet_jobs.retry', args: {job_name: job}, callback: function (r) {
        if (r.message && r.message.success) watchPacket(r.message.export_job);
    }});
}
