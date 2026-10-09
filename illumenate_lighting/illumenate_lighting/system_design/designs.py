# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Open, save, revise and copy ilL-System-Design records (WP-2.4).

The document contract (validation and build hash) lives in :mod:`.design_schema` (WP-2.2).
"""

from illumenate_lighting.illumenate_lighting.system_design.design_schema import (
	build_hash,
	canonical_json,
	validate_design_json,
)
