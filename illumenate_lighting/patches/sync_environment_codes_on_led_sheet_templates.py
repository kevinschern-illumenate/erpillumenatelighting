"""Give LED Sheet templates the current Environment Rating codes.

Sheet templates copy each Environment Rating's code onto their option rows, and the
Sheet part number and panel matching read that copy. The ratings moved from I/D/O
to 20/54/67 before the copies followed the rating, so existing templates still
carry the old codes. Re-syncs those, and any Part Number Builder still behind.
"""

import frappe

from illumenate_lighting.illumenate_lighting.api.environment_codes import propagate


def execute():
	propagate()
	frappe.db.commit()
