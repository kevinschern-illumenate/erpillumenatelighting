"""Copy a schedule line's customer intent without its calculated artifacts or prices.

Shared by reorder/replacement (``order_changes.fork_schedule``) and copying lines to
another schedule (``line_copy.copy_lines``): a copied configured line keeps its
canonical request and must be reconfigured against current engineering and pricing.
"""

from illumenate_lighting.illumenate_lighting.api.configuration_contract import canonical_json

ARTIFACT_FIELDS = (
	"configured_group",
	"configured_fixture",
	"configured_tape_neon",
	"configured_led_sheet",
	"ill_item_code",
	"item_code",
	"bom_no",
	"ill_bom",
	"unit_price",
	"extended_price",
	"manufacturable_length_mm",
	"total_watts",
	"total_lumens",
	"manufacturable_length_in",
)
RECONFIGURE_NOTE = "Reconfigure this line against current engineering and pricing before requesting an order."


def intent_values(line, exclude):
	from illumenate_lighting.illumenate_lighting.portal.configuration_reopen import for_line

	values = {key: value for key, value in line.as_dict().items() if key not in exclude}
	configured = any(
		values.get(key)
		for key in (
			"configured_group",
			"configured_fixture",
			"configured_tape_neon",
			"configured_led_sheet",
		)
	)
	# Older kit/tape rows can carry generated artifacts only inside selection JSON.
	configured = configured or bool(
		values.get("variant_selections") and values.get("manufacturer_type") == "ILLUMENATE"
	)
	if configured:
		request = for_line(line)
		values["ill_configurator_request"] = canonical_json(request) if request else None
		# Only intent survives a copy. Legacy selection JSON may contain
		# generated Item/BOM links that would bypass current engineering.
		values["variant_selections"] = None
		values["configuration_status"] = "Pending"
		for key in ARTIFACT_FIELDS:
			if key in values:
				values[key] = None
		values["notes"] = ((values.get("notes") or "") + "\n" + RECONFIGURE_NOTE).strip()
	return values
