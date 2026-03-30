# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt


def allow_blank_schedule_date(doc, method=None):
    """Suppress ERPNext's BuyingController.validate_schedule_date() so that
    Purchase Orders can be saved and submitted without a 'Required By' date.

    The Property Setter patch (make_po_schedule_date_optional) removes the UI
    red asterisk; this hook prevents the identical server-side check from
    throwing a validation error when the field is blank.
    """
    doc.validate_schedule_date = lambda: None
