"""Commonly stocked field wire for the System Designer and the CAD toolkit (PRD question 6).

``python -m tools.seed_imports.field_wire_common`` writes ``tools/seed_imports/field_wire_common.csv``
in the column layout of ``field_wire_TEMPLATE.csv``. Import it from Desk with the System Designer's
field wire import (``system_design.wire_import.import_field_wire``): run the dry run first; the real
run creates the Items (Item Group "Field Wire", sold per foot) and the ``ilL-Spec-Wire`` records.

Data rules:

- Every row names the product family and cites the manufacturer or distributor sheet it came from
  (``source_reference``). Values the sources disagreed on use the conservative one (lower temperature
  rating, for example) and say so in the row's notes below; values no source gave are left blank.
- Conductor DC resistance (``resistance_ohm_per_kft``) is NEC Chapter 9 Table 8 (uncoated copper,
  75 C) for 18 AWG and larger, and the manufacturer's measured DCR for 22-24 AWG data cable.
- Building wire ampacity is NEC 310.16 (the engine applies it); Class 2 cable uses the 402.5 fallback.
- ``is_verified`` is 0 on every row: engineering checks each sheet before the designer relies on it.
- No prices: add selling Item Prices after import (the readiness report lists wire without one).
"""

import csv
import io
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parent / "field_wire_common.csv"
COLUMNS = (
	"item_code",
	"item_name",
	"wire_name",
	"category",
	"applications",
	"conductors",
	"listing",
	"rated_v",
	"temp_rating_c",
	"plenum",
	"riser",
	"wet",
	"direct_burial",
	"sunlight_resistant",
	"shielded",
	"impedance_ohm",
	"resistance_ohm_per_kft",
	"ampacity_a",
	"ampacity_basis",
	"od_in",
	"riser_label",
	"sales_uom_mode",
	"spool_length_ft",
	"is_verified",
	"source_reference",
	"is_active",
)

# NEC Chapter 9 Table 8, ohm per 1000 ft at 75 C, uncoated copper.
TABLE8_STRANDED = {"18": 7.95, "16": 4.99, "14": 3.14, "12": 1.98, "10": 1.24, "8": 0.778}
TABLE8_SOLID = {"18": 7.77, "16": 4.89, "14": 3.07, "12": 1.93, "10": 1.21, "8": 0.764}

