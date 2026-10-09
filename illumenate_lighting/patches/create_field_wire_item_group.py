"""Field wire is sold as Items (System Designer D7, WP-1.4).

Creates the "Field Wire" Item Group and the UOMs wire Items use: Foot for wire sold by length and
Spool for wire sold by the spool. Existing records are left as they are.
"""

import frappe

from illumenate_lighting.illumenate_lighting.system_design.wire_import import ensure_wire_masters


def execute():
	ensure_wire_masters()
	frappe.db.commit()
