/* The publication panel and buttons live in public/js/gallery_publication.js. */
frappe.ui.form.on("ilL-Webflow-Gallery", {
	refresh(frm) {
		return window.IllGalleryPublication.refresh(frm);
	}
});