SW_13060 = "Southwire SPEC 13060 multi-conductor CL3R/FPLR/CMR/CMG non-shielded, 300 V (sheet lists 60 C and 75 C revisions; 60 C used) https://www.southwire.com/wire-cable/low-voltage-cable/multi-conductor-cl3r-fplr-cmr-cmg-non-shielded/p/R40049-1A"
SW_CL3P = "Southwire 16 AWG 2/C unshielded FPLP/CMP/CL3P (57561902), 300 V, 75 C https://rexelusa.com/p/495145/southwire/16-awg-2-c-unshielded-fplp-cmp-cl3p-cable/032886881442/57561902"
SW_LVLL = "Southwire SPEC 70827 low voltage landscape lighting cable, UL Subj 1493, 150 V, -20 to 60 C, direct burial, sunlight resistant https://cdn.shopify.com/s/files/1/0517/1760/3528/files/SPEC70827-ULEC-LVLL.pdf"
SW_NMB = "Southwire SPEC 10028 Romex SIMpull NM-B, 600 V, 90 C insulation, ampacity at 60 C https://cabletechsupport.southwire.com/tile/42/spec/10028/?country=US"
SW_THHN = "Southwire SPEC 10000 SIMpull THHN/THWN-2 copper, 600 V, 90 C dry; sizes 14-10 AWG are THWN (wet 75 C); ampacity per NEC 310.16 https://southwire.com/wire-cable/building-wire/simpull-sup-sup-thhn-thwn-2-copper/p/SPEC10000"
SW_MCAP = "Southwire SPEC 60240 MC-AP Type MC, THHN/THWN conductors, 600 V, 90 C, 0.538 in over armor for 12-2 https://cabletechsupport.southwire.com/tile/29/spec/60240/?country=US"
SW_SHIELD = "Southwire 95214 18/2 stranded shielded CMR/CL3R/FPLR, 300 V, 75 C, 0.161 in OD, 24 AWG drain https://www.gexpro.com/p/409314/southwire/18-2-cmr-cl3r-shielded-multi-conductor-cable/029892432591/952140509"
SW_10034 = "Southwire SPEC 10034 Class 2 lighting control and dimming cable, CL2, 150 V, solid copper, purple/gray (temperature not stated; 60 C used) https://cabletechsupport.southwire.com/tile/39/spec/10034/?country=US"
SW_GEN41 = "Southwire Genesis GEN41 16 solid 2/C CMP/FT6 low voltage dimming cable, plenum (voltage and temperature from the CMP listing: 300 V, 75 C) https://www.southwire.com/wire-cable/genesis-cable/low-voltage-dimming-cable-plenum/p/GEN41"
BELDEN_9841 = "Belden 9841 RS-485/DMX512, 1 pair 24 AWG 7x32 tinned copper, foil+braid shield, CM 300 V, 120 ohm, 0.232 in OD, DCR 24 ohm/1000 ft https://belden.com/products/Cable/Electronic-Wire-Cable/RS-485-Cable/9841"
BELDEN_9842 = "Belden 9842 RS-485/DMX512, 2 pair 24 AWG 7x32 tinned copper, foil+braid shield, CM 300 V, -30 to 80 C, 120 ohm https://www.belden.com/products/Cable/Electronic-Wire-Cable/RS-485-Cable/9842"
BELDEN_82841 = "Belden 82841 plenum counterpart of 9841 (CMP), 1 pair 24 AWG, 120 ohm https://www.belden.com/products/Cable/Electronic-Wire-Cable/RS-485-Cable/82841"
BELDEN_2412 = "Belden 2412 Category 6+ U/UTP, 4 pair 23 AWG solid bare copper, CMR, 0.224 in OD, DCR max 24 ohm/1000 ft https://www.belden.com/products/cable/ethernet-cable/category-6-cable/2412"
BELDEN_2413 = "Belden 2413 Category 6+ U/UTP plenum counterpart of 2412 (CMP), 4 pair 23 AWG solid, DCR max 24 ohm/1000 ft https://www.belden.com/products/cable/ethernet-cable/category-6-cable/2413"
LUTRON_QS = "Lutron GRX-CBL-346S QS link cable, CL3R/CMR cULus: 2x18 AWG common/power, 2x22 AWG MUX data, 24 AWG drain (resistance given is the 18 AWG power pair) https://www.stoneway.com/resources/Lutron/GRX-CBL-46L-500/Specification-Sheet.pdf"
LUTRON_QS_P = "Lutron GRX-PCBL-346S plenum QS link cable, same construction and distances as GRX-CBL-346S (resistance given is the 18 AWG power pair) https://www.stoneway.com/resources/Lutron/GRX-PCBL-46L-500/Specification-Sheet.pdf"


def class2(
	awg, count, listing, source, *, plenum=False, temp=60, roles=None, od=None, apps="class2-dc", label=None
):
	conductors = roles or f"{count}x{awg} Cu stranded power"
	kind = "CL3P" if plenum else "CL3R"
	return {
		"item_code": f"FW-{kind}-{awg}-{count}",
		"item_name": f"{awg}/{count} {kind} stranded copper Class 2 cable",
		"wire_name": f"{awg}/{count} {kind} stranded (Class 2 power)",
		"category": "class2-power",
		"applications": apps,
		"conductors": conductors,
		"listing": listing,
		"rated_v": 300,
		"temp_rating_c": temp,
		"plenum": plenum,
		"riser": True,
		"resistance_ohm_per_kft": TABLE8_STRANDED[awg],
		"ampacity_basis": "402.5 fallback",
		"od_in": od,
		"riser_label": label or f"{count} x #{awg} {kind}",
		"source_reference": source,
	}


LVLL_STOCK = {"16": "552131", "14": "552132", "12": "552134", "10": "552135", "8": "552136"}


def landscape(awg):
	return {
		"item_code": f"FW-LVLL-{awg}-2",
		"item_name": f"{awg}/2 low voltage landscape lighting cable, direct burial",
		"wire_name": f"{awg}/2 LVLL direct burial (Southwire stock {LVLL_STOCK[awg]})",
		"category": "landscape",
		"applications": "landscape-ac,class2-dc",
		"conductors": f"2x{awg} Cu stranded power",
		"listing": "LVLL UL Subj 1493",
		"rated_v": 150,
		"temp_rating_c": 60,
		"wet": True,
		"direct_burial": True,
		"sunlight_resistant": True,
		"resistance_ohm_per_kft": TABLE8_STRANDED[awg],
		"ampacity_basis": "402.5 fallback",
		"riser_label": f"2 x #{awg} LVLL direct burial",
		"source_reference": SW_LVLL,
	}


