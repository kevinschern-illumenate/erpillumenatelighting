# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

import frappe


def get_context(context):
	context.title = "Dealer Access Required"
	context.no_cache = 1
