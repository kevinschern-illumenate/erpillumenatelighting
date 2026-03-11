# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ilLAttributeFeedDirection(Document):
    """Feed Direction attribute for power feed location (End/Back)."""
    
    def validate(self):
        """Validate the feed direction."""
        # Ensure code is uppercase single character
        if self.code:
            self.code = self.code.upper().strip()
            if len(self.code) > 2:
                frappe.throw("Code should be 1-2 characters (e.g., 'E' for End, 'B' for Back)")
