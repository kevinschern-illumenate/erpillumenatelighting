"""Common lighting controls for controls in v1 (PRD question 7).

``python -m tools.seed_imports.controls_common`` writes ``controls_common.csv`` for the Desk controller
import (``system_design.controller_import.import_controllers``; dry run first). It adds the playback and
pixel controllers dealers ask for, next to the ilLumenate DMX controllers and decoders already on the site.

Every row cites its datasheet. Values the sheets do not give (terminal sizes, some input ranges) are left
blank, so the readiness report lists them for engineering instead of the designer trusting a guess. No
prices: add selling Item Prices after import.
"""

import csv
import io
import sys
from pathlib import Path

TARGET = Path(__file__).resolve().parent / "controls_common.csv"
COLUMNS = (
	"item_code",
	"item_name",
	"controller_name",
	"controller_type",
	"input_voltage_type",
	"input_voltage_min",
	"input_voltage_max",
	"standby_power_watts",
	"channels",
	"max_universes",
	"max_pixels",
	"max_data_length_ft",
	"dmx_footprint",
	"unit_load",
	"max_w_per_channel",
	"max_a_per_channel",
	"max_load_watts",
	"max_load_amps",
	"output_dimming",
	"terminal_min_awg",
	"terminal_max_awg",
	"input_protocols",
	"output_protocols",
	"ports",
	"item_group",
	"source_reference",
	"is_active",
)

PHAROS_LPC = (
	"Pharos Designer LPC datasheet: LPC 1 512 channels, LPC 2 1,024 channels DMX/eDMX; 2 DMX512/RDM ports "
	"(mirrored on LPC 1); 1 Ethernet/eDMX port; 9-48 V DC or PoE (Class 2, 4 W typical) "
	"https://www.ac-et.com/storage/product_images/pharos/lpc/pharos_designer_lpc_datasheet.pdf"
)
PHAROS_LPCX = (
	"Pharos LPC X datasheet: 19 in rackmount, eDMX output (sACN, Art-Net, KiNET, Pathport) on the data port, "
	"100-240 V AC 40 W typical; sold in universe capacities (this row: 10 universes) "
	"https://www.acclaimlighting.com/cdn/shop/files/Pharos_20LPC_20X.pdf"
)
ADVATEK_A4 = (
	"Advatek PixLite A4-S Mk3: 4 pixel outputs, up to 6 universes each (24 total), up to 4,080 RGB pixels, "
	"5-24 V input, sACN/Art-Net over Ethernet https://advatek.netlify.app/products/a4-s-mk3"
)
ADVATEK_16 = (
	"Advatek PixLite 16 Mk2 manual: 16 pixel outputs in two power banks, 96 universes of E1.31/Art-Net plus 4 "
	"DMX512 outputs; input voltage per the datasheet chart (not entered) "
	"https://manuals.plus/advatek/pixlite-16-mk2-long-range-control-board-manual.pdf"
)


def ports(*items):
	return "; ".join(items)


ROWS = [
	{
		"item_code": "PHAROS-LPC-1",
		"item_name": "Pharos Designer LPC 1 lighting playback controller",
		"controller_name": "Pharos LPC 1 (1 universe)",
		"controller_type": "DMX Controller",
		"input_voltage_type": "VDC",
		"input_voltage_min": 9,
		"input_voltage_max": 48,
		"standby_power_watts": 4,
		"channels": 512,
		"max_universes": 1,
		"input_protocols": "sACN, Art-Net",
		"output_protocols": "DMX512",
		"ports": ports("DMX 1:Out:DMX512:32", "DMX 2:Out:DMX512:32", "Ethernet:In:sACN"),
		"source_reference": PHAROS_LPC,
	},
	{
		"item_code": "PHAROS-LPC-2",
		"item_name": "Pharos Designer LPC 2 lighting playback controller",
		"controller_name": "Pharos LPC 2 (2 universes)",
		"controller_type": "DMX Controller",
		"input_voltage_type": "VDC",
		"input_voltage_min": 9,
		"input_voltage_max": 48,
		"standby_power_watts": 4,
		"channels": 1024,
		"max_universes": 2,
		"input_protocols": "sACN, Art-Net",
		"output_protocols": "DMX512",
		"ports": ports("DMX 1:Out:DMX512:32", "DMX 2:Out:DMX512:32", "Ethernet:In:sACN"),
		"source_reference": PHAROS_LPC,
	},
	{
		"item_code": "PHAROS-LPC-X-10",
		"item_name": "Pharos LPC X lighting playback controller, 10 universes",
		"controller_name": "Pharos LPC X 10 (eDMX)",
		"controller_type": "DMX Controller",
		"input_voltage_type": "VAC",
		"input_voltage_min": 100,
		"input_voltage_max": 240,
		"standby_power_watts": 40,
		"channels": 5120,
		"max_universes": 10,
		"output_protocols": "sACN, Art-Net",
		"ports": ports("Data:Out:sACN", "Management:In:sACN"),
		"source_reference": PHAROS_LPCX,
	},
	{
		"item_code": "ADVATEK-A4-S-MK3",
		"item_name": "Advatek PixLite A4-S Mk3 pixel controller",
		"controller_name": "PixLite A4-S Mk3 (4 outputs, 24 universes)",
		"controller_type": "Pixel Controller",
		"input_voltage_type": "VDC",
		"input_voltage_min": 5,
		"input_voltage_max": 24,
		"max_universes": 24,
		"max_pixels": 4080,
		"input_protocols": "sACN, Art-Net",
		"output_protocols": "SPI",
		"ports": ports(*(f"OUT{index}:Out:SPI:1020" for index in range(1, 5)), "Ethernet:In:sACN"),
		"source_reference": ADVATEK_A4,
	},
	{
		"item_code": "ADVATEK-PIXLITE-16-MK2",
		"item_name": "Advatek PixLite 16 Mk2 pixel controller",
		"controller_name": "PixLite 16 Mk2 (16 outputs, 100 universes)",
		"controller_type": "Pixel Controller",
		"input_voltage_type": "VDC",
		"max_universes": 100,
		"input_protocols": "sACN, Art-Net",
		"output_protocols": "SPI, DMX512",
		"ports": ports(
			*(f"OUT{index}:Out:SPI" for index in range(1, 17)),
			*(f"DMX{index}:Out:DMX512:32" for index in range(1, 5)),
			"Ethernet:In:sACN",
		),
		"source_reference": ADVATEK_16,
	},
]


def cell(value):
	return "" if value is None else str(value)


def csv_text(rows=ROWS):
	output = io.StringIO()
	writer = csv.DictWriter(output, fieldnames=COLUMNS, lineterminator="\n")
	writer.writeheader()
	for row in rows:
		values = {"output_dimming": "None", "is_active": 1, **row}
		writer.writerow({column: cell(values.get(column)) for column in COLUMNS})
	return output.getvalue()


def main(argv=None):
	TARGET.write_text(csv_text(), encoding="utf-8")
	print(f"Wrote {TARGET} ({len(ROWS)} controls)")
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
