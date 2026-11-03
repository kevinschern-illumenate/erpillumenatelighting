"""Legacy tape/neon URL; the main coordinator retains custom segments and reels."""

import frappe

from illumenate_lighting.illumenate_lighting.portal.page_scripts import script_version
from illumenate_lighting.templates.pages.configuration_routes import redirect_to_configurator

no_cache = 1


def get_context(context):
    context.configure_tape_js_version = script_version("configure_tape")
    category = frappe.form_dict.get("category", "LED Tape")
    redirect_to_configurator(category if category in {"LED Tape", "COB Tape", "LED Neon"} else "LED Tape")
