# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class ilLWebflowConfiguratorCache(Document):
    """Cache for Webflow configurator cascading options."""
    
    def before_insert(self):
        """Set created timestamp."""
        if not self.created_at:
            self.created_at = now_datetime()
        if not self.last_accessed:
            self.last_accessed = now_datetime()
    
    def is_expired(self) -> bool:
        """Check if cache entry has expired."""
        if not self.expires_at:
            return True
        return now_datetime() > self.expires_at
    
    def record_hit(self):
        """Record a cache hit."""
        self.hit_count = (self.hit_count or 0) + 1
        self.last_accessed = now_datetime()
        self.save(ignore_permissions=True)


def cleanup_expired_cache():
    """Scheduled job to clean up expired cache entries."""
    frappe.db.delete(
        "ilL-Webflow-Configurator-Cache",
        {"expires_at": ["<", now_datetime()]}
    )
    frappe.db.commit()
