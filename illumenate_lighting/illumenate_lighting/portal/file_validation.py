"""Bounded content validation shared by private uploads and packet preflight."""

import hashlib
import io
import warnings
from pathlib import PurePosixPath

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_FILES = 10
MAX_PDF_PAGES = 500
MAX_IMAGE_PIXELS = 40_000_000
HEIF_EXTENSIONS = (".heic", ".heif")
# ISO-BMFF major brands written by phones and cameras for HEIF still images.
# AVIF ("avif") and video brands are deliberately absent.
HEIF_BRANDS = frozenset((b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"))
HEIF_JPEG_QUALITY = 90


def stored_bytes(file):
	"""The exact bytes of a Frappe ``File``; ``get_content`` decodes what it can to text."""
	content = file.get_content()
	if isinstance(content, str):
		with open(file.get_full_path(), "rb") as handle:
			content = handle.read()
	return content


def is_heif(content):
	"""True when the bytes open with an ISO-BMFF ``ftyp`` box whose major brand is HEIF."""
	return (
		isinstance(content, bytes)
		and len(content) >= 12
		and content[4:8] == b"ftyp"
		and int.from_bytes(content[:4], "big") >= 16
		and content[8:12] in HEIF_BRANDS
	)


def normalize_upload(filename, content):
	"""Convert a HEIC/HEIF photo to a baseline JPEG; any other upload passes through untouched.

	The 20 MiB cap applies to the uploaded bytes. The converted image is
	orientation-corrected and written without EXIF/XMP, so GPS and camera metadata
	never reach storage. The JPEG then goes through ``validate_content`` as usual.
	"""
	name = PurePosixPath((filename or "").replace("\\", "/")).name
	if PurePosixPath(name).suffix.lower() not in HEIF_EXTENSIONS:
		return filename, content
	if not isinstance(content, bytes) or not content or len(content) > MAX_FILE_BYTES:
		raise ValueError("File must contain between 1 byte and 20 MiB")
	if not is_heif(content):
		raise ValueError("Image content does not match its filename")
	try:
		import pillow_heif
	except ImportError as exc:
		raise ValueError("HEIC photos are not supported here; export the photo as JPEG") from exc
	from PIL import Image, ImageOps

	pillow_heif.register_heif_opener()
	try:
		with warnings.catch_warnings():
			warnings.simplefilter("error", Image.DecompressionBombWarning)
			with Image.open(io.BytesIO(content)) as source:
				if source.format != "HEIF" or source.width * source.height > MAX_IMAGE_PIXELS:
					raise ValueError("Image must be HEIC with at most 40 million pixels")
				icc_profile = source.info.get("icc_profile")
				image = ImageOps.exif_transpose(source).convert("RGB")
		image.info = {}
		output = io.BytesIO()
		save = {"format": "JPEG", "quality": HEIF_JPEG_QUALITY, "optimize": True}
		if icc_profile:
			save["icc_profile"] = icc_profile
		image.save(output, **save)
	except Exception as exc:
		raise ValueError(f"Image validation failed: {exc}") from exc
	return f"{PurePosixPath(name).stem or 'photo'}.jpg", output.getvalue()


def validate_content(filename, content):
	if not isinstance(content, bytes) or not content or len(content) > MAX_FILE_BYTES:
		raise ValueError("File must contain between 1 byte and 20 MiB")
	filename = PurePosixPath((filename or "").replace("\\", "/")).name
	extension = PurePosixPath(filename).suffix.lower()
	if not filename or len(filename) > 180:
		raise ValueError("Use a filename of at most 180 characters")
	pages = None
	if extension == ".pdf" and content.startswith(b"%PDF-"):
		from pypdf import PdfReader

		try:
			reader = PdfReader(io.BytesIO(content), strict=True)
			if reader.is_encrypted:
				raise ValueError("Encrypted PDFs are not supported")
			pages = len(reader.pages)
			if not 1 <= pages <= MAX_PDF_PAGES:
				raise ValueError("PDF must have 1 to 500 pages")
			root = reader.trailer["/Root"]
			names = root.get("/Names", {})
			if hasattr(names, "get_object"):
				names = names.get_object()
			if root.get("/OpenAction") or root.get("/AA") or names.get("/JavaScript"):
				raise ValueError("PDF actions are not supported")
		except Exception as exc:
			raise ValueError(f"PDF validation failed: {exc}") from exc
		mime = "application/pdf"
	elif extension in (".png", ".jpg", ".jpeg"):
		from PIL import Image

		try:
			with warnings.catch_warnings():
				warnings.simplefilter("error", Image.DecompressionBombWarning)
				with Image.open(io.BytesIO(content)) as source:
					if (
						source.format not in ("PNG", "JPEG")
						or source.width * source.height > MAX_IMAGE_PIXELS
					):
						raise ValueError("Image must be PNG/JPEG with at most 40 million pixels")
					if (extension == ".png") != (source.format == "PNG"):
						raise ValueError("Image content does not match its filename")
					mime = Image.MIME[source.format]
					source.verify()
		except Exception as exc:
			raise ValueError(f"Image validation failed: {exc}") from exc
	else:
		raise ValueError("Only PDF, JPEG and PNG content is accepted")
	return {
		"filename": filename,
		"size": len(content),
		"sha256": hashlib.sha256(content).hexdigest(),
		"mime_type": mime,
		"pages": pages,
	}
