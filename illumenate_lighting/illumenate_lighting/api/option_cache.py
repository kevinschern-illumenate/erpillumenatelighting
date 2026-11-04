"""Cache read-only configurator option projections per template (plan 6.5).

A projection is the catalog-derived answer an init endpoint builds for one
template: allowed options resolved to attribute rows, specs, offerings and
sellable Items. It never depends on the user. Endpoints keep their permission
and template-visibility checks and strip prices from the cached copy as before.

Keys carry the catalog revision. ``product_finder.facts.catalog_stamp`` changes
when any template, spec, attribute, Item or Webflow Product is saved or deleted
(``hooks.py`` doc_events, which also covers publication) and otherwise within
its 60 s stamp cache. Mapping doctypes that are not part of that stamp call
:func:`invalidate` from their own hooks. Keys also fingerprint the site's
``ill_*`` config keys, so flipping a kill switch a projection reads (such as
the hero-image order) takes effect at once. Site flag ``ill_option_projection_cache``
(default on) turns caching off without a deploy.
"""

import copy
import hashlib
from time import time_ns

import frappe

PREFIX = "ill_option_projection"
EPOCH_KEY = PREFIX + ":epoch"
TTL_SECONDS = 3600

# Saved on their own (not as template child rows) and read by cached projections.
MAPPING_DOCTYPES = (
	"ilL-Rel-Driver-Eligibility",
	"ilL-Rel-Kit-Endcap-Map",
	"ilL-Rel-Kit-Lens-Map",
	"ilL-Rel-Kit-Mounting-Map",
	"ilL-Rel-Kit-Profile-Map",
)


def enabled():
	from illumenate_lighting.illumenate_lighting.portal.site_flags import option_projection_cache_enabled

	return option_projection_cache_enabled()


def _site_flags_fingerprint():
	conf = frappe.conf or {}
	flags = sorted((str(key), repr(conf.get(key))) for key in conf if str(key).startswith("ill_"))
	return hashlib.sha1(repr(flags).encode(), usedforsecurity=False).hexdigest()[:12]


def catalog_revision():
	from illumenate_lighting.illumenate_lighting.portal.product_finder.facts import catalog_stamp

	return f"{catalog_stamp()}:{frappe.cache().get_value(EPOCH_KEY) or 0}:{_site_flags_fingerprint()}"


def projection_key(kind, template):
	return f"{PREFIX}:{kind}:{template}:{catalog_revision()}"


def cached_projection(kind, template, build):
	"""``build()``'s result for ``(kind, template)`` at the current catalog revision.

	Only a successful result (no ``success: False``) is stored. Callers get their
	own copy, so stripping or decorating it never alters the cached value.
	"""
	if not template or not enabled():
		return build()
	key = projection_key(kind, template)
	cached = frappe.cache().get_value(key)
	if cached is not None:
		return copy.deepcopy(cached)
	result = build()
	if not (isinstance(result, dict) and result.get("success") is False):
		frappe.cache().set_value(key, copy.deepcopy(result), expires_in_sec=TTL_SECONDS)
	return result


def invalidate(*_args, **_kwargs):
	"""doc_events handler: drop every cached projection by moving to a new epoch."""
	frappe.cache().set_value(EPOCH_KEY, str(time_ns()))