def raceway_set(awg):
	return {
		"item_code": f"FW-THHN-{awg}-SET",
		"item_name": f"#{awg} THHN/THWN raceway set (2 + ground), per foot of run",
		"wire_name": f"THHN/THWN #{awg} raceway set",
		"category": "building-wire",
		"applications": "lv-branch",
		"conductors": f"2x{awg} Cu stranded power; 1x{awg} Cu stranded ground (green)",
		"listing": "THHN/THWN",
		"rated_v": 600,
		"temp_rating_c": 90,
		"wet": True,
		"resistance_ohm_per_kft": TABLE8_STRANDED[awg],
		"ampacity_basis": "310.16",
		"riser_label": f"2 x #{awg} + #{awg} G THHN/THWN",
		"source_reference": SW_THHN,
	}


def nmb(awg, od=None):
	return {
		"item_code": f"FW-NMB-{awg}-2G",
		"item_name": f"{awg}/2 NM-B with ground",
		"wire_name": f"NM-B {awg}/2 with ground (Romex SIMpull)",
		"category": "building-wire",
		"applications": "lv-branch",
		"conductors": f"2x{awg} Cu solid power; 1x{awg} Cu solid ground",
		"listing": "NM-B",
		"rated_v": 600,
		"temp_rating_c": 60,
		"resistance_ohm_per_kft": TABLE8_SOLID[awg],
		"ampacity_basis": "310.16",
		"od_in": od,
		"riser_label": f"{awg}/2 w/G NM-B",
		"source_reference": SW_NMB,
	}


