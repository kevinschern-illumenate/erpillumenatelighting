/* The publication panel, status pill and hero image preview live in public/js/gallery_publication.js. */
frappe.ui.form.on("ilL-Webflow-Gallery", {
	refresh(frm) {
		return window.IllGalleryPublication.refresh(frm);
	},
	// Adding, removing or dragging rows can change which image is first.
	gallery_images_add(frm) {
		window.IllGalleryPublication.setHeroPreview(frm);
	},
	gallery_images_remove(frm) {
		window.IllGalleryPublication.setHeroPreview(frm);
	},
	gallery_images_move(frm) {
		window.IllGalleryPublication.setHeroPreview(frm);
	}
});

frappe.ui.form.on("ilL-Child-Webflow-Gallery-Image", {
	image(frm) {
		window.IllGalleryPublication.setHeroPreview(frm);
	},
	alt_text(frm) {
		window.IllGalleryPublication.setHeroPreview(frm);
	}
});
