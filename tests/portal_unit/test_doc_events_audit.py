"""doc_events handlers never do synchronous network I/O — plan item 1.8.

External work (QBO, Webflow, email) must be queued: QBO through
``frappe.enqueue(..., enqueue_after_commit=True)``, Webflow by flagging rows
Pending for the publication worker, mail through ``portal.outbox``.
"""

import ast
import pathlib
import re
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]
HOOKS = REPO / "illumenate_lighting" / "hooks.py"
NETWORK = re.compile(
	r"\brequests\.(get|post|put|patch|delete|request|Session)\b|\burlopen\(|\bhttpx\.|"
	r"\bmake_(get|post|put|patch|delete)_request\(|\bfrappe\.sendmail\("
)


def doc_event_handlers():
	tree = ast.parse(HOOKS.read_text(encoding="utf-8"))
	for node in tree.body:
		if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "doc_events" for t in node.targets):
			events = ast.literal_eval(node.value)
			for doctype, handlers in events.items():
				for event, paths in handlers.items():
					for path in paths if isinstance(paths, list) else [paths]:
						yield doctype, event, path


def module_source(dotted_function):
	module = dotted_function.rpartition(".")[0]
	return (REPO / (module.replace(".", "/") + ".py")).read_text(encoding="utf-8")


def function_source(dotted_function):
	source = module_source(dotted_function)
	name = dotted_function.rpartition(".")[2]
	for node in ast.parse(source).body:
		if isinstance(node, ast.FunctionDef) and node.name == name:
			return ast.get_source_segment(source, node)
	raise AssertionError(f"{dotted_function} not found")


def reachable_source(dotted_function):
	"""Source of the handler plus every same-module function it calls, transitively."""
	source = module_source(dotted_function)
	functions = {
		node.name: node for node in ast.parse(source).body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
	}
	pending, seen = [dotted_function.rpartition(".")[2]], set()
	while pending:
		name = pending.pop()
		if name in seen or name not in functions:
			continue
		seen.add(name)
		for node in ast.walk(functions[name]):
			if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
				pending.append(node.func.id)
	return "\n".join(ast.get_source_segment(source, functions[name]) for name in sorted(seen))


class DocEventsAudit(unittest.TestCase):
	def test_inventory_resolves(self):
		handlers = list(doc_event_handlers())
		self.assertGreater(len(handlers), 30)
		for _doctype, _event, path in handlers:
			function_source(path)

	def test_handlers_make_no_direct_network_calls(self):
		offenders = sorted({path for _d, _e, path in doc_event_handlers() if NETWORK.search(reachable_source(path))})
		self.assertEqual(offenders, [])

	def test_reachability_follows_same_module_calls(self):
		reachable = reachable_source("illumenate_lighting.illumenate_lighting.api.qbo_bills.on_submit")
		self.assertIn("def _queue", reachable)
		self.assertNotIn("def send(", reachable)  # the worker runs in the queue, not the hook
		self.assertTrue(NETWORK.search(function_source("illumenate_lighting.illumenate_lighting.api.qbo_bills.send")))

	def test_qbo_bill_hooks_enqueue_after_commit(self):
		queue = function_source("illumenate_lighting.illumenate_lighting.api.qbo_bills._queue")
		self.assertIn("frappe.enqueue(", queue)
		self.assertIn("enqueue_after_commit=True", queue)
		for hook in ("on_submit", "on_cancel"):
			self.assertIn("_queue(", function_source(f"illumenate_lighting.illumenate_lighting.api.qbo_bills.{hook}"))

	def test_customer_notifications_go_through_the_outbox(self):
		notify = function_source("illumenate_lighting.illumenate_lighting.portal.notifications.notify_user")
		self.assertIn("outbox", notify)


if __name__ == "__main__":
	unittest.main()
