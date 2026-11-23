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

# Advatek's current range, read from its product pages on 2026-11-23 (advatek.netlify.app, the site's
# mirror of advateklighting.com). The A-series and receivers carry pixel power; the E-series does not; the
# T-series are long-range transmitters whose RJ45 outputs feed R-series receivers up to 300 m away.
# "Auxiliary port for DMX512 In/Out" on the controllers is the AUX port below.
ADVATEK_PAGE = "https://advatek.netlify.app/products/"
ADVATEK_E4 = (
	"Advatek PixLite E4-S Mk3: 24 universes of Art-Net or sACN, 4 non-powered pixel outputs (1,020 RGB each), "
	"RS485 auxiliary port for DMX512 in/out, 1 Ethernet port, 5-24 V DC, 2.5 W maximum power consumption, "
	"wall or DIN rail " + ADVATEK_PAGE + "e4-s-mk3"
)
ADVATEK_E16 = (
	"Advatek PixLite E16-S Mk3: 96 universes of Art-Net or sACN, 16 non-powered pixel outputs (1,020 RGB "
	"each), RS485 auxiliary port for DMX512 in/out, 1 Ethernet port, 5-24 V DC, 3.5 W maximum power "
	"consumption, wall or DIN rail " + ADVATEK_PAGE + "e16-s-mk3"
)
ADVATEK_T8 = (
	"Advatek PixLite T8-S Mk3 long range transmitter: 96 universes of Art-Net or sACN, 8 RJ45 data outputs to "
	"R2/R4 receivers placed up to 300 m away, up to 16,320 RGB pixels, RS485 auxiliary port for DMX512 in/out, "
	"2 Ethernet ports, 100-240 V AC, panel, wall or rack mount " + ADVATEK_PAGE + "t8-s-mk3"
)
ADVATEK_T16X = (
	"Advatek PixLite T16X-S Mk3 long range transmitter: 96 universes of Art-Net or sACN, 16 RJ45 data outputs "
	"to R1/R2 receivers, RS485 auxiliary port for DMX512 in/out, 2 Ethernet ports, 100-240 V AC, panel, wall "
	"or rack mount; total pixels not stated " + ADVATEK_PAGE + "t16x-s-mk3"
)
ADVATEK_R1F = (
	"Advatek PixLite R1F-S long range receiver (for the T16X-S): 1 pixel output (1,020 RGB), 1 data input from "
	"the transmitter up to 300 m away, 5-48 V DC, 10 A per output, DIN rail or surface mount "
	+ ADVATEK_PAGE
	+ "r1f-s"
)
ADVATEK_R2F = (
	"Advatek PixLite R2F-S long range receiver (for the T8-S or T16X-S): 2 fused pixel outputs (1,020 RGB "
	"each), 1 data input from the transmitter up to 300 m away, 5-24 V DC, 6 A per output (7.5 A fuses), 12 A "
	"total, wall or DIN rail " + ADVATEK_PAGE + "r2f-s"
)
ADVATEK_R4D = (
	"Advatek PixLite R4D-S long range receiver (for the T8-S): 4 fused pixel outputs (510 RGB each), 1 data "
	"input from the transmitter up to 300 m away, 5-24 V DC, 6 A per output (7.5 A fuses), 24 A total, wall or "
	"DIN rail " + ADVATEK_PAGE + "r4d-s"
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
	{
		"item_code": "ADVATEK-E4-S-MK3",
		"item_name": "Advatek PixLite E4-S Mk3 pixel controller",
		"controller_name": "PixLite E4-S Mk3 (4 outputs, 24 universes)",
		"controller_type": "Pixel Controller",
		"input_voltage_type": "VDC",
		"input_voltage_min": 5,
		"input_voltage_max": 24,
		"standby_power_watts": 2.5,
		"max_universes": 24,
		"max_pixels": 4080,
		"input_protocols": "sACN, Art-Net",
		"output_protocols": "SPI, DMX512",
		"ports": ports(
			*(f"OUT{index}:Out:SPI:1020" for index in range(1, 5)), "AUX:Out:DMX512:32", "Ethernet:In:sACN"
		),
		"source_reference": ADVATEK_E4,
	},
	{
		"item_code": "ADVATEK-E16-S-MK3",
		"item_name": "Advatek PixLite E16-S Mk3 pixel controller",
		"controller_name": "PixLite E16-S Mk3 (16 outputs, 96 universes)",
		"controller_type": "Pixel Controller",
		"input_voltage_type": "VDC",
		"input_voltage_min": 5,
		"input_voltage_max": 24,
		"standby_power_watts": 3.5,
		"max_universes": 96,
		"max_pixels": 16320,
		"input_protocols": "sACN, Art-Net",
		"output_protocols": "SPI, DMX512",
		"ports": ports(
			*(f"OUT{index}:Out:SPI:1020" for index in range(1, 17)), "AUX:Out:DMX512:32", "Ethernet:In:sACN"
		),
		"source_reference": ADVATEK_E16,
	},
	{
		"item_code": "ADVATEK-T8-S-MK3",
		"item_name": "Advatek PixLite T8-S Mk3 long range pixel transmitter",
		"controller_name": "PixLite T8-S Mk3 (8 long-range outputs, 96 universes)",
		"controller_type": "Pixel Controller",
		"input_voltage_type": "VAC",
		"input_voltage_min": 100,
		"input_voltage_max": 240,
		"max_universes": 96,
		"max_pixels": 16320,
		"max_data_length_ft": 984,
		"input_protocols": "sACN, Art-Net",
		"output_protocols": "SPI, DMX512",
		"ports": ports(
			*(f"RX{index}:Out:SPI:1" for index in range(1, 9)), "AUX:Out:DMX512:32", "Ethernet:In:sACN"
		),
		"source_reference": ADVATEK_T8,
	},
	{
		"item_code": "ADVATEK-T16X-S-MK3",
		"item_name": "Advatek PixLite T16X-S Mk3 long range pixel transmitter",
		"controller_name": "PixLite T16X-S Mk3 (16 long-range outputs, 96 universes)",
		"controller_type": "Pixel Controller",
		"input_voltage_type": "VAC",
		"input_voltage_min": 100,
		"input_voltage_max": 240,
		"max_universes": 96,
		"max_data_length_ft": 984,
		"input_protocols": "sACN, Art-Net",
		"output_protocols": "SPI, DMX512",
		"ports": ports(
			*(f"RX{index}:Out:SPI:1" for index in range(1, 17)), "AUX:Out:DMX512:32", "Ethernet:In:sACN"
		),
		"source_reference": ADVATEK_T16X,
	},
	{
		"item_code": "ADVATEK-R1F-S",
		"item_name": "Advatek PixLite R1F-S long range pixel receiver",
		"controller_name": "PixLite R1F-S receiver (1 output)",
		"controller_type": "Pixel Controller",
		"input_voltage_type": "VDC",
		"input_voltage_min": 5,
		"input_voltage_max": 48,
		"max_pixels": 1020,
		"max_data_length_ft": 984,
		"max_a_per_channel": 10,
		"max_load_amps": 10,
		"input_protocols": "SPI",
		"output_protocols": "SPI",
		"ports": ports("Data In:In:SPI", "OUT1:Out:SPI:1020"),
		"source_reference": ADVATEK_R1F,
	},
	{
		"item_code": "ADVATEK-R2F-S",
		"item_name": "Advatek PixLite R2F-S long range pixel receiver",
		"controller_name": "PixLite R2F-S receiver (2 outputs)",
		"controller_type": "Pixel Controller",
		"input_voltage_type": "VDC",
		"input_voltage_min": 5,
		"input_voltage_max": 24,
		"max_pixels": 2040,
		"max_data_length_ft": 984,
		"max_a_per_channel": 6,
		"max_load_amps": 12,
		"input_protocols": "SPI",
		"output_protocols": "SPI",
		"ports": ports("Data In:In:SPI", "OUT1:Out:SPI:1020", "OUT2:Out:SPI:1020"),
		"source_reference": ADVATEK_R2F,
	},
	{
		"item_code": "ADVATEK-R4D-S",
		"item_name": "Advatek PixLite R4D-S long range pixel receiver",
		"controller_name": "PixLite R4D-S receiver (4 outputs)",
		"controller_type": "Pixel Controller",
		"input_voltage_type": "VDC",
		"input_voltage_min": 5,
		"input_voltage_max": 24,
		"max_pixels": 2040,
		"max_data_length_ft": 984,
		"max_a_per_channel": 6,
		"max_load_amps": 24,
		"input_protocols": "SPI",
		"output_protocols": "SPI",
		"ports": ports("Data In:In:SPI", *(f"OUT{index}:Out:SPI:510" for index in range(1, 5))),
		"source_reference": ADVATEK_R4D,
	},
]


