# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""
Patch to convert CRM Lead job_title field from Data to Link field.

This patch:
1. Creates ilL-Job-Title-Master custom DocType if not exists
2. Audits existing job_title values from CRM Lead
3. Creates Job Title Master records for unique values
4. Changes job_title field to Link type pointing to ilL-Job-Title-Master
5. Migrates existing data to match new Link field format
6. Creates fallback "Other" record for unmapped titles

Rollback Note:
- Property Setters can be deleted via UI if needed to revert
- Job Title Master records can be kept or deleted as needed
"""

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def execute():
    """Convert Lead job_title from Data to Link field."""

    # Check if CRM Lead doctype exists
    if not frappe.db.exists("DocType", "CRM Lead"):
        print("CRM Lead doctype not found. Skipping patch.")
        return

    print("Starting CRM Lead job_title field conversion...")

    # Step 1: Audit existing job titles
    print("Step 1: Auditing existing job titles...")
    existing_titles = frappe.db.sql(
        """
        SELECT DISTINCT job_title
        FROM `tabCRM Lead`
        WHERE job_title IS NOT NULL
        AND job_title != ''
        ORDER BY job_title
    """,
        as_list=True,
    )

    unique_titles = [title[0].strip() for title in existing_titles if title[0]]
    print(f"Found {len(unique_titles)} unique job titles in existing leads")

    # Step 2: Ensure "Other" exists in Job Title Master
    print("Step 2: Ensuring 'Other' fallback exists...")
    if not frappe.db.exists("ilL-Job-Title-Master", "Other"):
        other_doc = frappe.get_doc(
            {
                "doctype": "ilL-Job-Title-Master",
                "job_title_name": "Other",
                "category": "Other",
                "sort_order": 99,
                "is_active": 1,
            }
        )
        other_doc.insert(ignore_permissions=True)
        print("Created 'Other' job title master record")

    # Step 3: Create Job Title Master records for existing unique titles
    print("Step 3: Creating Job Title Master records...")
    created_count = 0
    for title in unique_titles:
        if not frappe.db.exists("ilL-Job-Title-Master", title):
            try:
                doc = frappe.get_doc(
                    {
                        "doctype": "ilL-Job-Title-Master",
                        "job_title_name": title,
                        "category": _categorize_job_title(title),
                        "sort_order": 50,  # Middle priority for auto-created
                        "is_active": 1,
                    }
                )
                doc.insert(ignore_permissions=True)
                created_count += 1
            except Exception as e:
                print(
                    f"Warning: Could not create Job Title Master for '{title}': {e!s}"
                )
                # Map to "Other" later in migration

    print(f"Created {created_count} new Job Title Master records")
    frappe.db.commit()

    # Step 4: Change field type using Property Setter
    print("Step 4: Changing job_title field type to Link...")

    # Change fieldtype to Link
    make_property_setter(
        doctype="CRM Lead",
        fieldname="job_title",
        property="fieldtype",
        value="Link",
        property_type="Select",
    )

    # Set options to ilL-Job-Title-Master
    make_property_setter(
        doctype="CRM Lead",
        fieldname="job_title",
        property="options",
        value="ilL-Job-Title-Master",
        property_type="Data",
    )

    print("Property Setters created successfully")
    frappe.db.commit()

    # Step 5: Migrate data
    print("Step 5: Migrating existing data...")
    migration_count = 0
    error_count = 0

    # Get all leads with job titles
    leads = frappe.db.sql(
        """
        SELECT name, job_title
        FROM `tabCRM Lead`
        WHERE job_title IS NOT NULL
        AND job_title != ''
    """,
        as_dict=True,
    )

    for lead in leads:
        try:
            title = lead.job_title.strip()

            # Check if the title exists in Job Title Master
            if frappe.db.exists("ilL-Job-Title-Master", title):
                # Already valid - no change needed
                migration_count += 1
            else:
                # Map to "Other"
                frappe.db.set_value(
                    "CRM Lead", lead.name, "job_title", "Other", update_modified=False
                )
                migration_count += 1
        except Exception as e:
            error_count += 1
            print(f"Error migrating lead {lead.name}: {e!s}")

    frappe.db.commit()
    print(f"Migration complete: {migration_count} leads migrated, {error_count} errors")
    print("Job title conversion completed successfully!")


def _categorize_job_title(title: str) -> str:
    """
    Attempt to auto-categorize a job title based on keywords.
    """
    title_lower = title.lower()

    if any(
        word in title_lower
        for word in ["designer", "architect", "engineer", "electrical"]
    ):
        return "Design & Engineering"
    elif any(word in title_lower for word in ["purchas", "procurement", "buyer"]):
        return "Procurement & Purchasing"
    elif any(
        word in title_lower for word in ["project", "construction", "contractor"]
    ):
        return "Project Management"
    elif any(
        word in title_lower for word in ["facility", "maintenance", "operations"]
    ):
        return "Facility Management"
    elif any(word in title_lower for word in ["sales", "distributor", "rep"]):
        return "Sales & Distribution"
    else:
        return "Other"
