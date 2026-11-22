# Shipping: EasyPost labels and tracking (Phases 1 to 3)

How the outbound shipping build in this repo works, the contract between ERPNext and
n8n, and the setup steps. The plan itself is in `SHIPPING_RECEIVING_PLAN.md`.

## 1. Flow

1. **Delivery Note → Create Shipment** (button, saved or submitted note). Opens a new,
   unsaved Shipment with the defaults filled in: warehouse pickup address, the note's
   shipping address and contact, value of goods, today's date and the default pickup
   window, the default description of content, and one suggested parcel when the
   Items carry a weight. If a Shipment already lists the note, the button opens it instead.
2. Staff add boxes, picking a Parcel Template (native **Add Template**) or typing the
   dimensions, then enter the scale weight. Units are **inches and pounds**.
3. **Submit** the Shipment. Before submit, every parcel needs a positive length, width,
   height and weight. A row with Count 3 becomes three rows of one box each, so every box
   gets its own tracking number. Parcels over the hard limits in ilL-Shipping-Settings
   are refused, and parcels over the additional handling or oversize thresholds are
   flagged (`ill_special_handling`).
4. **Create Labels** (submitted Shipment, needs Submit permission on Shipment). ERPNext
   asks n8n for a rate (`action: rate`) and shows the rate, the service, the
   address-verification result and any surcharge flags. **Confirm** buys it
   (`action: buy`). ERPNext writes back the master tracking number (`awb_number`), each
   box's number and label, the tracking URL, the EasyPost id, the cost
   (`shipment_amount`), `ill_label_status = Bought`, and attaches one merged label PDF.
   The carrier and master number are mirrored to every linked Delivery Note
   (`ill_carrier`, `ill_tracking_number`).
5. **Submit the Delivery Note** as today. Buy the labels first and the shipment email
   already carries the tracking links.
6. EasyPost tracker events reach n8n, and n8n calls `receive_tracking_event`. ERPNext
   updates each box's status and the Shipment's `tracking_status`, sets the Shipment to
   Completed once every box is delivered, emails the shipping lead on exceptions, and
   (when switched on) emails the dealer on delivery.
7. **Void Label** (needs Submit permission) asks n8n to refund every box, sets
   `ill_label_status = Voided`, clears the numbers on the Shipment and on the Delivery
   Notes that still show them, and keeps the old numbers in a timeline comment. A voided
   Shipment can buy labels again. A Shipment with bought labels cannot be cancelled until
   they are voided.

The dealer portal, the shipment emails and the Delivery Note and Packing List print
formats read every tracking number from the linked, submitted, non-voided Shipments
(`portal/shipment_tracking.py`). Notes without a Shipment fall back to the manual
`ill_carrier` / `ill_tracking_number` fields, then `transporter_name` / `vehicle_no` /
`lr_no`.

## 2. Settings (ilL-Shipping-Settings)

| Field | Use |
| --- | --- |
| Enabled | Create Labels and Void Label refuse while off. Create Shipment and tracking work either way |
| Label Webhook URL | n8n webhook for `rate`, `buy`, `void` (workflow `shipping_easypost_labels.json`) |
| Webhook Shared Secret | HMAC key for both directions. `shipping_webhook_secret` in site_config wins |
| EasyPost Carrier Account ID | Our FedEx account in EasyPost (`ca_...`), passed through to n8n |
| Service / Residential Service | EasyPost service names, defaults `FEDEX_GROUND` and `GROUND_HOME_DELIVERY` |
| Pickup Address | Warehouse Address used as the Shipment pickup address |
| Pickup From / To | Default pickup window |
| Description of Content | Default for the required Shipment field |
| Default Parcel Template | Dimensions for the suggested parcel on Create Shipment |
| Exception Alert Email | Shipping lead address for tracking exceptions and returns |
| Send Delivered Email | Email dealer contacts when a Shipment is delivered (off by default) |
| Surcharge thresholds | Additional handling (longest side 48 in, second side 30 in, 50 lb, length + girth 105 in), oversize (96 in, length + girth 130 in) and hard limits (108 in, 150 lb, length + girth 165 in). FedEx published values; **check against our agreement** |

## 3. Signing

Both directions use the same shared secret. The signature header is
`X-ilL-Signature` = lowercase hex HMAC-SHA256 of the **raw request body**. A
`sha256=` prefix is accepted on the way in. A blank secret never verifies.

* ERPNext → n8n: ERPNext signs the body it posts. n8n verifies it with the n8n variable
  `SHIPPING_WEBHOOK_SECRET` before calling EasyPost.
* n8n → ERPNext: n8n signs the exact JSON string it posts to `receive_tracking_event`.

The EasyPost API key lives **only** in n8n, as an HTTP Basic Auth credential (key as user,
blank password). Use a test-mode key on staging.

## 4. ERPNext → n8n (label webhook)

`POST <Label Webhook URL>`, `Content-Type: application/json`. n8n answers in the same
request (Respond to Webhook). ERPNext waits up to 60 seconds.

### Common request fields

```json
{
  "action": "rate",
  "shipment": "SHIPMENT-00012",
  "easypost_id": null,
  "carrier": "FedEx",
  "service": "FEDEX_GROUND",
  "residential_service": "GROUND_HOME_DELIVERY",
  "carrier_account_id": "ca_123",
  "from_address": {"name": "Shipping", "company": "ilLumenate Lighting", "street1": "...",
                   "street2": "", "city": "...", "state": "WA", "zip": "98000",
                   "country": "US", "phone": "...", "email": "..."},
  "to_address": {"name": "...", "company": "...", "street1": "...", "street2": "",
                 "city": "...", "state": "..", "zip": "...", "country": "US",
                 "phone": "...", "email": "..."},
  "parcels": [
    {"row": "a1b2c3", "length_in": 48, "width_in": 6, "height_in": 6,
     "weight_lb": 12.5, "additional_handling": false}
  ],
  "reference": "SHIPMENT-00012",
  "delivery_notes": ["MAT-DN-2026-00031"]
}
```

