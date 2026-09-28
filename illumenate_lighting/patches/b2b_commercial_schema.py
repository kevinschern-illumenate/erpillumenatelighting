"""Repair commercial fields omitted from earlier successful portal migrations."""


def execute():
	from illumenate_lighting.patches.b2b_commercial_lineage import execute as install_commercial_fields

	# A new patch identity is required: existing sites already recorded the old
	# lineage patch as complete. This same setup runs from after_install.
	install_commercial_fields()
