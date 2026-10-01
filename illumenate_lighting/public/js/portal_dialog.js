/* Portal pages get frappe.ui.Dialog from frappe-web.bundle.js but not the form controls
 * that render its fields: frappe.ui.form.make_control lives in controls.bundle.js, which
 * only desk loads. Any dialog with fields fails on the portal with
 * "frappe.ui.form.make_control is not a function" unless the bundle is loaded first. */
window.PortalDialog = {
	ready() {
		if (typeof frappe.ui.form?.make_control === 'function') return Promise.resolve();
		if (!this._loading) {
			this._loading = new Promise((resolve, reject) => {
				// frappe.require on the website never settles if the script fails to load.
				const timer = setTimeout(() => reject(new Error(__('The form could not be loaded. Reload the page and retry.'))), 20000);
				frappe.require('controls.bundle.js', () => {
					clearTimeout(timer);
					if (typeof frappe.ui.form?.make_control === 'function') resolve();
					else reject(new Error(__('The form could not be loaded. Reload the page and retry.')));
				});
			}).catch(error => { this._loading = null; throw error; });
		}
		return this._loading;
	},
	async create(options) {
		await this.ready();
		return new frappe.ui.Dialog(options);
	}
};
