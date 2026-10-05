"""Catalog Publishers create catalog masters with their own permissions."""


def execute():
	from illumenate_lighting.portal_staff_permissions import apply_staff_permissions

	apply_staff_permissions()
