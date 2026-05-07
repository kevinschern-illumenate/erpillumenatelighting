"""Rebuild configurator_options on LED Neon Webflow products.

The LED Neon configurator now emits two separate options — ``Start Feed
Direction`` and ``End Feed Direction`` — derived from each tape/neon
template allowed-option's ``feed_position`` (Both | Start | End).

This patch re-saves every configurable LED Neon ilL-Webflow-Product so the
``before_save`` hook repopulates ``configurator_options`` with the split
entries and flags them as Pending sync.
"""

from __future__ import annotations

import frappe


def execute() -> None:
	products = frappe.get_all(
		"ilL-Webflow-Product",
		filters={"product_type": "LED Neon", "is_configurable": 1},
		pluck="name",
	)
	for name in products:
		try:
			doc = frappe.get_doc("ilL-Webflow-Product", name)
			doc.save(ignore_permissions=True)
		except Exception:
			frappe.log_error(
				title="split_neon_feed_direction_configurator_options",
				message=frappe.get_traceback(),
			)
	frappe.db.commit()
