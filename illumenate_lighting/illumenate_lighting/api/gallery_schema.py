# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Fixed lists and constants for the Webflow Gallery sync (see docs/WEBFLOW_GALLERY_SYNC.md)."""

import re

GALLERY_TYPES = (
	"Residential",
	"Hospitality",
	"Restaurant",
	"Healthcare",
	"Education",
	"Office",
	"Hotel",
	"Civic/Government",
	"Retail",
	"Architectural",
	"Transportation",
	"Landscape",
	"Multi-family",
	"Theater/Art",
	"Lobby",
	"Sports/Entertainment",
)

APPLICATIONS = (
	"Accent",
	"Cove",
	"Direct View",
	"Grazing",
	"Signage",
	"Task",
	"Undercabinet",
	"Toekick",
	"Recessed",
	"Millwork",
	"Perimeter",
	"Vanity",
	"Backlighting",
	"Step Lighting",
	"Display",
	"Shelving",
	"Washing",
	"Suspended",
	"Closet",
	"Undercounter",
)

DESIGN_SERVICES = (
	"Product Specification",
	"Takeoff Drawings",
	"Custom Installation Instructions",
	"Detailed Installation Drawings",
	"Photometric Calculations and Renderings",
	"Conceptual 3D Renderings",
	"Troubleshooting",
	"End-User Training",
)

# credit type -> (Webflow name field, Webflow website field)
CREDIT_FIELDS = {
	"Integrator": ("client-integrator", "client-website"),
	"Architect": ("architect", "architect-website"),
	"Designer": ("designer", "designer-website"),
	"Contractor": ("contractor", "contractor-website"),
	"Owner": ("owner", "owner-website"),
	"Photographer": ("photo-credit", "photographer-website"),
}
CREDIT_TYPES = tuple(CREDIT_FIELDS)

SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


# The status shown on the gallery form and list. Mirrors statusOf() in public/js/gallery_publication.js.
# With several target brands the gallery shows the status that most needs attention (first match).
PUBLICATION_STATUSES = (
	"Failed",
	"Queued",
	"Changes not staged",
	"Needs staging",
	"Staged",
	"Live",
	"Retired",
)
DEFAULT_PUBLICATION_STATUS = "Needs staging"


def publication_status(state, staged_hash=None, live_hash=None):
	"""The status label for one brand's publication record."""
	label = {
		"QUEUED": "Queued",
		"STAGED": "Staged",
		"LIVE": "Live",
		"FAILED": "Failed",
		"RETIRED": "Retired",
	}.get(state)
	if label:
		return label
	return "Changes not staged" if (staged_hash or live_hash) else "Needs staging"


def gallery_status(publications):
	"""One status for a gallery from its publication records (dicts); no record means not staged."""
	labels = {
		publication_status(p.get("state"), p.get("staged_hash"), p.get("live_hash")) for p in publications
	}
	for label in PUBLICATION_STATUSES:
		if label in labels:
			return label
	return DEFAULT_PUBLICATION_STATUS
