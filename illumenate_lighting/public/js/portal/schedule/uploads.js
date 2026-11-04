// Schedule detail page (uploads). Extracted verbatim from templates/pages/schedule.html (plan 2.1).
// File upload helper function
async function uploadFile(fileInput, callback) {
    try {
        const ids = await PortalUploads.uploadAll(fileInput, 'ilL-Project-Fixture-Schedule', schedule_name);
        callback(ids[0] || null);
    } catch (error) {
        frappe.msgprint({title: __('File not saved'), indicator: 'red', message: frappe.utils.escape_html(error.message)});
        // Do not save the line or replace its previous file after failure.
    }
}
