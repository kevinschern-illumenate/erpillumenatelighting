# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ilLChildSpecGallery(Document):
	"""Extra spec sheet images on a template (owner, 2026-11-04): one row per image, placed in
	the spec sheet section named by Section. Spec sheets only; not sent to Webflow."""

	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		gallery_img: DF.Attach
		gallery_section: DF.Literal["Dimensions", "Accessories Dimensions", "Bend Diameter(s)", "Overview", "Emission Angle"]
		gallery_title: DF.Data | None
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
	# end: auto-generated types

	pass
