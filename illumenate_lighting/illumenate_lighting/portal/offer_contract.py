"""Pure commercial offer snapshots and material conversion comparisons."""

HEADER_FIELDS = (
	"company",
	"currency",
	"selling_price_list",
	"price_list_currency",
	"conversion_rate",
	"plc_conversion_rate",
	"total",
	"net_total",
	"total_taxes_and_charges",
	"grand_total",
	"rounded_total",
	"discount_amount",
	"additional_discount_percentage",
	"apply_discount_on",
	"terms",
	"tc_name",
	"payment_terms_template",
	"customer_address",
	"shipping_address_name",
	"contact_person",
)
LINE_FIELDS = (
	"item_code",
	"item_name",
	"description",
	"qty",
	"uom",
	"conversion_factor",
	"rate",
	"amount",
	"net_rate",
	"net_amount",
	"discount_percentage",
	"discount_amount",
	"price_list_rate",
	"delivery_date",
	"ill_section_label",
	"ill_fixture_type",
	"additional_notes",
	"ill_schedule_line_id",
	"ill_configured_fixture",
	"ill_configured_tape_neon",
	"ill_configured_led_sheet",
	"ill_configured_group",
	"ill_bom",
	"ill_configuration_json",
)
TAX_FIELDS = (
	"charge_type",
	"account_head",
	"description",
	"rate",
	"tax_amount",
	"total",
	"included_in_print_rate",
	"row_id",
	"cost_center",
)


def commercial_snapshot(doc, *, customer):
	return {
		"schema_version": 1,
		"customer": customer,
		**{key: doc.get(key) for key in HEADER_FIELDS},
		"items": [{key: row.get(key) for key in LINE_FIELDS} for row in doc.get("items") or []],
		"taxes": [{key: row.get(key) for key in TAX_FIELDS} for row in doc.get("taxes") or []],
	}


def assert_conversion_matches(offer, order):
	"""Mapping may rename child rows; it must not change the accepted commercial scope."""
	from decimal import Decimal

	if (
		offer["customer"] != order["customer"]
		or offer["currency"] != order["currency"]
		or offer.get("terms") != order.get("terms")
	):
		raise ValueError("Customer, currency or terms changed during order conversion")
	if len(offer["items"]) != len(order["items"]):
		raise ValueError("Quoted rows were omitted or duplicated during conversion")
	for before, after in zip(offer["items"], order["items"], strict=True):
		for key in (
			"item_code",
			"uom",
			"ill_configured_fixture",
			"ill_configured_tape_neon",
			"ill_configured_led_sheet",
			"ill_bom",
		):
			if (before.get(key) or None) != (after.get(key) or None):
				raise ValueError(f"Quoted {key} changed during order conversion")
		for key in ("qty", "conversion_factor", "rate", "amount"):
			if abs(Decimal(str(before.get(key) or 0)) - Decimal(str(after.get(key) or 0))) > Decimal(
				"0.000001"
			):
				raise ValueError(f"Quoted {key} changed during order conversion")
	for key in ("grand_total", "net_total", "total_taxes_and_charges", "discount_amount"):
		if abs(Decimal(str(offer.get(key) or 0)) - Decimal(str(order.get(key) or 0))) > Decimal("0.000001"):
			raise ValueError(f"Quoted {key} changed during order conversion")
