# Copyright (c) 2026, ilLumenate Lighting and contributors
# For license information, please see license.txt

"""Dimming protocol vocabulary shared with ``packages/data/src/protocols.ts`` (plan Appendix B.1).

``ilL-Attribute-Dimming Protocol.engine_protocol`` holds one of :data:`ENGINE_PROTOCOLS`. The WP-1.1 patch
pre-fills it from the attribute's ``protocol`` choice or, failing that, its label; anything it cannot
match stays blank and makes dependent catalog items ``incomplete`` ("unmapped protocol").
"""

import re

ENGINE_PROTOCOLS = (
	"none",
	"phase-forward",
	"phase-reverse",
	"0-10V",
	"1-10V",
	"DALI-2",
	"DMX512",
	"RDM",
	"sACN",
	"Art-Net",
	"CRMX-wireless",
	"Lutron-QS",
	"Lutron-EcoSystem",
	"PWM",
	"SPI",
)

# Phase-cut methods; they trigger the D4 review gate.
PHASE_PROTOCOLS = frozenset({"phase-forward", "phase-reverse"})
DMX_PROTOCOLS = frozenset({"DMX512", "RDM", "sACN", "Art-Net", "CRMX-wireless"})

# The attribute's own ``protocol`` Select, value for value.
ATTRIBUTE_PROTOCOLS = {
	"0-10V": "0-10V",
	"TRIAC": "phase-forward",
	"MLV": "phase-forward",
	"ELV": "phase-reverse",
	"DALI": "DALI-2",
	"DMX512": "DMX512",
	"DMX/RDM": "DMX512",
	"SPI": "SPI",
	"PWM": "PWM",
}

# Case-insensitive label rules, most specific first (Appendix B.1).
_LABEL_RULES = (
	(r"\b(lutron)\b.*\becosystem\b", "Lutron-EcoSystem"),
	(r"\b(lutron)\b.*\bqs\b", "Lutron-QS"),
	(r"\bcrmx\b", "CRMX-wireless"),
	(r"\bart-?net\b", "Art-Net"),
	(r"\bsacn\b", "sACN"),
	(r"\bdmx\b", "DMX512"),
	(r"\bdali\b", "DALI-2"),
	(r"\b1-10\s*v\b", "1-10V"),
	(r"\b0-10\s*v\b", "0-10V"),
	(r"\b(elv|reverse[- ]phase|trailing[- ]edge)\b", "phase-reverse"),
	(r"\b(triac|mlv|forward[- ]phase|leading[- ]edge)\b", "phase-forward"),
	(r"\bspi\b", "SPI"),
	(r"\bpwm\b", "PWM"),
	(r"\b(none|non-dimming|on/off)\b", "none"),
)


def engine_protocol_for(protocol=None, label=None):
	"""Best engine protocol for an attribute record, or ``None`` when nothing matches."""
	if protocol and protocol in ATTRIBUTE_PROTOCOLS:
		return ATTRIBUTE_PROTOCOLS[protocol]
	text = str(label or "").lower()
	for pattern, value in _LABEL_RULES:
		if re.search(pattern, text):
			return value
	return None