* Weight is in **pounds**. n8n converts to ounces (`weight_lb * 16`) in one place.
* `row` is the Shipment Parcel row name. n8n sets it as the EasyPost shipment `reference`
  and returns it, so numbers map back to boxes.
* `easypost_id` is the EasyPost Order id from the rate step (`buy`, `void`).

### `rate`

n8n verifies `to_address` (`verify: ["delivery"]`), creates an EasyPost **Order** with
one shipment per parcel (`options.label_format = "PDF"`, `options.additional_handling`
per parcel, `carrier_accounts = [carrier_account_id]`) and picks the rate for `carrier`
with `residential_service` when the verified address is residential, `service`
otherwise. Nothing is bought.

```json
{"ok": true, "easypost_id": "order_abc",
 "rate": {"carrier": "FedEx", "service": "FEDEX_GROUND", "amount": 41.27,
          "currency": "USD", "delivery_days": 3},
 "rates": [{"carrier": "FedEx", "service": "FEDEX_GROUND", "amount": 41.27,
            "currency": "USD", "delivery_days": 3}],
 "address": {"verified": true, "residential": false, "messages": []},
 "messages": []}
```

### `buy`

`POST /v2/orders/{easypost_id}/buy` with `carrier` and the service the rate step chose,
which ERPNext sends back as `service_selected` (falling back to `service`). If EasyPost
says the order is already bought, n8n reads the order and returns it, so a retry never
buys twice.

```json
{"ok": true, "easypost_id": "order_abc", "carrier": "FedEx", "service": "FEDEX_GROUND",
 "amount": 41.27, "currency": "USD", "master_tracking": "7949...",
 "tracking_url": "https://track.easypost.com/...",
 "parcels": [{"row": "a1b2c3", "tracking_number": "7949...",
              "label_url": "https://easypost-files.s3.amazonaws.com/....pdf",
              "easypost_shipment_id": "shp_..."}]}
```

### `void`

Reads the order and posts `/v2/shipments/{id}/refund` for each bought shipment.

```json
{"ok": true, "refunds": [{"easypost_shipment_id": "shp_...", "status": "submitted"}]}
```

### Errors (any action)

HTTP 200 with:

```json
{"ok": false, "error": "address_invalid", "message": "Address not found",
 "messages": ["..."]}
```

`error` is one of `address_invalid`, `no_rate`, `already_refunded`, `easypost_error`,
`bad_request`. ERPNext shows `message`, sets `ill_label_status = Error` (except on a
failed void, which leaves Bought) and stores the message in `ill_label_message`. A
timeout or non-200 is treated as `easypost_error`. **After a timeout on buy, check EasyPost
before retrying.** The retry reuses the same order id, so it cannot buy twice.

## 5. n8n → ERPNext (tracker events)

`POST https://<site>/api/method/illumenate_lighting.illumenate_lighting.api.shipping.receive_tracking_event`,
signed as above. The workflow `shipping_easypost_tracker.json` receives EasyPost's
`tracker.updated` / `tracker.created` webhooks, verifies EasyPost's
`X-Hmac-Signature` with the EasyPost webhook secret, and forwards:

```json
{"tracking_code": "7949...", "status": "delivered", "status_detail": "arrived_at_destination",
 "carrier": "FedEx", "est_delivery_date": "2026-11-25T00:00:00Z",
 "message": "Delivered, Left at front door", "occurred_at": "2026-11-24T18:03:00Z",
 "public_url": "https://track.easypost.com/..."}
```

Responses: `{"success": true, "shipment": "...", "tracking_status": "Delivered"}`, or a
404 `{"success": false, "error": "not_found"}` when no Shipment holds that number (n8n
should not retry that). Status mapping:

| EasyPost status | Box | Shipment `tracking_status` |
| --- | --- | --- |
| `delivered` | Delivered | Delivered once every box is delivered, and Shipment status becomes Completed |
| `return_to_sender` | Returned | Returned, plus an exception alert |
| `failure`, `error` | Exception | unchanged, plus an exception alert |
| `cancelled` | Cancelled | unchanged |
| anything else | In Transit, Out for Delivery, ... | In Progress |

## 6. Setup checklist

1. `bench migrate` (creates ilL-Shipping-Settings, the custom fields, the unit labels on
   Shipment Parcel and the `shipping-integration@illumenate.lighting` service user).
2. Create the warehouse **Address** (with phone and email) and the **Shipment Parcel
   Templates** for our standard boxes.
3. In EasyPost: connect our FedEx account, note its carrier account id, create a webhook
   to the tracker workflow's URL, and copy its secret.
4. In n8n: import both workflows, add the EasyPost Basic Auth credential (test key on
   staging), set the variables `SHIPPING_WEBHOOK_SECRET`, `EASYPOST_WEBHOOK_SECRET` and
   `ERPNEXT_BASE_URL`, then activate.
5. In ilL-Shipping-Settings: Label Webhook URL, the shared secret, carrier account id,
   pickup address and window, exception email, then tick **Enabled**.
6. Permissions: whoever has **Submit** on Shipment can buy and void labels. Set that in
   Role Permissions Manager (Stock User / Stock Manager by default).
7. Walk through the test cases in the plan's section 10 on staging.
