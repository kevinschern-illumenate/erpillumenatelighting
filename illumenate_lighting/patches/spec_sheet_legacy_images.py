# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Move custom_image_* values that are already ERPNext Files into Webflow Product spec_assets.

Local (Mac) paths and external URLs are left in place and listed by
``api.spec_sheets.legacy_images.report`` for marketing to upload.
"""

import frappe

from illumenate_lighting.illumenate_lighting.api.spec_sheets.legacy_images import run


def execute():
	result = run(dry_run=False)
	frappe.db.commit()
	print(
		f"Spec sheets: moved {result['moved']} legacy images into spec_assets; "
		f"{len(result['issues'])} legacy image values still need uploading "
		"(see api.spec_sheets.legacy_images.report)"
	)
