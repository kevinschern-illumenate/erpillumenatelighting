"""Bounded content validation shared by private uploads and packet preflight."""

import hashlib
import io
import warnings
from pathlib import PurePosixPath

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_FILES = 10
MAX_PDF_PAGES = 500
MAX_IMAGE_PIXELS = 40_000_000


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
