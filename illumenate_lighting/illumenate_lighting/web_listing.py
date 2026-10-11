"""Product Status on the product templates.

Product Status says where a template is offered in ERPNext and the portal, separately
from whether its Webflow Product is live on the website. ``is_active``, which most of
the code reads, follows it: Active and ERPNext Only are active, the rest are not.
"""

from illumenate_lighting.illumenate_lighting.web_listing_schema import ACTIVE_STATUSES


def apply_product_status(doc):
	"""Keep Product Status and is_active in step; call from each template's validate().

	A status that is set wins. Code that only sets ``is_active`` (imports, the kit
	generator) still works: the status follows it, keeping Discontinued and Archived when
	the template stays inactive. A new template saved with ``is_active`` off and the
	default Active status is inactive: the status there is only the field default.
	"""
	status = getattr(doc, "product_status", None)
	before = doc.get_doc_before_save() if hasattr(doc, "get_doc_before_save") else None
	status_changed = not before or before.get("product_status") != status
	active_changed = not before or bool(before.get("is_active")) != bool(getattr(doc, "is_active", 0))
	if not before and status == "Active" and not getattr(doc, "is_active", 0):
		status = None
	if not status or (active_changed and not status_changed):
		if getattr(doc, "is_active", 0):
			status = status if status in ACTIVE_STATUSES else "Active"
		else:
			status = status if status and status not in ACTIVE_STATUSES else "Draft"
	doc.product_status = status
	doc.is_active = int(status in ACTIVE_STATUSES)
