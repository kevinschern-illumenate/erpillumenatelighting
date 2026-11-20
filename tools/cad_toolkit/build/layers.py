"""The DWT layer table as an AutoCAD script (draw-to-quote plan 1.6).

Reads ``tools/system_designer/packages/data/src/layers.json`` (the riser layers and the plan-view
layers) and writes ``ilLumenate-layers.scr``: run it once in an empty drawing (SCRIPT), then save the
drawing as ``ilLumenate.dwt``. ILSETUP makes the same layers with entmake, so a template is optional.
``python -m tools.cad_toolkit.build.layers`` rewrites the committed copy; a test keeps it current.
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
LAYERS = REPO / "tools/system_designer/packages/data/src/layers.json"
TARGET = REPO / "tools/cad_toolkit/build/ilLumenate-layers.scr"
ACAD_LINETYPES = ("DASHED", "DASHED2", "DASHDOT", "PHANTOM", "HIDDEN", "DOT")


def ascii_text(value):
	return (
		str(value)
		.replace("\u2013", "-")
		.replace("\u2014", "-")
		.encode("ascii", "replace")
		.decode()
		.replace('"', "'")
	)


def layer_rows(data):
	rows = [{**layer, "plot": layer.get("export", True)} for layer in data["layers"]]
	return rows + list(data.get("planLayers") or [])


def script(data=None):
	data = data or json.loads(LAYERS.read_text(encoding="utf-8"))
	lines = ["; ilLumenate layer standard (generated from layers.json; do not edit)", "CMDECHO", "0"]
	used = sorted({layer["linetype"] for layer in layer_rows(data)} & set(ACAD_LINETYPES))
	for linetype in used:
		lines += ["_.-LINETYPE", "_Load", linetype, "acad.lin", ""]
	for layer in layer_rows(data):
		name = layer["name"]
		lines += [
			"_.-LAYER",
			"_Make",
			name,
			"_Color",
			str(layer["aciColor"]),
			name,
			"_Ltype",
			layer["linetype"],
			name,
			"_LWeight",
			f"{layer['lineweightMm']:g}",
			name,
			"_Plot",
			"_Plot" if layer["plot"] else "_No",
			name,
			"_Description",
			ascii_text(layer["description"]),
			name,
			"",
		]
	lines += ["_.-LAYER", "_Set", "0", "", "CMDECHO", "1", ""]
	return "\n".join(lines)


def main(argv=None):
	TARGET.write_text(script(), encoding="ascii", newline="\r\n")
	print(f"Wrote {TARGET}")
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