# --- Pharos: the full current range, read from pharoscontrols.com on 2026-11-23 --------------------
#
# Designer hardware (https://www.pharoscontrols.com/designer/hardware/) and Express products
# (https://www.pharoscontrols.com/express/products/). One row per orderable code on those pages (capacity and
# finish variants included). Interfaces the controller schema has no protocol for (contact closure and
# analog inputs, relays, RS232/RS485, MIDI, audio, timecode, KiNET, Pathport) are described in the source
# text instead of as ports. Ethernet links to Pharos controllers are recorded as sACN, the eDMX protocol the
# rest of the catalog uses. Typical power is entered where the page gives watts; AC units give only amps.
PHAROS = "https://www.pharoscontrols.com/"


def pharos_row(code, name, controller_name, controller_type, page, facts, **spec):
	"""One Pharos row: item ``PHAROS-<code>``, the page it came from and what the page says."""
	return {
		"item_code": "PHAROS-" + code.replace("+", "-PLUS").replace(" ", "-"),
		"item_name": name,
		"controller_name": controller_name,
		"controller_type": controller_type,
		"source_reference": f"Pharos {code}: {facts} {PHAROS}{page}",
		**spec,
	}


def pharos_rows():
	rows = []
	poe2 = {"input_voltage_type": "VDC"}  # PoE powered: no input range on the page
	rows.append(
		pharos_row(
			"LPC 4",
			"Pharos Designer LPC 4 lighting playback controller",
			"Pharos LPC 4 (4 universes)",
			"DMX Controller",
			"designer/hardware/lpc/",
			"2,048 channels eDMX, 2 isolated RDM-compatible DMX512 ports, Ethernet (sACN, Art-Net, KiNET, Pathport), "
			"8 contact closure/digital/analog inputs, RS232/RS485/DMX in serial port, MIDI, DALI via RIO D4, "
			"9-48 V DC or PoE (802.3af Class 2) 4 W typical 7 W maximum, 8-module DIN rail",
			input_voltage_type="VDC",
			input_voltage_min=9,
			input_voltage_max=48,
			standby_power_watts=4,
			channels=2048,
			max_universes=4,
			input_protocols="sACN, Art-Net",
			output_protocols="DMX512",
			ports=ports("DMX 1:Out:DMX512:32", "DMX 2:Out:DMX512:32", "Ethernet:In:sACN"),
		)
	)
	for universes in range(20, 101, 10):
		rows.append(
			pharos_row(
				f"LPC X S3 {universes}",
				f"Pharos Designer LPC X S3 {universes} lighting playback controller",
				f"Pharos LPC X S3 {universes} ({universes} universes eDMX)",
				"DMX Controller",
				"designer/hardware/lpc-x/",
				f"{universes * 512:,} channels eDMX; DMX512 and DALI via Pharos gateways; 10/100/1000 Ethernet "
				"(etherCON); RS232; 100-240 V AC 50-60 Hz 0.4-0.2 A; 19 in 1U rack",
				input_voltage_type="VAC",
				input_voltage_min=100,
				input_voltage_max=240,
				channels=universes * 512,
				max_universes=universes,
				output_protocols="sACN, Art-Net",
				ports=ports("Data:Out:sACN", "Management:In:sACN"),
			)
		)
	for family, codes, page, depth in (
		("VLC S2", (50, 100, 250, 500, 1000, 1500), "designer/hardware/vlc/", "19 in 1U rack"),
		("VLC+ M", (50, 100, 250, 500), "designer/hardware/vlc-plus/", "19 in 1U rack"),
		("VLC+", (1000, 1500, 3000), "designer/hardware/vlc-plus/", "19 in 2U rack"),
	):
		for universes in codes:
			rows.append(
				pharos_row(
					f"{family} {universes}",
					f"Pharos Designer {family} {universes} video lighting controller",
					f"Pharos {family} {universes} ({universes} universes eDMX)",
					"DMX Controller",
					page,
					f"video lighting controller, {universes * 512:,} channels eDMX; DMX512 and DALI via Pharos gateways; "
					f"10/100/1000 Ethernet (etherCON); 100-240 V AC 50-60 Hz 0.4-0.2 A; {depth}",
					input_voltage_type="VAC",
					input_voltage_min=100,
					input_voltage_max=240,
					channels=universes * 512,
					max_universes=universes,
					output_protocols="sACN, Art-Net",
					ports=ports("Data:Out:sACN", "Management:In:sACN"),
				)
			)
	for size, watts in ((5, 7), (8, 10)):
		rows.append(
			pharos_row(
				f"TPS {size} B",
				f'Pharos Designer TPS {size} touch panel station, {size}" black',
				f'Pharos TPS {size} B ({size}" touchscreen)',
				"Scene Controller",
				"designer/hardware/tps/",
				f'{size}" capacitive wall touchscreen for any Designer controller, 10/100 Ethernet, PoE (802.3af '
				f"Class 0) {watts} W typical",
				standby_power_watts=watts,
				input_protocols="sACN",
				ports=ports("Ethernet:Bidirectional:sACN"),
				**poe2,
			)
		)
	for region in ("UK", "US"):
		for finish, label in (("BB", "black on black"), ("CC", "cream on cream"), ("WW", "white on white")):
			rows.append(
				pharos_row(
					f"BPS {region} {finish}",
					f"Pharos Designer BPS button panel station, {region} backbox, {label}",
					f"Pharos BPS {region} {finish} (8 buttons)",
					"Scene Controller",
					"designer/hardware/bps/",
					f"8 programmable buttons with LEDs, magnetic overlay, flush {region} single-gang backbox, 10/100 "
					"Ethernet, PoE (802.3af Class 1) 1.5 W typical",
					standby_power_watts=1.5,
					input_protocols="sACN",
					ports=ports("Ethernet:Bidirectional:sACN"),
					**poe2,
				)
			)
	rows += [
		pharos_row(
			"RIO 84",
			"Pharos RIO 84 remote input output device",
			"Pharos RIO 84 (8 in, 4 out, serial/DMX)",
			"Gateway",
			"designer/hardware/rio/",
			"8 contact closure/digital/analog inputs (24 V max), 4 outputs, RS232/RS485/DMX serial port for output "
			"or triggering, 10/100 Ethernet, PoE (802.3af Class 1) 1.5 W typical, 6-module DIN rail",
			standby_power_watts=1.5,
			input_protocols="sACN",
			output_protocols="DMX512",
			ports=ports("Serial:Out:DMX512:32", "Ethernet:In:sACN"),
			**poe2,
		),
		pharos_row(
			"RIO A",
			"Pharos Designer RIO A remote audio input device",
			"Pharos RIO A (audio, LTC, MIDI)",
			"Gateway",
			"designer/hardware/rio-a/",
			"stereo audio in (or linear timecode), MIDI in and out, MIDI Show Control and MTC, 10/100 Ethernet, "
			"PoE (802.3af Class 1) 1.5 W typical, 4-module DIN rail",
			standby_power_watts=1.5,
			input_protocols="sACN",
			ports=ports("Ethernet:Bidirectional:sACN"),
			**poe2,
		),
		pharos_row(
			"RIO D4",
			"Pharos RIO D4 remote DALI 4-port device",
			"Pharos RIO D4 (4 DALI ports)",
			"Gateway",
			"designer/hardware/rio-d4/",
			"4 DALI ports that transmit and receive DALI commands, for Designer and Express controllers (up to four "
			"per Express Control), 10/100 Ethernet, PoE (802.3af Class 2) 7 W maximum, 6-module DIN rail",
			standby_power_watts=7,
			input_protocols="sACN",
			output_protocols="DALI",
			ports=ports(*(f"DALI {index}:Out:DALI:64" for index in range(1, 5)), "Ethernet:In:sACN"),
			**poe2,
		),
		pharos_row(
			"RIO G4",
			"Pharos RIO G4 remote gateway 4-port device",
			"Pharos RIO G4 (4 DMX/SDI ports)",
			"Gateway",
			"designer/hardware/rio-g4/",
			"4 isolated RDM-capable DMX512 ports (or SDI serial output) for Designer and Express controllers (up to "
			"four per Express Control), 100 Ethernet, PoE (802.3af Class 2) 7 W maximum, 6-module DIN rail",
			standby_power_watts=7,
			input_protocols="sACN",
			output_protocols="DMX512",
			ports=ports(*(f"DMX {index}:Out:DMX512:32" for index in range(1, 5)), "Ethernet:In:sACN"),
			**poe2,
		),
	]
	for count in (10, 20):
		rows.append(
			pharos_row(
				f"EDN {count}",
				f"Pharos Designer EDN {count} Ethernet data node",
				f"Pharos EDN {count} ({count} DMX/RDM ports)",
				"Gateway",
				"designer/hardware/edn/",
				f"{count} isolated RDM-compatible DMX512 ports (or SDI serial output), 1+1 etherCON Ethernet, 100-240 V "
				"AC 50-60 Hz 0.25-0.12 A, 19 in 1U rack",
				input_voltage_type="VAC",
				input_voltage_min=100,
				input_voltage_max=240,
				max_universes=count,
				input_protocols="sACN",
				output_protocols="DMX512",
				ports=ports(
					*(f"DMX {index}:Out:DMX512:32" for index in range(1, count + 1)), "Ethernet:In:sACN"
				),
			)
		)
	rows += [
		pharos_row(
			"SDI",
			"Pharos Designer SDI serial data interface",
			"Pharos SDI (DMX to serial pixel data, 3 universes)",
			"Pixel Controller",
			"designer/hardware/sdi/",
			"converts DMX from an EDN or RIO G4 port to synchronous (SPI, e.g. WS2812, APA102) or asynchronous serial "
			"LED data, up to 3 universes (1,536 channels) per unit, 5-28 V DC 0.3 W typical 0.6 W maximum, "
			"2-module DIN rail",
			input_voltage_type="VDC",
			input_voltage_min=5,
			input_voltage_max=28,
			standby_power_watts=0.3,
			channels=1536,
			max_universes=3,
			input_protocols="DMX512",
			output_protocols="SPI",
			ports=ports("Serial In:In:DMX512", "Serial Out:Out:SPI"),
		),
		pharos_row(
			"PAC R",
			"Pharos Repeat DMX splitter, 1 in 4 out",
			"Pharos Repeat (DMX splitter 1 in, 4 out)",
			"Repeater",
			"designer/hardware/repeat/",
			"DMX/RDM input repeated onto 4 RDM-compatible outputs, 9-48 V DC 4 W typical, 6-module DIN rail",
			input_voltage_type="VDC",
			input_voltage_min=9,
			input_voltage_max=48,
			standby_power_watts=4,
			input_protocols="DMX512",
			output_protocols="DMX512",
			ports=ports("DMX In:In:DMX512", *(f"DMX {index}:Out:DMX512:32" for index in range(1, 5))),
		),
		pharos_row(
			"PAC S",
			"Pharos Switch unmanaged 4-port PoE Ethernet switch",
			"Pharos Switch (4-port PoE)",
			"Gateway",
			"designer/hardware/switch/",
			"unmanaged Ethernet switch with 4 Class 2 PoE ports for LPC 1/2/4, TPS, BPS, Express Touch and RIO "
			"devices, 24 V DC, 45 W maximum depending on load, 6-module DIN rail",
			input_voltage_type="VDC",
			input_voltage_min=24,
			input_voltage_max=24,
			input_protocols="sACN",
			output_protocols="sACN",
			ports=ports("Uplink:In:sACN", *(f"PoE {index}:Out:sACN:1" for index in range(1, 5))),
		),
	]
	for universes in (1, 2, 4, 6):
		rows.append(
			pharos_row(
				f"XPC {universes}",
				f"Pharos Express Control {universes} lighting controller",
				f"Pharos Express Control {universes} ({universes * 512:,} channels)",
				"DMX Controller",
				"express/products/",
				f"{universes * 512:,} channels, 2 isolated self-healing RDM DMX512 ports, eDMX (sACN, Art-Net, KiNET), "
				"DALI port (up to 64 devices, separate bus supply), 2 contact closure/digital/analog inputs, 2 relay "
				"outputs, 10/100 Ethernet, 9-48 V DC or PoE (802.3af Class 2) 4 W typical, DIN rail",
				input_voltage_type="VDC",
				input_voltage_min=9,
				input_voltage_max=48,
				standby_power_watts=4,
				channels=universes * 512,
				max_universes=universes,
				input_protocols="sACN, Art-Net",
				output_protocols="DMX512, DALI",
				ports=ports(
					"DMX 1:Out:DMX512:32", "DMX 2:Out:DMX512:32", "DALI:Out:DALI:64", "Ethernet:In:sACN"
				),
			)
		)
	for size, watts in ((5, 7), (8, 10)):
		for finish, label in (("B", "black"), ("W", "white")):
			rows.append(
				pharos_row(
					f"XPT {size} {finish}",
					f"Pharos Express Touch {size} wall touchscreen, {label}",
					f'Pharos Express Touch {size} {finish} ({size}" touchscreen)',
					"Scene Controller",
					"express/products/",
					f'{size}" capacitive wall touchscreen for Express Control (up to 32 per controller), PoE (802.3af '
					f"Class 0) {watts} W typical",
					standby_power_watts=watts,
					input_protocols="sACN",
					ports=ports("Ethernet:Bidirectional:sACN"),
					**poe2,
				)
			)
	return rows


ROWS = ROWS + pharos_rows()


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