ROWS = [
	# --- Class 2 power to tape and neon (indoor, in-wall riser and plenum) --------------------------
	class2("18", 2, "CL3R/CMR/FPLR", SW_13060),
	class2("16", 2, "CL3R/CMR/FPLR", SW_13060),
	class2("14", 2, "CL3R/CMR/FPLR", SW_13060),
	class2("12", 2, "CL3R/CMR/FPLR", SW_13060),
	class2("18", 2, "CL3P/CMP/FPLP", SW_CL3P, plenum=True, temp=75),
	class2("16", 2, "CL3P/CMP/FPLP", SW_CL3P, plenum=True, temp=75),
	class2("14", 2, "CL3P/CMP/FPLP", SW_CL3P, plenum=True, temp=75),
	class2("12", 2, "CL3P/CMP/FPLP", SW_CL3P, plenum=True, temp=75),
	# Multi-channel tape: RGB (common + 3 channels) and RGBW (common + 4), and pixel tape (V+, data, GND).
	class2(
		"18",
		4,
		"CL3R/CMR/FPLR",
		SW_13060,
		roles="1x18 Cu stranded power; 3x18 Cu stranded channel",
		apps="class2-dc-multichannel",
		label="4 x #18 CL3R (common + RGB)",
	),
	class2(
		"16",
		4,
		"CL3R/CMR/FPLR",
		SW_13060,
		roles="1x16 Cu stranded power; 3x16 Cu stranded channel",
		apps="class2-dc-multichannel",
		label="4 x #16 CL3R (common + RGB)",
	),
	class2(
		"18",
		5,
		"CL3R/CMR/FPLR",
		SW_13060,
		roles="1x18 Cu stranded power; 4x18 Cu stranded channel",
		apps="class2-dc-multichannel",
		label="5 x #18 CL3R (common + RGBW)",
	),
	class2(
		"18",
		3,
		"CL3R/CMR/FPLR",
		SW_13060 + "; R40048-1A 0.171 in OD",
		roles="2x18 Cu stranded power; 1x18 Cu stranded signal",
		od=0.171,
		apps="spi-data,class2-dc",
		label="3 x #18 CL3R (V+, data, GND)",
	),
	# --- Dimming signal --------------------------------------------------------------------------------
	{
		"item_code": "FW-CL2-16-2-0-10V",
		"item_name": "16/2 CL2 0-10 V dimming cable, purple/gray",
		"wire_name": "16/2 CL2 0-10 V dimming (purple/gray)",
		"category": "control",
		"applications": "0-10v",
		"conductors": "2x16 Cu solid signal (purple/gray)",
		"listing": "CL2",
		"rated_v": 150,
		"temp_rating_c": 60,
		"riser": False,
		"resistance_ohm_per_kft": TABLE8_SOLID["16"],
		"riser_label": "16/2 CL2 0-10V (PR/GY)",
		"source_reference": SW_10034,
	},
	{
		"item_code": "FW-CMP-16-2-0-10V",
		"item_name": "16/2 CMP/FT6 plenum dimming cable",
		"wire_name": "16/2 CMP plenum 0-10 V dimming (Genesis GEN41)",
		"category": "control",
		"applications": "0-10v,dali",
		"conductors": "2x16 Cu solid signal",
		"listing": "CMP/FT6",
		"rated_v": 300,
		"temp_rating_c": 75,
		"plenum": True,
		"riser": True,
		"resistance_ohm_per_kft": TABLE8_SOLID["16"],
		"riser_label": "16/2 CMP 0-10V",
		"source_reference": SW_GEN41,
	},
	{
		"item_code": "FW-CL3R-18-2-SH",
		"item_name": "18/2 CL3R shielded stranded control cable",
		"wire_name": "18/2 CMR/CL3R shielded (Southwire 95214)",
		"category": "control",
		"applications": "0-10v,dali",
		"conductors": "2x18 Cu stranded signal; 1x24 Cu stranded ground",
		"listing": "CMR/CL3R/FPLR",
		"rated_v": 300,
		"temp_rating_c": 75,
		"riser": True,
		"shielded": True,
		"resistance_ohm_per_kft": TABLE8_STRANDED["18"],
		"od_in": 0.161,
		"riser_label": "18/2 SH CL3R",
		"source_reference": SW_SHIELD,
	},
	# --- Landscape (outdoor, direct burial) ----------------------------------------------------------
	*(landscape(awg) for awg in ("16", "14", "12", "10", "8")),
	# --- Line voltage to supplies ----------------------------------------------------------------------
	nmb("14"),
	nmb("12", od=0.422),
	*(raceway_set(awg) for awg in ("14", "12", "10")),
	{
		"item_code": "FW-MCAP-12-2",
		"item_name": "12/2 MC-AP armored cable",
		"wire_name": "MC-AP 12-2 Type MC (Southwire)",
		"category": "cable-assembly",
		"applications": "lv-branch",
		"conductors": "2x12 Cu solid power; 1x12 Al solid ground",
		"listing": "MC (MC-AP)",
		"rated_v": 600,
		"temp_rating_c": 90,
		"resistance_ohm_per_kft": TABLE8_SOLID["12"],
		"ampacity_basis": "310.16",
		"od_in": 0.538,
		"riser_label": "12/2 MC-AP",
		"source_reference": SW_MCAP,
	},
	# --- Data and controls ----------------------------------------------------------------------------
	{
		"item_code": "FW-BELDEN-9841",
		"item_name": "Belden 9841 DMX/RS-485 1 pair 24 AWG",
		"wire_name": "Belden 9841 DMX 1 pair 24 AWG shielded, CM",
		"category": "data",
		"applications": "dmx",
		"conductors": "2x24 Cu stranded data pair",
		"listing": "CM",
		"rated_v": 300,
		"temp_rating_c": 75,
		"shielded": True,
		"impedance_ohm": 120,
		"resistance_ohm_per_kft": 24,
		"od_in": 0.232,
		"riser_label": "DMX 1PR #24 SH (9841)",
		"source_reference": BELDEN_9841,
	},
	{
		"item_code": "FW-BELDEN-9842",
		"item_name": "Belden 9842 DMX/RS-485 2 pair 24 AWG",
		"wire_name": "Belden 9842 DMX 2 pair 24 AWG shielded, CM",
		"category": "data",
		"applications": "dmx",
		"conductors": "4x24 Cu stranded data pair",
		"listing": "CM",
		"rated_v": 300,
		"temp_rating_c": 75,
		"shielded": True,
		"impedance_ohm": 120,
		"resistance_ohm_per_kft": 24,
		"riser_label": "DMX 2PR #24 SH (9842)",
		"source_reference": BELDEN_9842,
	},
	{
		"item_code": "FW-BELDEN-82841",
		"item_name": "Belden 82841 plenum DMX/RS-485 1 pair 24 AWG",
		"wire_name": "Belden 82841 DMX 1 pair 24 AWG shielded, CMP",
		"category": "data",
		"applications": "dmx",
		"conductors": "2x24 Cu stranded data pair",
		"listing": "CMP",
		"rated_v": 300,
		"temp_rating_c": 75,
		"plenum": True,
		"riser": True,
		"shielded": True,
		"impedance_ohm": 120,
		"resistance_ohm_per_kft": 24,
		"riser_label": "DMX 1PR #24 SH CMP (82841)",
		"source_reference": BELDEN_82841,
	},
	{
		"item_code": "FW-CAT6-CMR",
		"item_name": "Category 6 U/UTP CMR (Belden 2412)",
		"wire_name": "Cat 6 U/UTP 4 pair 23 AWG CMR (Belden 2412)",
		"category": "data",
		"applications": "ethernet,dmx",
		"conductors": "8x24 Cu solid data pair",
		"listing": "CMR",
		"rated_v": 300,
		"temp_rating_c": 60,
		"riser": True,
		"impedance_ohm": 100,
		"resistance_ohm_per_kft": 24,
		"od_in": 0.224,
		"riser_label": "CAT6 CMR",
		"source_reference": BELDEN_2412
		+ " (23 AWG recorded as 24 AWG, the nearest size the spec form lists)",
	},
	{
		"item_code": "FW-CAT6-CMP",
		"item_name": "Category 6 U/UTP CMP (Belden 2413)",
		"wire_name": "Cat 6 U/UTP 4 pair 23 AWG CMP (Belden 2413)",
		"category": "data",
		"applications": "ethernet,dmx",
		"conductors": "8x24 Cu solid data pair",
		"listing": "CMP",
		"rated_v": 300,
		"temp_rating_c": 60,
		"plenum": True,
		"riser": True,
		"impedance_ohm": 100,
		"resistance_ohm_per_kft": 24,
		"riser_label": "CAT6 CMP",
		"source_reference": BELDEN_2413
		+ " (23 AWG recorded as 24 AWG, the nearest size the spec form lists)",
	},
	{
		"item_code": "FW-LUTRON-GRX-CBL-346S",
		"item_name": "Lutron GRX-CBL-346S QS link cable",
		"wire_name": "Lutron QS link cable GRX-CBL-346S (CL3R)",
		"category": "control",
		"applications": "lutron-qs",
		"conductors": "2x18 Cu stranded power; 2x22 Cu stranded data pair; 1x24 Cu stranded ground",
		"listing": "CL3R/CMR",
		"rated_v": 300,
		"temp_rating_c": 60,
		"riser": True,
		"resistance_ohm_per_kft": TABLE8_STRANDED["18"],
		"riser_label": "QS GRX-CBL-346S",
		"source_reference": LUTRON_QS,
	},
	{
		"item_code": "FW-LUTRON-GRX-PCBL-346S",
		"item_name": "Lutron GRX-PCBL-346S plenum QS link cable",
		"wire_name": "Lutron QS link cable GRX-PCBL-346S (plenum)",
		"category": "control",
		"applications": "lutron-qs",
		"conductors": "2x18 Cu stranded power; 2x22 Cu stranded data pair; 1x24 Cu stranded ground",
		"listing": "CL3P/CMP",
		"rated_v": 300,
		"temp_rating_c": 60,
		"plenum": True,
		"riser": True,
		"resistance_ohm_per_kft": TABLE8_STRANDED["18"],
		"riser_label": "QS GRX-PCBL-346S",
		"source_reference": LUTRON_QS_P,
	},
]


def cell(value):
	if value is None:
		return ""
	if value is True:
		return "1"
	if value is False:
		return "0"
	return str(value)


def csv_text(rows=ROWS):
	output = io.StringIO()
	writer = csv.DictWriter(output, fieldnames=COLUMNS, lineterminator="\n")
	writer.writeheader()
	for row in rows:
		values = {"sales_uom_mode": "Per Foot", "is_verified": 0, "is_active": 1, **row}
		writer.writerow({column: cell(values.get(column)) for column in COLUMNS})
	return output.getvalue()


def main(argv=None):
	TARGET.write_text(csv_text(), encoding="utf-8")
	print(f"Wrote {TARGET} ({len(ROWS)} wires)")
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
