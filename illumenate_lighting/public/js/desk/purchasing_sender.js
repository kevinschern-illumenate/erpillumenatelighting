// Purchasing documents email from the shared purchasing mailbox (email_templates/purchasing_mail.py).
// The server sends from the mailbox whatever From is picked; this makes the composer show it, and
// use the mailbox's signature, instead of preselecting the buyer's own Email Account.
// frappe.boot.ill_purchasing_mail = { email, doctypes, payment_entry } exists only once the
// mailbox is set up and "Send All Purchasing Email From This Account" is on.
(function (root) {
	function mailbox(composer) {
		const frappe = root.frappe;
		const cfg = frappe && frappe.boot && frappe.boot.ill_purchasing_mail;
		if (!cfg || !cfg.email) return null;
		const doc = composer.doc || (composer.frm && composer.frm.doc) || {};
		const doctype = doc.doctype || (composer.frm && composer.frm.doctype) || composer.doctype;
		if ((cfg.doctypes || []).includes(doctype)) return cfg.email;
		if (doctype === cfg.payment_entry && doc.party_type === "Supplier") return cfg.email;
		return null;
	}

	function patch() {
		const views = root.frappe && root.frappe.views;
		const Base = views && views.CommunicationComposer;
		if (!Base || Base.ill_purchasing_sender) return Boolean(Base);
		const Composer = class extends Base {
			get_fields() {
				const fields = super.get_fields();
				const email = mailbox(this);
				// The From list is the buyer's User Emails; pick the mailbox when it is one of them.
				const listed = email && (this.user_email_accounts || []).find((a) => String(a).toLowerCase() === email);
				if (listed) this.sender = listed;
				return fields;
			}

			set_content(sender_email) {
				// With no From passed, Frappe reads the default outgoing account's signature.
				const email = mailbox(this);
				const ours = email && String(this.sender || "").toLowerCase() === email;
				return super.set_content(sender_email || (ours ? this.sender : sender_email));
			}
		};
		Composer.ill_purchasing_sender = true;
		views.CommunicationComposer = Composer;
		return true;
	}

	root.illPurchasingSender = { mailbox, patch };
	// The composer is defined by Frappe's desk bundle; "app_ready" fires after it loads.
	if (!patch() && root.$ && root.document) root.$(root.document).on("app_ready", patch);
})(typeof window !== "undefined" ? window : globalThis);
