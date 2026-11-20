"""Package the AutoCAD toolkit as an Autodesk ``.bundle`` (draw-to-quote plan 3.11).

``python -m tools.cad_toolkit.package_bundle [--out dist]`` writes ``ilLumenate.bundle`` (and a zip of it):

- ``PackageContents.xml``: loads ``Contents/ilLumenate.lsp`` at startup in every drawing;
- ``Contents/ilLumenate.lsp``: the toolkit's LISP files joined in load order (one file, so load order
  never depends on the autoloader);
- ``Contents/ilLumenate-layers.scr``: the DWT layer script; ``Contents/README.txt``.

Dealers unzip it into ``%APPDATA%\\Autodesk\\ApplicationPlugins`` (Windows) or
``~/Library/Application Support/Autodesk/ApplicationAddins`` (Mac). The catalog is not bundled: it is
downloaded from the portal per user (no prices, refreshed when it goes stale).
"""

import argparse
import shutil
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent
LISP = ROOT / "lisp"
ORDER = (
	"il-util.lsp",
	"il-json.lsp",
	"il-math.lsp",
	"il-sha256.lsp",
	"il-catalog.lsp",
	"il-model.lsp",
	"il-assets.lsp",
	"il-core.lsp",
	"il-blocks.lsp",
	"il-commands.lsp",
)
APP_ID = "{7C4E0E6B-4C2B-4E7E-9E1A-1F0C9B7A2D10}"
COMMANDS = (
	"ILSETUP",
	"ILCATALOG",
	"ILSTYLE",
	"ILTAPE",
	"ILCONVERT",
	"ILJUMPER",
	"ILFEED",
	"ILSCALE",
	"ILROOM",
	"ILCAB",
	"ILPSU",
	"ILCONNECT",
	"ILWIRE",
	"ILOTHER",
	"ILOVERRIDE",
	"ILUPDATE",
	"ILCHECK",
	"ILQUOTE",
	"ILRECEIPT",
	"ILOUT",
	"ILRISER",
	"ILSTRIP",
	"ILVERSION",
	"ILHELP",
)


def version():
	text = (LISP / "il-util.lsp").read_text(encoding="ascii")
	return text.split('(setq *il-version* "', 1)[1].split('"', 1)[0]


def joined_lisp():
	parts = [
		f";;; ilLumenate CAD toolkit {version()} -- built by tools/cad_toolkit/package_bundle.py. Do not edit.\n"
	]
	for name in ORDER:
		parts.append(f"\n;;; ---- {name} ----\n")
		parts.append((LISP / name).read_text(encoding="ascii"))
	return "".join(parts)


def package_contents():
	commands = "\n".join(f'        <Command Global="{name}" Local="{name}" />' for name in COMMANDS)
	return f"""<?xml version="1.0" encoding="utf-8"?>
<ApplicationPackage SchemaVersion="1.0" AppVersion="{escape(version())}" ProductCode="{APP_ID}"
  Name="ilLumenate CAD toolkit" Description="Draw ilLumenate LED runs and export a draw-to-quote package for the dealer portal."
  Author="ilLumenate Lighting" AutodeskProduct="AutoCAD" ProductType="Application" SupportedLocales="Enu">
  <CompanyDetails Name="ilLumenate Lighting" Url="https://illumenate.lighting" />
  <Components Description="AutoLISP toolkit">
    <RuntimeRequirements OS="Win64|Mac" Platform="AutoCAD*" SeriesMin="R23.0" />
    <ComponentEntry AppName="ilLumenate" Version="{escape(version())}" ModuleName="./Contents/ilLumenate.lsp"
      AppDescription="ilLumenate draw-to-quote commands" LoadOnAutoCADStartup="True" PerDocument="True">
      <Commands GroupName="ILLUMENATE">
{commands}
      </Commands>
    </ComponentEntry>
  </Components>
</ApplicationPackage>
"""


README = """ilLumenate CAD toolkit {version}

Install: copy the ilLumenate.bundle folder into
  Windows: %APPDATA%\\Autodesk\\ApplicationPlugins
  Mac:     ~/Library/Application Support/Autodesk/ApplicationAddins
then restart AutoCAD. Type ILHELP for the commands.

1. ILSETUP, then ILCATALOG with the CAD catalog downloaded from the ilLumenate portal.
2. ILSCALE the architect's underlay, ILROOM the rooms, ILCAB the cabinets.
3. ILSTYLE a run style, ILTAPE or ILCONVERT the runs, ILPSU and ILCONNECT the supplies, ILWIRE the home runs.
4. ILCHECK, then ILQUOTE to write the .ilq.json package.
5. On the schedule page in the portal: Import Drawing. Download the receipt and run ILRECEIPT.

The toolkit makes no network calls and never holds prices. Lengths it shows are hints: the portal's
configurators snap, split and build every run, and the System Designer sizes supplies and wire.
Supported: AutoCAD 2019+ on Windows; AutoCAD LT 2024+ and AutoCAD for Mac pending the version spike.
"""


def build(out):
	out = Path(out)
	bundle = out / "ilLumenate.bundle"
	if bundle.exists():
		shutil.rmtree(bundle)
	contents = bundle / "Contents"
	contents.mkdir(parents=True)
	(bundle / "PackageContents.xml").write_text(package_contents(), encoding="utf-8")
	(contents / "ilLumenate.lsp").write_text(joined_lisp(), encoding="ascii", newline="\r\n")
	from tools.cad_toolkit.build.layers import script

	(contents / "ilLumenate-layers.scr").write_text(script(), encoding="ascii", newline="\r\n")
	(contents / "README.txt").write_text(README.format(version=version()), encoding="ascii", newline="\r\n")
	archive = out / f"ilLumenate-cad-toolkit-{version()}.zip"
	with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as handle:
		for path in sorted(bundle.rglob("*")):
			if path.is_file():
				handle.write(path, path.relative_to(out).as_posix())
	return bundle, archive


def main(argv=None):
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("--out", default="dist")
	args = parser.parse_args(argv)
	bundle, archive = build(args.out)
	print(f"Wrote {bundle} and {archive}")
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
