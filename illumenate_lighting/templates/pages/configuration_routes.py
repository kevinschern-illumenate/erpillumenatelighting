"""Compatibility redirects for former standalone configurator URLs."""

from urllib.parse import urlencode

import frappe


def redirect_to_configurator(category):
	params = {
		key: str(frappe.form_dict[key])
		for key in (
			"schedule",
			"line_idx",
			"line_key",
			"template",
			"product_slug",
			"moisture",
			"ip_rating",
			"light_type",
			"cct",
			"cct_low",
			"cct_high",
			"cri",
			"dimming",
			"mounting",
			"lens",
			"finish",
			"lumen_class",
		)
		if frappe.form_dict.get(key) is not None
	}
	params.update(category=category, mode="coordinator")
	frappe.local.flags.redirect_location = "/portal/configure?" + urlencode(params)
	raise frappe.Redirect
