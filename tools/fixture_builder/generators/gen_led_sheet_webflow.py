"""Generate current ilL-Webflow-Product imports from legacy family configuration."""

from .webflow_catalog import HEADERS
from .webflow_catalog import generate as generate_webflow


def generate(config, output_dir):
	return generate_webflow(config, output_dir, "led-sheet")
