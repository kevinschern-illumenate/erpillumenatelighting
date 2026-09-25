"""Grant product authoring to named job roles, without assigning any users."""


def execute():
	from illumenate_lighting.portal_staff_permissions import apply_staff_permissions

	apply_staff_permissions()
