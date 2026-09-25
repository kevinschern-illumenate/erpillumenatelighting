"""Additive ERP permissions for named portal staff jobs; never assigns users."""

import frappe

READ_MASTERS = (
	"Customer",
	"Contact",
	"Address",
	"Company",
	"Currency",
	"UOM",
	"Item",
	"Item Group",
	"Brand",
	"Price List",
	"Item Price",
	"BOM",
	"Warehouse",
	"Account",
	"Cost Center",
	"Payment Terms Template",
	"Terms and Conditions",
	"Sales Taxes and Charges Template",
	"Project",
)


def authoring_permissions(names):
	"""Explicit product-master families; no customer or commercial transactions."""
	managed = {
		name: {"read", "select", "write", "create", "report", "import", "export"}
		for name in names
		if name.startswith(("ilL-Spec-", "ilL-Attribute-", "ilL-Rel-"))
		or name
		in {
			"ilL-Fixture-Template",
			"ilL-Tape-Neon-Template",
			"ilL-LED-Sheet-Template",
			"ilL-Driver-Template",
			"ilL-Controller-Template",
			"ilL-Spec-Submittal-Mapping",
			"ilL-Neon-Submittal-Mapping",
			"ilL-LED-Sheet-Submittal-Mapping",
			"ilL-Driver-Submittal-Mapping",
			"ilL-Controller-Submittal-Mapping",
			"ilL-Item-Literature",
		}
	}
	for name in ("Item", "UOM", "Item Group", "Brand", "ilL-Webflow-Product", "ilL-Webflow-Category"):
		managed.setdefault(name, {"read", "select"})
	return managed


def apply_staff_permissions():
	from frappe.permissions import add_permission, update_permission_property

	for role in ("ilL Sales Review", "ilL Order Approver"):
		matrix = {doctype: {"read", "select"} for doctype in READ_MASTERS}
		for doctype in ("ilL-Project", "ilL-Project-Fixture-Schedule"):
			matrix[doctype] = {"read", "select", "write", "create", "report", "print"}
		matrix["Quotation"] = {
			"read",
			"select",
			"write",
			"create",
			"submit",
			"print",
			"report",
			"amend",
			"cancel",
		}
		matrix["Sales Order"] = {"read", "select", "write", "create", "print", "report"}
		if role == "ilL Order Approver":
			matrix["Sales Order"].update({"submit", "cancel", "amend"})
		for doctype, permissions in matrix.items():
			if not frappe.db.exists("DocType", doctype):
				continue
			if not frappe.db.exists(
				"Custom DocPerm", {"parent": doctype, "role": role, "permlevel": 0, "if_owner": 0}
			):
				add_permission(doctype, role, 0)
			# Only named job roles are managed; existing site roles/overrides remain.
			for ptype in (
				"read",
				"select",
				"write",
				"create",
				"submit",
				"print",
				"report",
				"amend",
				"cancel",
				"delete",
				"share",
				"export",
				"import",
				"email",
			):
				update_permission_property(doctype, role, 0, ptype, int(ptype in permissions), validate=False)
	frappe.clear_cache()
	apply_service_permissions()


def apply_service_permissions():
	"""Technical/support roles do not gain commercial document permissions."""
	from frappe.permissions import add_permission, update_permission_property

	matrices = {
		"ilL Engineering": {
			"ilL-Document-Request": {"read", "select", "write", "create", "report"},
			"Task": {"read", "select", "write", "create"},
			"ilL-Export-Job": {"read", "select", "report"},
		},
		"ilL Support": {"Issue": {"read", "select", "write", "create", "report"}},
		"ilL Operations": {"ilL-Document-Request": {"read", "select", "report"}},
		"ilL Integration": {"ilL-Portal-Delivery": {"read", "select", "report"}},
		"ilL Sales Review": {"ilL-Order-Intake": {"read", "select", "report"}},
		"ilL Order Approver": {"ilL-Order-Intake": {"read", "select", "report"}},
	}
	masters = authoring_permissions(
		frappe.get_all("DocType", filters={"istable": 0, "issingle": 0}, pluck="name")
	)
	matrices["ilL Engineering"].update(masters)
	matrices["ilL Catalog Publisher"] = {
		**masters,
		"ilL-Webflow-Product": {"read", "select", "write", "create", "report", "import", "export"},
		"ilL-Webflow-Category": {"read", "select", "write", "create", "report", "import", "export"},
		"ilL-Webflow-Brand": {"read", "select"},
	}
	matrices["ilL Integration"].update(
		{
			name: {"read", "select"}
			for name in ("ilL-Webflow-Brand", "ilL-Webflow-Product", "ilL-Webflow-Category")
		}
	)
	for role, matrix in matrices.items():
		if not frappe.db.exists("Role", role):
			frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(
				ignore_permissions=True
			)
		for doctype, permissions in matrix.items():
			if not frappe.db.exists("DocType", doctype):
				continue
			add_permission(doctype, role, 0)
			for ptype in (
				"read",
				"select",
				"write",
				"create",
				"report",
				"import",
				"delete",
				"share",
				"export",
				"submit",
				"cancel",
			):
				update_permission_property(doctype, role, 0, ptype, int(ptype in permissions), validate=False)
	frappe.clear_cache()
