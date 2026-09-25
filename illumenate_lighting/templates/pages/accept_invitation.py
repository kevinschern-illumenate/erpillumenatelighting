"""Invitation tokens stay in the browser fragment until an authenticated POST."""

no_cache = 1


def get_context(context):
	context.no_cache = 1
