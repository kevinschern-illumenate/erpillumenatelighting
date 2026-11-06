// Webflow approvals and failures as browser notifications (plan 4.19, D83).
// webflow_notify.notify() rings the Desk bell (Notification Log, emailed per Notification
// Settings) and sends this realtime event to each recipient. While ERPNext is open in a tab, it
// shows an in-page alert and, once the browser allows notifications, a system notification.
(function (root) {
	const EVENT = "ill_webflow_alert";

	function browserNotify(data) {
		const Notice = root.Notification;
		if (!Notice) return;
		const open = () => {
			const notice = new Notice(data.title || "Webflow", { body: data.body || "", tag: data.route || EVENT });
			notice.onclick = () => {
				root.focus && root.focus();
				if (data.route && root.frappe && root.frappe.set_route) root.frappe.set_route(data.route);
				notice.close();
			};
		};
		if (Notice.permission === "granted") {
			open();
		} else if (Notice.permission === "default" && Notice.requestPermission) {
			Promise.resolve(Notice.requestPermission()).then(choice => choice === "granted" && open()).catch(() => {});
		}
	}

	function handle(data) {
		data = data || {};
		if (root.frappe && root.frappe.show_alert) {
			root.frappe.show_alert({ message: root.frappe.utils.escape_html(data.title || ""), indicator: "orange" }, 10);
		}
		try {
			browserNotify(data);
		} catch (error) {
			// A browser that refuses notifications still has the bell and the email.
		}
	}

	function listen() {
		if (root.frappe && root.frappe.realtime && root.frappe.realtime.on) {
			root.frappe.realtime.off && root.frappe.realtime.off(EVENT, handle);
			root.frappe.realtime.on(EVENT, handle);
		}
	}

	root.illWebflowAlerts = { handle, listen, EVENT };
	// frappe.realtime has no socket until the Desk starts; "app_ready" fires after that.
	if (root.$ && root.document) root.$(root.document).on("app_ready", listen);
	listen();
})(typeof window !== "undefined" ? window : globalThis);
