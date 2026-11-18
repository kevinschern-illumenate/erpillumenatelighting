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
