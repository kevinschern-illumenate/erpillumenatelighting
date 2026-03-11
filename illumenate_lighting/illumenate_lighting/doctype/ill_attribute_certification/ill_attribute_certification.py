# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class ilLAttributeCertification(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF
		from illumenate_lighting.illumenate_lighting.doctype.ill_child_certification_applies_to.ill_child_certification_applies_to import ilLChildCertificationAppliesTo

		applies_to_types: DF.Table[ilLChildCertificationAppliesTo]
		badge_image: DF.AttachImage | None
		certification_body: DF.Data | None
		certification_code: DF.Data
		certification_name: DF.Data
		description: DF.SmallText | None
		is_active: DF.Check
	# end: auto-generated types

	pass
