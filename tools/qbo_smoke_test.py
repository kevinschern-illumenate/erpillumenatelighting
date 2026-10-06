#!/usr/bin/env python3
"""
Smoke-test the ERPNext QBO payment endpoint without touching any money.

Sends two requests to receive_payment_event:
  1. A correctly signed Delete for a QBO payment id that cannot exist.
     Expect HTTP 200, {"success": true, "action": "skipped"} and a new
     ilL-QBO-Sync-Log row with status Skipped-NoOp.
  2. The same body with a wrong signature. Expect HTTP 401 "unauthorized".

Usage:
    QBO_WEBHOOK_SECRET=<same value as ilL-QBO-Settings> \
        python3 tools/qbo_smoke_test.py https://illumenatelighting.v.frappe.cloud
"""

import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request

PATH = "/api/method/illumenate_lighting.illumenate_lighting.api.qbo_sync.receive_payment_event"


def post(url, body, signature):
	req = urllib.request.Request(
		url,
		data=body,
		method="POST",
		headers={"Content-Type": "application/json", "X-QBO-Signature": signature},
	)
	try:
		with urllib.request.urlopen(req, timeout=30) as resp:
			return resp.status, resp.read().decode()
	except urllib.error.HTTPError as e:
		return e.code, e.read().decode()


def main():
	if len(sys.argv) != 2 or not os.environ.get("QBO_WEBHOOK_SECRET"):
		sys.exit(__doc__)
	url = sys.argv[1].rstrip("/") + PATH
	secret = os.environ["QBO_WEBHOOK_SECRET"].encode()
	body = json.dumps({"qbo_payment_id": f"SMOKE-{int(time.time())}", "event_type": "Delete"}).encode()

	signed_status, text = post(url, body, hmac.new(secret, body, hashlib.sha256).hexdigest())
	print(f"signed request   -> HTTP {signed_status}: {text}")
	try:
		signed_ok = signed_status == 200 and json.loads(text)["message"]["success"] is True
	except (ValueError, KeyError, TypeError):
		signed_ok = False

	bad_status, text = post(url, body, "0" * 64)
	print(f"bad signature    -> HTTP {bad_status}: {text}")

	if signed_ok and bad_status == 401:
		print("PASS: endpoint reachable, secret matches, bad signatures rejected")
		return 0
	if signed_status == 401:
		print("FAIL: signed request rejected — secret differs from ilL-QBO-Settings / site_config")
	elif signed_status == 404:
		print("FAIL: endpoint not found — is the latest app deployed to this site?")
	else:
		print("FAIL: see responses above")
	return 1


if __name__ == "__main__":
	sys.exit(main())
