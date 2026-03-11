# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe
import json
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, add_to_date


class ilLWebflowSession(Document):
    """Webflow configurator session for tracking user configurations."""
    
    def before_insert(self):
        """Set defaults before insert."""
        if not self.session_id:
            self.session_id = frappe.generate_hash(length=32)
        
        if not self.created_at:
            self.created_at = now_datetime()
        
        if not self.expires_at:
            # Sessions expire after 24 hours by default
            self.expires_at = add_to_date(now_datetime(), hours=24)
        
        if not self.status:
            self.status = "Active"
    
    def validate(self):
        """Validate session data."""
        # Validate configuration JSON
        if self.configuration_json:
            try:
                if isinstance(self.configuration_json, str):
                    json.loads(self.configuration_json)
            except json.JSONDecodeError:
                frappe.throw(_("Invalid configuration JSON"))
    
    def is_expired(self) -> bool:
        """Check if session has expired."""
        if not self.expires_at:
            return False
        return now_datetime() > self.expires_at
    
    def is_active(self) -> bool:
        """Check if session is still active."""
        return self.status == "Active" and not self.is_expired()
    
    def get_configuration(self) -> dict:
        """Get configuration as dictionary."""
        if not self.configuration_json:
            return {}
        
        if isinstance(self.configuration_json, dict):
            return self.configuration_json
        
        try:
            return json.loads(self.configuration_json)
        except json.JSONDecodeError:
            return {}
    
    def set_configuration(self, config: dict):
        """Set configuration from dictionary."""
        self.configuration_json = json.dumps(config)
    
    def mark_converted(self, user: str = None):
        """Mark session as converted."""
        self.status = "Converted"
        self.converted_at = now_datetime()
        if user:
            self.converted_to_user = user
        self.save(ignore_permissions=True)
    
    def mark_expired(self):
        """Mark session as expired."""
        self.status = "Expired"
        self.save(ignore_permissions=True)
    
    def extend_expiry(self, hours: int = 24):
        """Extend session expiry."""
        self.expires_at = add_to_date(now_datetime(), hours=hours)
        self.save(ignore_permissions=True)


def cleanup_expired_sessions():
    """Scheduled job to clean up expired sessions."""
    # Mark expired sessions
    frappe.db.sql("""
        UPDATE `tabilL-Webflow-Session`
        SET status = 'Expired'
        WHERE status = 'Active'
        AND expires_at < NOW()
    """)
    
    # Delete sessions older than 7 days
    cutoff = add_to_date(now_datetime(), days=-7)
    frappe.db.delete(
        "ilL-Webflow-Session",
        {"created_at": ["<", cutoff], "status": ["in", ["Expired", "Abandoned"]]}
    )
    
    frappe.db.commit()
