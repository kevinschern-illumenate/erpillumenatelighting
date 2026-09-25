"""Legacy segment URL preserved as an adapter to the current configurator."""

from illumenate_lighting.templates.pages.configuration_routes import redirect_to_configurator

no_cache = 1


def get_context(context):
    redirect_to_configurator("Linear Fixture")
