"""Keep app state outside Frappe's temporary backup cleanup directory."""

from pathlib import Path


def private_state_directory(private_path, name):
	"""Relocate a legacy app directory intact; never merge or overwrite snapshots.

	Cloud runs its backup before migration hooks. A site already blocked at that
	step needs the same directory move performed by its operator before updating.
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
			raise FileExistsError(
				f"Both {legacy} and {directory} exist. Preserve both and resolve the app state "
				"directory conflict before retrying; no snapshots have been overwritten."
			)
		legacy.rename(directory)
	return directory
