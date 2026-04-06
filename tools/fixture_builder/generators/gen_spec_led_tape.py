"""Generator for ilL-Spec-LED Tape.csv — tape spec rows.

One row per TapeSpecDef. Multi-line continuation rows for dimming protocols.
"""

from __future__ import annotations

from ..config_schema import FixtureBuilderConfig
from .common import write_csv

HEADERS = [
    "Item",
    "LED Package",
    "Product Category",
    "Input Voltage",
    "Watts per Foot",
    "Voltage Drop Max Run Length (ft)",
    "Input Protocol",
    "Lumens per Foot",
    "CRI Typical",
    "LED Pitch (mm)",
    "PCB Mounting",
    "PCB Finish",
    "Cut Increment (mm)",
    "Is Free Cutting",
    "Leader Cable Item",
    "Protocol (Supported Dimming Protocols)",
]


def generate(config: FixtureBuilderConfig, output_dir: str) -> str:
    """Generate ilL-Spec-LED Tape.csv and return the filepath."""
    rows = []

    for ts in config.tape_specs:
        # Primary row with first dimming protocol (if any)
        first_protocol = ts.dimming_protocols[0] if ts.dimming_protocols else ""
        rows.append([
            ts.item_code,
            ts.led_package,
            ts.product_category,
            ts.input_voltage,
            ts.watts_per_foot,
            ts.voltage_drop_max_run_length_ft,
            ts.input_protocol,
            ts.lumens_per_foot,
            ts.cri_typical,
            ts.led_pitch_mm,
            ts.pcb_mounting,
            ts.pcb_finish,
            ts.cut_increment_mm,
            1 if ts.is_free_cutting else 0,
            ts.leader_cable_item,
            first_protocol,
        ])

        # Continuation rows for additional dimming protocols
        for protocol in ts.dimming_protocols[1:]:
            row = [""] * len(HEADERS)
            row[15] = protocol  # Protocol column
            rows.append(row)

    filepath = f"{output_dir}/ilL-Spec-LED Tape.csv"
    write_csv(filepath, HEADERS, rows)
    return filepath
