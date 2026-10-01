/* The website build of frappe.call (frappe/website/js/website.js) ignores the `error` option
 * that desk's frappe.call honours, so failure handlers in portal code (re-enabling buttons,
 * clearing spinners, showing a message) never ran: after a server-side validation error the
 * control stayed disabled until the page was reloaded. Mirror desk: call opts.error once for a
 * failed request, with the parsed body for a 417 (frappe.throw) and the jqXHR otherwise.
 * Desk defines frappe.request and keeps its own frappe.call untouched. */
(function () {
	if (typeof frappe === 'undefined' || typeof frappe.call !== 'function' || frappe.request || frappe.call.illErrorCallbacks) return;
	const webCall = frappe.call;
	frappe.call = function (opts) {
		const request = webCall.apply(this, arguments);
		const onError = opts && typeof opts === 'object' && typeof opts.error === 'function' ? opts.error : null;
		if (onError && request && typeof request.fail === 'function') {
			request.fail(function (xhr) {
				let payload = xhr;
				if (xhr && xhr.status === 417) {
					payload = xhr.responseJSON;
					if (!payload) {
						try { payload = JSON.parse(xhr.responseText); } catch (e) { payload = xhr.responseText; }
					}
				}
				try { onError(payload); } catch (e) { console.error(e); }
			});
		}
		return request;
	};
	frappe.call.illErrorCallbacks = true;
})();
