"""Keep app state outside Frappe's temporary backup cleanup directory."""

from datetime import datetime, timezone
from pathlib import Path


def private_state_directory(private_path, name, log=None):
	"""Relocate a legacy app directory intact; never merge or overwrite snapshots.

	Frappe's backup cleanup removes every non-file entry of ``private/backups``,
	so any directory left there breaks all backups. When both the legacy and the
	current directory exist, the legacy tree is moved whole into a new
	``legacy-<UTC timestamp>`` child of the current directory. Nothing is merged,
	and ``log`` (if given) is told where it went so a person can review it.
	"""
	if name not in ("ill-workspace", "b2b-release"):
		raise ValueError("Unknown app state directory")
	private = Path(private_path)
	directory = private / name
	legacy = private / "backups" / name
	for path in (legacy, directory):
		if path.is_symlink() or (path.exists() and not path.is_dir()):
			raise ValueError(f"Expected an app state directory, not a file or symlink: {path}")
	if legacy.exists():
		if directory.exists():
			stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
			destination = directory / f"legacy-{stamp}"
			suffix = 1
			while destination.exists():
				destination = directory / f"legacy-{stamp}-{suffix}"
				suffix += 1
			legacy.rename(destination)
			if log:
				log(
					f"Both {legacy} and {directory} existed. The legacy directory was moved intact to "
					f"{destination}; review any pending snapshot it holds. Nothing was merged or deleted."
				)
		else:
			legacy.rename(directory)
	return directory
