"""Indexes for owner-bound sessions and verification reuse; safe on fresh installs."""

import frappe


def execute():
	frappe.db.add_index("ilL-Configurator-Session", ["session_token"], "finder_token")
	frappe.db.add_index("ilL-Configurator-Session", ["user", "status", "modified"], "finder_owner_status")
	frappe.db.add_index(
		"ilL-Product-Verification-Request", ["product", "finder_session", "schedule"], "finder_verification"
	)
	frappe.db.sql("UPDATE `tabilL-Configurator-Session` SET user=NULL WHERE user='Guest'")
	frappe.db.sql("UPDATE `tabilL-Configurator-Session` SET last_seen=modified WHERE last_seen IS NULL")
